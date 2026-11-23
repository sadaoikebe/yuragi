// yuragi TSF text service (DESIGN「TIP」).
//
// The TIP runs inside other people's applications, so it does as little as
// possible: it sends keys to the broker over a named pipe and writes the
// replies on screen. It never starts Python, never retries, keeps no files.
// The only process it may start is the broker, under the three conditions of
// DESIGN「ブローカーを起動する条件」. Its decisions that need no TSF live in tip_logic.h (tested on any OS).
//
// Practices from SampleIME / CorvusSKK / Mozc:
//   - disabled / empty context / keyboard closed: not our key
//   - empty composition: Back/Enter/Esc go to the application
//   - RequestEditSession: SYNC, then ASYNCDONTCARE on TF_E_SYNCHRONOUS
// Never block ActivateEx (Windows 11's TextInputHost is shared).

#include <windows.h>
#include <oleauto.h>
#include <olectl.h>
#include <initguid.h>
#include <msctf.h>
#include <ctffunc.h>
#include <inputscope.h>
#include <sddl.h>
#include <userenv.h>

#include <algorithm>
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cwchar>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "resource.h"
#include "tip_json.h"
#include "tip_logic.h"
#include "tip_popup.h"

#ifndef YURAGI_TAG
#define YURAGI_TAG "dev"
#endif

using tip_logic::Link;
using tip_logic::Message;
using tip_logic::Mode;
using tip_logic::Notice;

// {A7C4E201-0B3A-4F11-9E61-0C1A0B7E0A01}
static const CLSID CLSID_YuragiTip = {
    0xa7c4e201, 0x0b3a, 0x4f11, {0x9e, 0x61, 0x0c, 0x1a, 0x0b, 0x7e, 0x0a, 0x01}};
// {A7C4E202-0B3A-4F11-9E61-0C1A0B7E0A01}
static const GUID GUID_YuragiProfile = {
    0xa7c4e202, 0x0b3a, 0x4f11, {0x9e, 0x61, 0x0c, 0x1a, 0x0b, 0x7e, 0x0a, 0x01}};
// {A7C4E206-0B3A-4F11-9E61-0C1A0B7E0A01}
static const GUID GUID_YuragiToggle = {
    0xa7c4e206, 0x0b3a, 0x4f11, {0x9e, 0x61, 0x0c, 0x1a, 0x0b, 0x7e, 0x0a, 0x01}};
static const GUID kCats[] = {
    GUID_TFCAT_TIP_KEYBOARD,
    GUID_TFCAT_DISPLAYATTRIBUTEPROVIDER,
    GUID_TFCAT_TIPCAP_COMLESS,
    GUID_TFCAT_TIPCAP_INPUTMODECOMPARTMENT,
    GUID_TFCAT_TIPCAP_IMMERSIVESUPPORT,
    GUID_TFCAT_TIPCAP_SYSTRAYSUPPORT,
};

static LONG g_locks = 0;
static HINSTANCE g_hinst = nullptr;
static bool g_log = false;  // tip.json "log": true

static const wchar_t kProductKey[] = L"Software\\yuragi-ime";
static const wchar_t kMaintenanceMutex[] = L"Local\\yuragi-ime-maintenance";

// Only when tip.json asks for it: every application writes here.
static void Log(const wchar_t* fmt, ...) {
    if (!g_log) return;
    wchar_t path[MAX_PATH];
    GetTempPathW(MAX_PATH, path);
    wcscat_s(path, L"yuragi_tip.log");
    FILE* f = nullptr;
    _wfopen_s(&f, path, L"ab");
    if (!f) return;
    wchar_t buf[1024];
    va_list ap;
    va_start(ap, fmt);
    _vsnwprintf_s(buf, _TRUNCATE, fmt, ap);  // vswprintf_s ends the host application on overflow
    va_end(ap);
    char line[sizeof(buf) / sizeof(buf[0]) * 3 + 1];  // UTF-8, one line per call
    int n = WideCharToMultiByte(CP_UTF8, 0, buf, -1, line, (int)sizeof(line) - 1, nullptr, nullptr);
    if (n > 0) {
        line[n - 1] = '\n';
        fwrite(line, 1, (size_t)n, f);
    }
    fclose(f);
}

static std::wstring Utf8ToWide(const std::string& s) {
    if (s.empty()) return {};
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    if (n <= 0) return {};
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), w.data(), n);
    return w;
}

// Key times for the chord FSM: the high-resolution counter.
static ULONGLONG NowMs() {
    static LARGE_INTEGER frequency = [] {
        LARGE_INTEGER f;
        QueryPerformanceFrequency(&f);
        return f;
    }();
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (ULONGLONG)(c.QuadPart * 1000 / frequency.QuadPart);
}

static UINT VkOf(WPARAM w) { return (UINT)(w & 0xFF); }

static tip_logic::Mods HeldMods() {
    tip_logic::Mods m;
    m.shift = (GetKeyState(VK_SHIFT) & 0x8000) != 0;
    m.ctrl = (GetKeyState(VK_CONTROL) & 0x8000) != 0;
    m.alt = (GetKeyState(VK_MENU) & 0x8000) != 0;
    m.win = ((GetKeyState(VK_LWIN) | GetKeyState(VK_RWIN)) & 0x8000) != 0;
    return m;
}

static bool CompartmentSet(ITfCompartmentMgr* cm, REFGUID guid) {
    ITfCompartment* c = nullptr;
    bool set = false;
    if (SUCCEEDED(cm->GetCompartment(guid, &c)) && c) {
        VARIANT v;
        VariantInit(&v);
        if (SUCCEEDED(c->GetValue(&v)) && v.vt == VT_I4 && v.lVal) set = true;
        VariantClear(&v);
        c->Release();
    }
    return set;
}

// Disabled or empty contexts are not ours (SampleIME / CorvusSKK / Mozc).
static bool KeyboardDisabled(ITfThreadMgr* tm) {
    if (!tm) return true;
    ITfDocumentMgr* dm = nullptr;
    if (FAILED(tm->GetFocus(&dm)) || !dm) return true;
    ITfContext* ctx = nullptr;
    if (FAILED(dm->GetTop(&ctx)) || !ctx) {
        dm->Release();
        return true;
    }
    bool disabled = false;
    ITfCompartmentMgr* cm = nullptr;
    if (SUCCEEDED(ctx->QueryInterface(IID_ITfCompartmentMgr, (void**)&cm)) && cm) {
        disabled = CompartmentSet(cm, GUID_COMPARTMENT_KEYBOARD_DISABLED) ||
                   CompartmentSet(cm, GUID_COMPARTMENT_EMPTYCONTEXT);
        cm->Release();
    }
    ctx->Release();
    dm->Release();
    return disabled;
}

static bool KeyboardClosed(ITfThreadMgr* tm) {
    if (!tm) return true;
    ITfCompartmentMgr* cm = nullptr;
    if (FAILED(tm->QueryInterface(IID_ITfCompartmentMgr, (void**)&cm)) || !cm) return false;
    bool closed = false;
    ITfCompartment* c = nullptr;
    if (SUCCEEDED(cm->GetCompartment(GUID_COMPARTMENT_KEYBOARD_OPENCLOSE, &c)) && c) {
        VARIANT v;
        VariantInit(&v);
        if (SUCCEEDED(c->GetValue(&v)) && v.vt == VT_I4 && v.lVal == 0) closed = true;
        VariantClear(&v);
        c->Release();
    }
    cm->Release();
    return closed;
}

static bool OpenKeyboard(ITfThreadMgr* tm, TfClientId id) {
    if (!tm || id == TF_CLIENTID_NULL) return false;
    ITfCompartmentMgr* cm = nullptr;
    if (FAILED(tm->QueryInterface(IID_ITfCompartmentMgr, (void**)&cm)) || !cm) return false;
    bool changed = false;
    ITfCompartment* c = nullptr;
    if (SUCCEEDED(cm->GetCompartment(GUID_COMPARTMENT_KEYBOARD_OPENCLOSE, &c)) && c) {
        VARIANT v;
        VariantInit(&v);
        v.vt = VT_I4;
        v.lVal = 1;
        changed = SUCCEEDED(c->SetValue(id, &v));
        VariantClear(&v);
        c->Release();
    }
    cm->Release();
    return changed;
}

static std::wstring DllDir() {
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(g_hinst, path, MAX_PATH);
    std::wstring s(path);
    size_t slash = s.find_last_of(L"\\/");
    if (slash != std::wstring::npos) s.resize(slash);
    return s;
}

static bool ReadJsonFile(const std::wstring& path, tip_json::Value& value) {
    FILE* f = nullptr;
    if (_wfopen_s(&f, path.c_str(), L"rb") || !f) return false;
    std::string bytes;
    char buf[4096];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) != 0) bytes.append(buf, n);
    fclose(f);
    if (bytes.compare(0, 3, "\xEF\xBB\xBF") == 0) bytes.erase(0, 3);
    return tip_json::Parser(bytes).Parse(value) && value.kind == tip_json::Value::Object;
}

// %USERPROFILE%\.yuragi-ime\tip.json (optional):
//   {"toggle_vk":192,"toggle_mods":["alt"],"log":false,"log_text":false,"document_context":true}
struct TipConfig {
    UINT toggle_vk = VK_OEM_3;
    unsigned toggle_mods = 4;  // shift=1, ctrl=2, alt=4, win=8
    bool log = false, log_text = false;
    bool document_context = true;
    void Load() {
        wchar_t profile[MAX_PATH];
        DWORD n = GetEnvironmentVariableW(L"USERPROFILE", profile, MAX_PATH);
        if (!n || n >= MAX_PATH) return;
        tip_json::Value v;
        if (!ReadJsonFile(std::wstring(profile) + L"\\.yuragi-ime\\tip.json", v)) return;
        int vk;
        if (tip_logic::ReadInt(v, "toggle_vk", vk) && vk > 0 && vk < 256) toggle_vk = (UINT)vk;
        const auto& mods = v.Get("toggle_mods");
        if (mods.kind == tip_json::Value::Array) {
            unsigned mask = 0;
            bool valid = true;
            for (const auto& m : mods.array) {
                if (m.text == "shift") mask |= 1;
                else if (m.text == "ctrl") mask |= 2;
                else if (m.text == "alt") mask |= 4;
                else if (m.text == "win") mask |= 8;
                else valid = false;
            }
            if (valid) toggle_mods = mask;
        }
        tip_logic::ReadBool(v, "log", log);
        tip_logic::ReadBool(v, "log_text", log_text);
        tip_logic::ReadBool(v, "document_context", document_context);
    }
};

// -- the broker: whether this process may start it (DESIGN「ブローカーを起動する条件」) --------------------------

static std::wstring PipeName() {
    std::wstring name = L"\\\\.\\pipe\\yuragi-ime-";
    HANDLE token = nullptr;
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) {
        DWORD size = 0;
        GetTokenInformation(token, TokenUser, nullptr, 0, &size);
        std::vector<BYTE> buffer(size);
        if (GetTokenInformation(token, TokenUser, buffer.data(), size, &size)) {
            LPWSTR sid = nullptr;
            if (ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(buffer.data())->User.Sid, &sid)) {
                name += sid;
                LocalFree(sid);
            }
        }
        CloseHandle(token);
    }
    DWORD session = 0;
    ProcessIdToSessionId(GetCurrentProcessId(), &session);
    return name + L"-" + std::to_wstring(session);
}

static bool TagMatches() {
    wchar_t value[128];
    DWORD size = sizeof value;
    if (RegGetValueW(HKEY_CURRENT_USER, kProductKey, L"Tag", RRF_RT_REG_SZ, nullptr, value, &size) !=
        ERROR_SUCCESS)
        return false;
    return Utf8ToWide(YURAGI_TAG) == value;
}

static bool MaintenanceActive() {
    HANDLE mutex = OpenMutexW(SYNCHRONIZE, FALSE, kMaintenanceMutex);
    if (!mutex) return false;
    CloseHandle(mutex);
    return true;
}

// Medium integrity exactly, and not an app container: neither sandboxed (it
// could not read the dictionary) nor elevated (the broker must not run as admin).
static bool MediumIntegrity() {
    HANDLE token = nullptr;
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) return false;
    bool medium = false;
    DWORD container = 0, size = sizeof container;
    bool app_container = GetTokenInformation(token, TokenIsAppContainer, &container, size, &size) &&
                         container;
    size = 0;
    GetTokenInformation(token, TokenIntegrityLevel, nullptr, 0, &size);
    std::vector<BYTE> buffer(size);
    if (!app_container &&
        GetTokenInformation(token, TokenIntegrityLevel, buffer.data(), size, &size)) {
        auto label = reinterpret_cast<TOKEN_MANDATORY_LABEL*>(buffer.data());
        DWORD rid = *GetSidSubAuthority(label->Label.Sid,
                                        *GetSidSubAuthorityCount(label->Label.Sid) - 1);
        medium = rid >= SECURITY_MANDATORY_MEDIUM_RID && rid < SECURITY_MANDATORY_HIGH_RID;
    }
    CloseHandle(token);
    return medium;
}

// Whether this process may start the broker (DESIGN「ブローカーを起動する条件」).
static bool MaySpawn() {
    tip_logic::SpawnFacts facts;
    facts.tag_matches = TagMatches();
    facts.maintenance = MaintenanceActive();
    facts.medium_integrity = MediumIntegrity();
    return tip_logic::MaySpawn(facts);
}

// The broker beside this DLL (Program Files: nobody else can replace it),
// away from the application's job, with no handles and the user's default
// environment. A failure is not retried here (DESIGN「ブローカーを起動する条件」).
static bool SpawnBroker() {
    std::wstring exe = DllDir() + L"\\yuragi-broker.exe";
    std::wstring command = L"\"" + exe + L"\"";
    LPVOID environment = nullptr;
    HANDLE token = nullptr;
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY | TOKEN_DUPLICATE, &token)) {
        CreateEnvironmentBlock(&environment, token, FALSE);
        CloseHandle(token);
    }
    STARTUPINFOW si = {};
    si.cb = sizeof si;
    PROCESS_INFORMATION pi = {};
    std::wstring dir = DllDir();
    BOOL made = CreateProcessW(exe.c_str(), command.data(), nullptr, nullptr, FALSE,
                               CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB |
                                   CREATE_UNICODE_ENVIRONMENT,
                               environment, dir.c_str(), &si, &pi);
    DWORD error = made ? 0 : GetLastError();
    if (environment) DestroyEnvironmentBlock(environment);
    if (!made) {
        Log(L"broker not started (error %lu)", error);
        return false;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    Log(L"broker started");
    return true;
}

// -- the connection (DESIGN「接続」) ----------------------------------------------------------

// One pipe and one reader thread per Tip. The thread waits for the pipe, the
// stop signal and the connect signal, and polls only while it waits for a pipe
// to appear (Open). Each line read is queued and the TIP's window is told;
// writes come from the UI thread.
class BrokerLink {
public:
    struct Item {
        enum Kind { Line, Connected, Lost, Unavailable, Connecting } kind;
        std::string line;
        Link link = Link::Connected;
    };

    BrokerLink() = default;
    ~BrokerLink() { Stop(); }

    void Start(HWND notify, UINT message) {
        notify_ = notify;
        message_ = message;
        name_ = PipeName();
        stop_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        connect_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        arrived_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        write_done_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        thread_ = std::thread([this] { Run(); });
    }
    void Stop() {
        if (!thread_.joinable()) return;
        SetEvent(stop_);
        thread_.join();
        for (HANDLE h : {stop_, connect_, arrived_, write_done_}) CloseHandle(h);
        stop_ = connect_ = arrived_ = write_done_ = nullptr;
    }
    // Neither connected nor trying: only then does a connect signal start an attempt,
    // so no signal is left behind to start another one right after (DESIGN「接続」).
    bool Idle() const { return idle_; }
    void RequestConnect() {
        idle_ = false;
        SetEvent(connect_);
    }
    bool Connected() {
        std::lock_guard<std::mutex> lock(pipe_lock_);
        return pipe_ != INVALID_HANDLE_VALUE;
    }
    HANDLE Arrived() const { return arrived_; }

    // From the UI thread, bounded: a write that does not finish in budget_ms
    // is cancelled and reported as failed (that key passes through).
    bool Write(const std::string& line, DWORD budget_ms) {
        std::lock_guard<std::mutex> lock(pipe_lock_);
        if (pipe_ == INVALID_HANDLE_VALUE) return false;
        return WriteTo(pipe_, write_done_, line, budget_ms);
    }

    bool Pop(Item& item) {
        std::lock_guard<std::mutex> lock(queue_lock_);
        if (queue_.empty()) return false;
        item = std::move(queue_.front());
        queue_.pop_front();
        return true;
    }

private:
    static bool WriteTo(HANDLE pipe, HANDLE done, const std::string& line, DWORD budget_ms) {
        std::string data = line + "\n";
        OVERLAPPED ov = {};
        ResetEvent(done);
        ov.hEvent = done;
        DWORD written = 0;
        if (!WriteFile(pipe, data.data(), (DWORD)data.size(), nullptr, &ov)) {
            if (GetLastError() != ERROR_IO_PENDING) return false;
            if (WaitForSingleObject(done, budget_ms) != WAIT_OBJECT_0) {
                CancelIoEx(pipe, &ov);
                GetOverlappedResult(pipe, &ov, &written, TRUE);
                return false;
            }
        }
        return GetOverlappedResult(pipe, &ov, &written, FALSE) && written == data.size();
    }

    void Push(Item item) {
        {
            std::lock_guard<std::mutex> lock(queue_lock_);
            queue_.push_back(std::move(item));
        }
        SetEvent(arrived_);
        PostMessageW(notify_, message_, 0, 0);
    }

    bool Stopping() { return WaitForSingleObject(stop_, 0) == WAIT_OBJECT_0; }

    void Run() {
        for (;;) {
            HANDLE waits[] = {stop_, connect_};
            if (WaitForMultipleObjects(2, waits, FALSE, INFINITE) != WAIT_OBJECT_0 + 1) return;
            Link why = Link::Unreachable;
            HANDLE pipe = Open(why);
            if (pipe == INVALID_HANDLE_VALUE) {
                if (Stopping()) return;
                idle_ = true;
                Push({Item::Unavailable, {}, why});
                continue;
            }
            // The hello goes first; only then may the UI thread write (keys).
            HANDLE hello_done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
            bool greeted = WriteTo(pipe, hello_done, tip_logic::Hello(),
                                   tip_logic::KEY_BUDGET_MS);
            CloseHandle(hello_done);
            if (!greeted) {
                CloseHandle(pipe);
                idle_ = true;
                Push({Item::Unavailable, {}, Link::Unreachable});
                continue;
            }
            {
                std::lock_guard<std::mutex> lock(pipe_lock_);
                pipe_ = pipe;
            }
            Push({Item::Connected, {}, Link::Connected});
            Read(pipe);
            Close();
            if (Stopping()) return;
            idle_ = true;
            Push({Item::Lost, {}, Link::Connecting});
        }
    }

    void Close() {
        std::lock_guard<std::mutex> lock(pipe_lock_);
        if (pipe_ != INVALID_HANDLE_VALUE) CloseHandle(pipe_);
        pipe_ = INVALID_HANDLE_VALUE;
    }

    // The pipe; when there is none, maybe start the broker (DESIGN「ブローカーを起動する条件」) and wait for
    // its pipe at most BROKER_WAIT_MS, looking every BROKER_POLL_MS.
    HANDLE Open(Link& why) {
        bool spawned = false;
        ULONGLONG deadline = 0;
        for (;;) {
            HANDLE pipe = CreateFileW(name_.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                                      OPEN_EXISTING, FILE_FLAG_OVERLAPPED, nullptr);
            if (pipe != INVALID_HANDLE_VALUE) return pipe;
            DWORD error = GetLastError();
            if (error == ERROR_ACCESS_DENIED) {
                why = Link::NotAllowed;  // e.g. a sandbox the pipe does not admit (DESIGN「通信」)
                return INVALID_HANDLE_VALUE;
            }
            if (error != ERROR_FILE_NOT_FOUND && error != ERROR_PIPE_BUSY) {
                why = Link::Unreachable;
                return INVALID_HANDLE_VALUE;
            }
            if (error == ERROR_FILE_NOT_FOUND && !spawned) {
                if (!MaySpawn()) {
                    why = Link::NotAllowed;
                    return INVALID_HANDLE_VALUE;
                }
                if (!SpawnBroker()) {
                    why = Link::Unreachable;
                    return INVALID_HANDLE_VALUE;
                }
                spawned = true;
                deadline = GetTickCount64() + tip_logic::BROKER_WAIT_MS;
                Push({Item::Connecting, {}, Link::Connecting});
            }
            if (!spawned) deadline = deadline ? deadline : GetTickCount64() + tip_logic::BROKER_WAIT_MS;
            if (GetTickCount64() >= deadline) {
                why = Link::Unreachable;
                return INVALID_HANDLE_VALUE;
            }
            if (WaitForSingleObject(stop_, tip_logic::BROKER_POLL_MS) == WAIT_OBJECT_0)
                return INVALID_HANDLE_VALUE;
        }
    }

    void Read(HANDLE pipe) {
        HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        std::string buffer;
        char chunk[16384];
        for (;;) {
            OVERLAPPED ov = {};
            ov.hEvent = done;
            ResetEvent(done);
            DWORD n = 0;
            if (!ReadFile(pipe, chunk, sizeof chunk, nullptr, &ov) && GetLastError() != ERROR_IO_PENDING)
                break;
            HANDLE waits[] = {stop_, done};
            if (WaitForMultipleObjects(2, waits, FALSE, INFINITE) == WAIT_OBJECT_0) {
                CancelIoEx(pipe, &ov);
                GetOverlappedResult(pipe, &ov, &n, TRUE);
                break;
            }
            if (!GetOverlappedResult(pipe, &ov, &n, FALSE) || n == 0) break;
            buffer.append(chunk, n);
            size_t start = 0;
            for (size_t nl; (nl = buffer.find('\n', start)) != std::string::npos; start = nl + 1)
                Push({Item::Line, buffer.substr(start, nl - start), Link::Connected});
            buffer.erase(0, start);
        }
        CloseHandle(done);
    }

    HWND notify_ = nullptr;
    UINT message_ = 0;
    std::wstring name_;
    HANDLE stop_ = nullptr, connect_ = nullptr, arrived_ = nullptr, write_done_ = nullptr;
    std::mutex pipe_lock_, queue_lock_;
    HANDLE pipe_ = INVALID_HANDLE_VALUE;
    std::deque<Item> queue_;
    std::atomic<bool> idle_{true};
    std::thread thread_;
};

// -- display attributes ----------------------------------------------------------------

// Three published display attributes: raw input, converted, focused bunsetsu.
static const GUID kAttributeGuids[] = {
    {0xa7c4e203, 0x0b3a, 0x4f11, {0x9e,0x61,0x0c,0x1a,0x0b,0x7e,0x0a,0x01}},
    {0xa7c4e204, 0x0b3a, 0x4f11, {0x9e,0x61,0x0c,0x1a,0x0b,0x7e,0x0a,0x01}},
    {0xa7c4e205, 0x0b3a, 0x4f11, {0x9e,0x61,0x0c,0x1a,0x0b,0x7e,0x0a,0x01}},
};
static TF_DISPLAYATTRIBUTE DefaultAttribute(int index) {
    TF_DISPLAYATTRIBUTE a{};
    a.crText.type = TF_CT_NONE; a.crBk.type = TF_CT_NONE;
    a.crLine.type = TF_CT_NONE;
    a.lsStyle = index == 0 ? TF_LS_DOT : TF_LS_SOLID;
    a.fBoldLine = index == 2;
    a.bAttr = index == 0 ? TF_ATTR_INPUT : (index == 1 ? TF_ATTR_CONVERTED : TF_ATTR_TARGET_CONVERTED);
    return a;
}
class AttributeInfo final : public ITfDisplayAttributeInfo {
    LONG refs_ = 1;
    int index_;
    TF_DISPLAYATTRIBUTE attribute_;
public:
    explicit AttributeInfo(int i) : index_(i), attribute_(DefaultAttribute(i)) { InterlockedIncrement(&g_locks); }
    ~AttributeInfo() { InterlockedDecrement(&g_locks); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** pp) override {
        if (!pp) return E_POINTER;
        *pp = nullptr;
        if (id != IID_IUnknown && id != IID_ITfDisplayAttributeInfo) return E_NOINTERFACE;
        *pp = static_cast<ITfDisplayAttributeInfo*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n = InterlockedDecrement(&refs_); if (!n) delete this; return n;
    }
    HRESULT STDMETHODCALLTYPE GetGUID(GUID* g) override {
        if (!g) return E_POINTER; *g = kAttributeGuids[index_]; return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetDescription(BSTR* b) override {
        if (!b) return E_POINTER;
        const wchar_t* names[] = {L"yuragi input", L"yuragi converted", L"yuragi focused segment"};
        *b = SysAllocString(names[index_]); return *b ? S_OK : E_OUTOFMEMORY;
    }
    HRESULT STDMETHODCALLTYPE GetAttributeInfo(TF_DISPLAYATTRIBUTE* a) override {
        if (!a) return E_POINTER; *a = attribute_; return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetAttributeInfo(const TF_DISPLAYATTRIBUTE* a) override {
        if (!a) return E_POINTER; attribute_ = *a; return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Reset() override { attribute_ = DefaultAttribute(index_); return S_OK; }
};
class AttributeEnum final : public IEnumTfDisplayAttributeInfo {
    LONG refs_ = 1;
    ULONG index_ = 0;
public:
    AttributeEnum() { InterlockedIncrement(&g_locks); }
    ~AttributeEnum() { InterlockedDecrement(&g_locks); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** pp) override {
        if (!pp) return E_POINTER;
        *pp = nullptr;
        if (id != IID_IUnknown && id != IID_IEnumTfDisplayAttributeInfo) return E_NOINTERFACE;
        *pp = static_cast<IEnumTfDisplayAttributeInfo*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n = InterlockedDecrement(&refs_); if (!n) delete this; return n;
    }
    HRESULT STDMETHODCALLTYPE Clone(IEnumTfDisplayAttributeInfo** pp) override {
        if (!pp) return E_POINTER;
        auto* e = new AttributeEnum(); e->index_ = index_; *pp = e; return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Next(ULONG count, ITfDisplayAttributeInfo** infos, ULONG* fetched) override {
        if (!infos || (!fetched && count != 1)) return E_POINTER;
        ULONG n = 0;
        while (n < count && index_ < 3) infos[n++] = new AttributeInfo((int)index_++);
        if (fetched) *fetched = n;
        return n == count ? S_OK : S_FALSE;
    }
    HRESULT STDMETHODCALLTYPE Reset() override { index_ = 0; return S_OK; }
    HRESULT STDMETHODCALLTYPE Skip(ULONG count) override {
        ULONG n = (std::min)(count, 3UL - index_); index_ += n;
        return n == count ? S_OK : S_FALSE;
    }
};

// -- the input field's kind (DESIGN「パスワード欄」) -------------------------------------------------

static tip_logic::Scope FieldScope(ITfContext* ctx, TfEditCookie ec, ITfRange* range) {
    using tip_logic::Scope;
    Scope kind = Scope::Unavailable;
    ITfReadOnlyProperty* prop = nullptr;
    HRESULT property_hr = ctx->GetAppProperty(GUID_PROP_INPUTSCOPE, &prop);
    if (property_hr == S_FALSE) return Scope::Allowed;
    if (property_hr == S_OK) {
        VARIANT v;
        VariantInit(&v);
        HRESULT hr = prop->GetValue(ec, range, &v);
        if (SUCCEEDED(hr) && v.vt == VT_EMPTY) {
            kind = Scope::Allowed;
        } else if (SUCCEEDED(hr) && v.vt == VT_UNKNOWN && v.punkVal) {
            ITfInputScope* scope = nullptr;
            if (SUCCEEDED(v.punkVal->QueryInterface(IID_ITfInputScope, (void**)&scope))) {
                InputScope* scopes = nullptr;
                UINT count = 0;
                if (SUCCEEDED(scope->GetInputScopes(&scopes, &count))) {
                    kind = Scope::Allowed;
                    for (UINT i = 0; i < count; ++i)
                        if (scopes[i] == IS_PASSWORD || scopes[i] == IS_NUMERIC_PASSWORD)
                            kind = Scope::Password;
                }
                CoTaskMemFree(scopes);
                scope->Release();
            }
        }
        VariantClear(&v);
        prop->Release();
    }
    return kind;
}

static tip_logic::Scope SelectionScope(ITfContext* ctx, TfEditCookie ec) {
    TF_SELECTION selection{};
    ULONG fetched = 0;
    if (FAILED(ctx->GetSelection(ec, TF_DEFAULT_SELECTION, 1, &selection, &fetched)) || !fetched)
        return tip_logic::Scope::Unavailable;
    auto scope = FieldScope(ctx, ec, selection.range);
    selection.range->Release();
    return scope;
}

// -- composition and its edits ------------------------------------------------------

struct CompositionState {
    ITfContext* ctx;
    ITfComposition* composition = nullptr;
    ITfRange* commit_end = nullptr;
    long long commit_seq = 0;
    long long applied_seq = 0;
    bool track_commit;
    bool disconnected = false;
    bool active = true, ending = false, position_pending = false, show_candidates = false;
    std::vector<Message> pending;
    CompositionState(ITfContext* c, bool track)
        : ctx(c), track_commit(track), disconnected(track) { ctx->AddRef(); }
    ~CompositionState() {
        if (commit_end) commit_end->Release();
        if (composition) composition->Release();
        ctx->Release();
    }
    void BreakContinuity() {
        if (commit_end) commit_end->Release();
        commit_end = nullptr;
        commit_seq = 0;
        disconnected = true;
    }
};

// Python's display offsets count code points; TSF ranges count UTF-16 units.
static LONG Utf16Offset(const std::wstring& text, int codepoints) {
    size_t i = 0;
    for (int n = 0; n < codepoints && i < text.size(); ++n) {
        wchar_t c = text[i++];
        if (c >= 0xd800 && c <= 0xdbff && i < text.size() &&
            text[i] >= 0xdc00 && text[i] <= 0xdfff) ++i;
    }
    return (LONG)i;
}

// Read the caret under an edit cookie; hide the popup when the text is not laid out.
static void PlacePopup(TfEditCookie ec, ITfContext* ctx, ITfRange* caret, TipPopup& popup,
                       bool log_candidates = false) {
    if (!popup.HasRows()) return;
    ITfContextView* view = nullptr;
    bool positioned = false;
    if (SUCCEEDED(ctx->GetActiveView(&view))) {
        RECT rect{};
        BOOL clipped = FALSE;
        // S_OK with no height means the text is not visible. A collapsed caret
        // in Notepad can have zero width even when it is visible.
        if (SUCCEEDED(view->GetTextExt(ec, caret, &rect, &clipped)) && rect.bottom > rect.top) {
            bool first_show = log_candidates && !IsWindowVisible(popup.Window());
            positioned = popup.Place(rect, g_hinst);
            if (positioned && first_show)
                Log(L"candidate shown window=%p t=%llu", static_cast<void*>(popup.Window()), NowMs());
        }
        view->Release();
    }
    if (!positioned) popup.Hide();
}

using RetiredStates = std::vector<std::shared_ptr<CompositionState>>;
static constexpr UINT kKeysMessage = WM_APP + 2;

class EditSession final : public ITfEditSession {
public:
    enum Kind { Apply, Finalize, Position };
    EditSession(Kind kind, std::shared_ptr<CompositionState> state, ITfCompositionSink* sink,
                const TfGuidAtom* atoms, TipPopup& candidate, RetiredStates* retired, HWND keys)
        : kind_(kind), state_(std::move(state)), sink_(sink), candidate_(candidate), retired_(retired),
          keys_(keys) {
        sink_->AddRef();
        for (int i = 0; i < 3; ++i) atoms_[i] = atoms[i];
    }
    ~EditSession() {
        if (kind_ == Position) state_->position_pending = false;
        sink_->Release();
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** pp) override {
        if (!pp) return E_POINTER;
        *pp = nullptr;
        if (riid != IID_IUnknown && riid != IID_ITfEditSession) return E_NOINTERFACE;
        *pp = static_cast<ITfEditSession*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n = InterlockedDecrement(&refs_); if (!n) delete this; return n;
    }

    HRESULT STDMETHODCALLTYPE DoEditSession(TfEditCookie ec) override {
        if (kind_ == Position) {
            state_->position_pending = false;
            if (!state_->active || !state_->composition || !state_->show_candidates ||
                !candidate_.HasRows()) return S_OK;
            ITfRange* caret = nullptr;
            if (SUCCEEDED(state_->composition->GetRange(&caret))) {
                caret->Collapse(ec, TF_ANCHOR_END);
                PlacePopup(ec, state_->ctx, caret, candidate_, g_log);
                caret->Release();
            }
            return S_OK;
        }
        if (kind_ == Finalize) return FinalizeState(ec, state_);
        if (!state_->active) return S_OK;
        // Synchronous edits can overtake queued asynchronous cleanup: finish
        // the retired compositions of this context first (keeping their text).
        for (const auto& old : *retired_) {
            if (old->ctx == state_->ctx && old->composition) {
                HRESULT hr = FinalizeState(ec, old);
                if (FAILED(hr)) {
                    state_->BreakContinuity();
                    return hr;
                }
            }
        }
        retired_->erase(std::remove_if(retired_->begin(), retired_->end(),
            [](const std::shared_ptr<CompositionState>& old) { return !old->composition; }),
            retired_->end());
        std::vector<Message> pending;
        pending.swap(state_->pending);
        for (const auto& r : pending) {
            if (!state_->active) break;
            // A converted phrase can commit and start the next composition in
            // the same reply. Apply both in order under the same edit cookie.
            HRESULT hr = S_OK;
            if (!r.commit.empty()) hr = Write(ec, Utf8ToWide(r.commit), true, r);
            if (SUCCEEDED(hr)) hr = Write(ec, Utf8ToWide(r.composition), false, r);
            state_->applied_seq = r.seq;
            PostMessageW(keys_, kKeysMessage, 0, 0);
            if (FAILED(hr)) {
                state_->BreakContinuity();
                return hr;
            }
        }
        return S_OK;
    }

private:
    HRESULT End(TfEditCookie ec, const std::shared_ptr<CompositionState>& state) {
        if (!state->composition) return S_OK;
        state->ending = true;
        ITfComposition* comp = state->composition;
        state->composition = nullptr;
        HRESULT hr = comp->EndComposition(ec);
        comp->Release();
        state->ending = false;
        return hr;
    }
    // DESIGN「見えている文字の確定」: the text stays as shown; only the conversion ends.
    HRESULT FinalizeState(TfEditCookie ec, const std::shared_ptr<CompositionState>& state) {
        if (!state->composition) return S_OK;
        ITfRange* range = nullptr;
        HRESULT hr = state->composition->GetRange(&range);
        if (SUCCEEDED(hr)) {
            ITfProperty* prop = nullptr;
            if (SUCCEEDED(state->ctx->GetProperty(GUID_PROP_ATTRIBUTE, &prop))) {
                prop->Clear(ec, range);
                prop->Release();
            }
            range->Release();
        }
        return End(ec, state);
    }
    void Attribute(TfEditCookie ec, ITfProperty* prop, ITfRange* range, TfGuidAtom atom) {
        if (atom == TF_INVALID_GUIDATOM) return;
        VARIANT v; VariantInit(&v); v.vt = VT_I4; v.lVal = (LONG)atom;
        prop->SetValue(ec, range, &v);
    }
    HRESULT Write(TfEditCookie ec, const std::wstring& text, bool commit, const Message& reply) {
        if (commit) state_->BreakContinuity();
        ITfContext* ctx = state_->ctx;
        ITfRange* range = nullptr;
        HRESULT hr = S_OK;
        if (state_->composition) {
            hr = state_->composition->GetRange(&range);
            if (SUCCEEDED(hr)) hr = range->SetText(ec, 0, text.data(), (LONG)text.size());
        } else if (!text.empty()) {
            ITfInsertAtSelection* ins = nullptr;
            hr = ctx->QueryInterface(IID_ITfInsertAtSelection, (void**)&ins);
            if (SUCCEEDED(hr)) {
                // Acquire ownership before inserting preedit. StartComposition
                // can return S_OK with a null composition when the app rejects it.
                hr = commit ? ins->InsertTextAtSelection(ec, 0, text.data(), (LONG)text.size(), &range) :
                              ins->InsertTextAtSelection(ec, TF_IAS_QUERYONLY, L"", 0, &range);
                ins->Release();
            }
            if (SUCCEEDED(hr) && range && !commit) {
                ITfContextComposition* cc = nullptr;
                hr = ctx->QueryInterface(IID_ITfContextComposition, (void**)&cc);
                if (SUCCEEDED(hr)) {
                    hr = cc->StartComposition(ec, range, sink_, &state_->composition);
                    cc->Release();
                    if (SUCCEEDED(hr)) {
                        hr = state_->composition ?
                            range->SetText(ec, 0, text.data(), (LONG)text.size()) : E_FAIL;
                    }
                }
            }
        }
        if (FAILED(hr) || !range) {
            if (range) range->Release();
            return commit && SUCCEEDED(hr) ? E_FAIL : hr;
        }
        const bool editing = !commit && reply.phase == tip_logic::Phase::Editing &&
                             reply.focus >= 0 && (size_t)reply.focus < reply.segments.size();
        ITfProperty* prop = nullptr;
        if (SUCCEEDED(ctx->GetProperty(GUID_PROP_ATTRIBUTE, &prop))) {
            prop->Clear(ec, range);
            if (!commit && !text.empty()) {
                Attribute(ec, prop, range, atoms_[reply.converted ? 1 : 0]);
                for (size_t i = 0; i < reply.segments.size(); ++i) {
                    const auto& seg = reply.segments[i];
                    LONG start = Utf16Offset(text, seg.display_start);
                    LONG end = Utf16Offset(text, seg.display_end);
                    ITfRange* part = nullptr;
                    if (SUCCEEDED(range->Clone(&part))) {
                        LONG moved = 0;
                        part->Collapse(ec, TF_ANCHOR_START);
                        part->ShiftEnd(ec, end, &moved, nullptr);
                        part->ShiftStart(ec, start, &moved, nullptr);
                        const bool focused = (int)i == reply.focus;
                        int attribute = reply.converted && !(focused && editing) ? (focused ? 2 : 1) : 0;
                        Attribute(ec, prop, part, atoms_[attribute]);
                        part->Release();
                    }
                }
            }
            prop->Release();
        }
        ITfRange* caret = nullptr;
        HRESULT caret_hr = range->Clone(&caret);
        int caret_position = commit ? reply.commit_caret : reply.caret;
        if (caret_position < 0 && editing) caret_position = reply.segments[reply.focus].display_end;
        if (SUCCEEDED(caret_hr)) {
            caret_hr = caret->Collapse(ec, caret_position >= 0 ? TF_ANCHOR_START : TF_ANCHOR_END);
            if (SUCCEEDED(caret_hr) && caret_position > 0) {
                LONG moved = 0;
                LONG offset = Utf16Offset(text, caret_position);
                caret_hr = caret->ShiftEnd(ec, offset, &moved, nullptr);
                if (SUCCEEDED(caret_hr)) caret_hr = caret->Collapse(ec, TF_ANCHOR_END);
            }
        }
        if (SUCCEEDED(caret_hr)) {
            TF_SELECTION selection{};
            selection.range = caret; selection.style.ase = TF_AE_NONE;
            caret_hr = ctx->SetSelection(ec, 1, &selection);
            if (!commit && reply.ShowsCandidates())
                PlacePopup(ec, ctx, caret, candidate_, g_log);
        }
        if (commit || text.empty()) hr = End(ec, state_);
        if (FAILED(caret_hr)) {
            state_->BreakContinuity();
        } else if (commit && caret_position < 0 && SUCCEEDED(hr) && state_->active) {
            // A commit in the middle keeps the document context disconnected:
            // its caret is not the end of the text we committed.
            state_->disconnected = false;
            if (state_->track_commit) {
                // The next preedit can be inserted at this position in this same edit.
                if (SUCCEEDED(caret->SetGravity(ec, TF_GRAVITY_BACKWARD, TF_GRAVITY_BACKWARD))) {
                    state_->commit_end = caret;
                    state_->commit_seq = reply.seq;
                    caret = nullptr;
                } else {
                    state_->BreakContinuity();
                }
            }
        }
        if (caret) caret->Release();
        range->Release();
        return hr;
    }

    LONG refs_ = 1;
    Kind kind_;
    std::shared_ptr<CompositionState> state_;
    ITfCompositionSink* sink_;
    TfGuidAtom atoms_[3];
    TipPopup& candidate_;
    RetiredStates* retired_;
    HWND keys_;
};

// -- the taskbar glyph (DESIGN「状態」) --------------------------------------------------------

// The taskbar input indicator (Windows 8+) shows only an item whose guidItem
// is GUID_LBI_INPUTMODE, drawn from its icon. The DLL has no icon resource,
// so the glyph is rendered at run time in the taskbar's foreground colour.
static bool TaskbarIsLight() {
    DWORD value = 0, size = sizeof(value);
    return RegGetValueW(HKEY_CURRENT_USER,
               L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
               L"SystemUsesLightTheme", RRF_RT_REG_DWORD, nullptr, &value, &size) == ERROR_SUCCESS
           && value != 0;
}
// Sized for the taskbar's scale, not this application's: in a DPI-unaware application
// GetSystemMetrics answers at 96 dpi (16 px) while a 150 % taskbar shows 24 px.
static HICON MakeModeIcon(const wchar_t* glyph, bool faint) {
    UINT dpi = GetDpiForWindow(FindWindowW(L"Shell_TrayWnd", nullptr));
    int cx = GetSystemMetricsForDpi(SM_CXSMICON, dpi), cy = GetSystemMetricsForDpi(SM_CYSMICON, dpi);
    BITMAPINFO bi{};
    bi.bmiHeader.biSize = sizeof(bi.bmiHeader);
    bi.bmiHeader.biWidth = cx; bi.bmiHeader.biHeight = -cy;
    bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32; bi.bmiHeader.biCompression = BI_RGB;
    void* bits = nullptr;
    HDC screen = GetDC(nullptr);
    HDC dc = CreateCompatibleDC(screen);
    HBITMAP color = CreateDIBSection(screen, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    ReleaseDC(nullptr, screen);
    if (!dc || !color || !bits) {
        if (color) DeleteObject(color);
        if (dc) DeleteDC(dc);
        return nullptr;
    }
    HGDIOBJ old_bmp = SelectObject(dc, color);
    // White glyph on black; its grey level becomes the alpha below. The font is as tall
    // as the icon; the glyph is drawn once to find its ink, then again centred on the
    // ink (centring the text line leaves it small and low, the line has leading).
    HFONT font = CreateFontW(-cy, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                             DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                             ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Yu Gothic UI");
    HGDIOBJ old_font = SelectObject(dc, font);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(255, 255, 255));
    auto draw = [&](int dx, int dy) {
        memset(bits, 0, (size_t)cx * cy * 4);
        RECT rc{dx, dy, cx + dx, cy + dy};
        DrawTextW(dc, glyph, -1, &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
        GdiFlush();
    };
    draw(0, 0);
    int left = cx, top = cy, right = -1, bottom = -1;
    const BYTE* ink = static_cast<const BYTE*>(bits);
    for (int y = 0; y < cy; ++y)
        for (int x = 0; x < cx; ++x, ink += 4)
            if (ink[0] | ink[1] | ink[2]) {
                left = (std::min)(left, x); right = (std::max)(right, x);
                top = (std::min)(top, y); bottom = (std::max)(bottom, y);
            }
    if (right >= 0) draw((cx - 1 - right - left) / 2, (cy - 1 - bottom - top) / 2);
    SelectObject(dc, old_font);
    DeleteObject(font);
    SelectObject(dc, old_bmp);
    DeleteDC(dc);
    BYTE fg = TaskbarIsLight() ? 0 : 255;
    auto* px = static_cast<BYTE*>(bits);
    for (int i = 0; i < cx * cy; ++i, px += 4) {
        BYTE a = (std::max)(px[0], (std::max)(px[1], px[2]));
        if (faint) a = (BYTE)(a * 2 / 5);  // "ゆ" drawn faint while preparing
        px[0] = px[1] = px[2] = fg; px[3] = a;
    }
    HBITMAP mask = CreateBitmap(cx, cy, 1, 1, nullptr);
    ICONINFO ii{};
    ii.fIcon = TRUE; ii.hbmColor = color; ii.hbmMask = mask;
    HICON icon = mask ? CreateIconIndirect(&ii) : nullptr;
    if (mask) DeleteObject(mask);
    DeleteObject(color);
    return icon;
}

// -- the one-line notice (DESIGN「小さな表示」) ------------------------------------------------------

static const wchar_t* NoticeText(Notice n) {
    switch (n) {
        case Notice::Stopped: return L"日本語変換が止まっています。タスクバーの「!」を右クリックしてください";
        case Notice::None: break;
    }
    return L"";
}

class ReadSession;

class Tip final : public ITfTextInputProcessorEx,
            public ITfKeyEventSink,
            public ITfThreadMgrEventSink,
            public ITfCompositionSink,
            public ITfDisplayAttributeProvider,
            public ITfLangBarItemButton,
            public ITfSource,
            public ITfTextLayoutSink,
            public ITfTextEditSink {
    enum class Action { Pass, Send, ObserveAlt, Global, Buffer };
    enum class SendResult { Sent, Unavailable, FocusMoved };
    enum class ReplayResult { Sent, Retry, FocusMoved, Foreground, Failed };
    struct Decision {
        Action action = Action::Pass;
        tip_logic::GlobalCommand command = tip_logic::GlobalCommand::None;
        bool Eats() const { return action == Action::Send || action == Action::Global || action == Action::Buffer; }
    };
    struct Stroke {
        UINT raw;
        LPARAM flags;
        LONG message_time;
        ULONGLONG time;
        tip_logic::Chord chord;
        bool down;
        bool windows_only = false;
        bool preserved = false;
    };
    struct TestedKey { Stroke key; Decision decision; uint64_t generation; };
    struct SentKey {
        Stroke key;
        long long replay_after = 0;
        std::optional<tip_logic::GlobalCommand> run_after;
    };
    struct Registration { GUID guid; TF_PRESERVEDKEY key; unsigned code; };
    static constexpr LPARAM kReplayMarker = 0x59555247; // YURG, in KEYBDINPUT.dwExtraInfo

public:
    Tip() { InterlockedIncrement(&g_locks); }
    ~Tip() { InterlockedDecrement(&g_locks); }

    // -- IUnknown -----------------------------------------------------------------
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** pp) override {
        if (!pp) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_ITfTextInputProcessor ||
            riid == IID_ITfTextInputProcessorEx) {
            *pp = static_cast<ITfTextInputProcessorEx*>(this);
        } else if (riid == IID_ITfKeyEventSink) {
            *pp = static_cast<ITfKeyEventSink*>(this);
        } else if (riid == IID_ITfThreadMgrEventSink) {
            *pp = static_cast<ITfThreadMgrEventSink*>(this);
        } else if (riid == IID_ITfCompositionSink) {
            *pp = static_cast<ITfCompositionSink*>(this);
        } else if (riid == IID_ITfDisplayAttributeProvider) {
            *pp = static_cast<ITfDisplayAttributeProvider*>(this);
        } else if (riid == IID_ITfLangBarItem || riid == IID_ITfLangBarItemButton) {
            *pp = static_cast<ITfLangBarItemButton*>(this);
        } else if (riid == IID_ITfSource) {
            *pp = static_cast<ITfSource*>(this);
        } else if (riid == IID_ITfTextLayoutSink) {
            *pp = static_cast<ITfTextLayoutSink*>(this);
        } else if (riid == IID_ITfTextEditSink) {
            *pp = static_cast<ITfTextEditSink*>(this);
        } else {
            *pp = nullptr;
            return E_NOINTERFACE;
        }
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n = InterlockedDecrement(&refs_);
        if (!n) delete this;
        return n;
    }

    // -- activation -----------------------------------------------------------------
    HRESULT STDMETHODCALLTYPE Activate(ITfThreadMgr* ptim, TfClientId tid) override {
        return ActivateEx(ptim, tid, 0);
    }
    HRESULT STDMETHODCALLTYPE ActivateEx(ITfThreadMgr* ptim, TfClientId tid, DWORD) override {
        tm_ = ptim;
        tm_->AddRef();
        client_ = tid;
        settings_.Load();
        keymap_ = tip_logic::DefaultKeyTable();
        const unsigned toggle = settings_.toggle_vk | (settings_.toggle_mods << 8);
        constexpr unsigned default_toggle = VK_OEM_3 | (4 << 8);
        const auto mods = settings_.toggle_mods;
        if (toggle != default_toggle && !(mods & 8) && !tip_logic::ModifierVk(settings_.toggle_vk) &&
            !tip_logic::Typing({settings_.toggle_vk, {(mods & 1) != 0, (mods & 2) != 0, (mods & 4) != 0, false}})) {
            keymap_.rev.clear(); // the broker's copy takes precedence when received
            keymap_.global.erase(default_toggle);
            keymap_.global[toggle] = tip_logic::GlobalCommand::Toggle;
        }
        g_log = settings_.log;
        ITfSource* src = nullptr;
        if (SUCCEEDED(tm_->QueryInterface(IID_ITfSource, (void**)&src))) {
            src->AdviseSink(IID_ITfThreadMgrEventSink, (ITfThreadMgrEventSink*)this, &cookie_tm_);
            src->Release();
        }
        ITfKeystrokeMgr* km = nullptr;
        if (SUCCEEDED(tm_->QueryInterface(IID_ITfKeystrokeMgr, (void**)&km))) {
            km->AdviseKeyEventSink(client_, this, TRUE);
            km->Release();
        }
        ITfCategoryMgr* cat = nullptr;
        if (SUCCEEDED(CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
                                       IID_ITfCategoryMgr, (void**)&cat))) {
            for (int i = 0; i < 3; ++i) cat->RegisterGUID(kAttributeGuids[i], &atoms_[i]);
            cat->Release();
        }
        EnsureWindow();
        OpenKeyboard(tm_, client_);
        PreserveKeys();
        ITfLangBarItemMgr* lbm = nullptr;
        if (SUCCEEDED(tm_->QueryInterface(IID_ITfLangBarItemMgr, (void**)&lbm))) {
            if (SUCCEEDED(lbm->AddItem(this))) langbar_ = true;
            lbm->Release();
        }
        link_.Start(hwnd_, kLinkMessage);
        TryConnect();  // DESIGN「接続」: one of the four moments a connection is tried
        CheckScope();
        Log(L"ActivateEx client=%u", (unsigned)tid);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Deactivate() override {
        DropHeld(L"deactivate");
        tested_.reset();
        menu_generation_.reset();
        FinishLocal();
        link_.Stop();
        UnadviseLayout();
        UnadviseTextEdit();
        ++focus_generation_;
        KillTimer(hwnd_, kTimerNotice);
        candidate_.Destroy();
        notice_popup_.Destroy();
        if (hwnd_) DestroyWindow(hwnd_);
        hwnd_ = nullptr;
        if (scope_ctx_) {
            scope_ctx_->Release();
            scope_ctx_ = nullptr;
        }
        if (tm_) {
            if (langbar_) {
                ITfLangBarItemMgr* lbm = nullptr;
                if (SUCCEEDED(tm_->QueryInterface(IID_ITfLangBarItemMgr, (void**)&lbm))) {
                    lbm->RemoveItem(this);
                    lbm->Release();
                }
                langbar_ = false;
            }
            ITfKeystrokeMgr* km = nullptr;
            if (SUCCEEDED(tm_->QueryInterface(IID_ITfKeystrokeMgr, (void**)&km))) {
                UnpreserveKeys(km);
                km->UnadviseKeyEventSink(client_);
                km->Release();
            }
            ITfSource* src = nullptr;
            if (cookie_tm_ != TF_INVALID_COOKIE &&
                SUCCEEDED(tm_->QueryInterface(IID_ITfSource, (void**)&src))) {
                src->UnadviseSink(cookie_tm_);
                src->Release();
            }
            tm_->Release();
            tm_ = nullptr;
        }
        client_ = TF_CLIENTID_NULL;
        cookie_tm_ = TF_INVALID_COOKIE;
        return S_OK;
    }

    // -- focus ------------------------------------------------------------------------
    HRESULT STDMETHODCALLTYPE OnSetFocus(ITfDocumentMgr*, ITfDocumentMgr*) override {
        FocusMoved();
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnInitDocumentMgr(ITfDocumentMgr*) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnUninitDocumentMgr(ITfDocumentMgr*) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnPushContext(ITfContext*) override { FocusMoved(); return S_OK; }
    HRESULT STDMETHODCALLTYPE OnPopContext(ITfContext*) override { FocusMoved(); return S_OK; }
    HRESULT STDMETHODCALLTYPE OnSetFocus(BOOL) override { FocusMoved(); return S_OK; }

    // The application ended the composition (focus moved, etc.): its text is the app's now.
    HRESULT STDMETHODCALLTYPE OnCompositionTerminated(TfEditCookie, ITfComposition* c) override {
        if (state_ && !state_->ending && state_->composition == c) {
            state_->composition->Release();
            state_->composition = nullptr;
            FinishLocal();
            SendRequest("reset");
        }
        return S_OK;
    }

    // ITfTextLayoutSink (DESIGN「タイマー」): the candidate list follows the text.
    HRESULT STDMETHODCALLTYPE OnLayoutChange(ITfContext*, TfLayoutCode, ITfContextView*) override {
        RequestCandidatePosition();
        return S_OK;
    }

    HRESULT STDMETHODCALLTYPE OnEndEdit(ITfContext* ctx, TfEditCookie,
                                        ITfEditRecord* record) override {
        auto state = state_;
        if (!state || !state->commit_end || ctx != state->ctx) return S_OK;
        BOOL ours = FALSE;
        if (SUCCEEDED(ctx->InWriteSession(client_, &ours)) && ours) return S_OK;
        BOOL selection_changed = FALSE;
        if (FAILED(record->GetSelectionStatus(&selection_changed)) || selection_changed) {
            state->BreakContinuity();
            return S_OK;
        }
        IEnumTfRanges* changes = nullptr;
        HRESULT hr = record->GetTextAndPropertyUpdates(TF_GTP_INCL_TEXT, nullptr, 0, &changes);
        if (SUCCEEDED(hr)) {
            ITfRange* changed = nullptr;
            ULONG fetched = 0;
            hr = changes->Next(1, &changed, &fetched);
            if (changed) changed->Release();
            changes->Release();
        }
        if (hr != S_FALSE) state->BreakContinuity();
        return S_OK;
    }

    // -- keys (DESIGN「打鍵の処理」) ----------------------------------------------------------------------
    HRESULT STDMETHODCALLTYPE OnTestKeyDown(ITfContext*, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        auto key = ReadStroke(w, l);
        if (IsReplay(key)) { *e = FALSE; return S_OK; }
        bool tested = SameTest(key);
        auto decision = tested ? tested_->decision : Decide(key);
        if (!tested) {
            if (decision.action == Action::ObserveAlt) Buffer(key); // no pipe I/O in OnTestKeyDown
            tested_ = TestedKey{key, decision, focus_generation_};
            // IMM applications call OnKeyDown only for a key eaten here (keybind/windows.md §1.1).
            if (!decision.Eats() && Eligible() && ScopeAllowsInput()) Typed(key);
        }
        *e = decision.Eats() ? TRUE : FALSE;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnTestKeyUp(ITfContext*, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        auto key = ReadStroke(w, l, false);
        if (GetMessageExtraInfo() != kReplayMarker && !SameEvent(tested_up_, key))
            QueueRelease(key);
        tested_up_ = key;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnKeyDown(ITfContext* ctx, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        auto key = ReadStroke(w, l);
        if (IsReplay(key)) return S_OK;
        auto tested = SameTest(key) ? tested_ : std::nullopt;
        tested_.reset();
        if (tested) key = tested->key; // the modifier snapshot of this event
        const bool moved = FocusChanged();
        if (moved) FocusMoved();
        Decision decision = tested ? tested->decision : Decide(key);
        *e = decision.Eats() ? TRUE : FALSE;
        if (tested && decision.Eats() && (moved || tested->generation != focus_generation_)) {
            Buffer(key);
            AdoptHeld();
            return S_OK;
        }
        const bool eligible = ScopeAllowsInput() && !KeyboardDisabled(tm_) &&
                              (!KeyboardClosed(tm_) || (decision.action == Action::Global &&
                                                       tip_logic::OpensKeyboard(decision.command)));
        if (decision.Eats() && (decision.action == Action::Buffer || carry_.Active() ||
                               !buffered_.empty() || KeysWaiting() || !eligible)) {
            Buffer(key);
            return S_OK;
        }
        if (!eligible) return S_OK;
        FlushReleases();
        Typed(key);
        switch (decision.action) {
            case Action::Buffer: break; // queued above, even if the field is unresolved
            case Action::Global:
                if (!RunGlobal(decision.command)) ReplayHeld(key);
                break;
            case Action::Send: SendOrReplay(key, ctx, true); break;
            case Action::ObserveAlt:
                if (tested && !buffered_.empty() && SameEvent(buffered_.front(), key) && !KeysWaiting()) {
                    buffered_.pop_front();
                    SendKey(key, false, ctx, true);
                } else if (!tested) {
                    if (KeysWaiting() || !buffered_.empty()) Buffer(key);
                    else SendKey(key, false, ctx, true);
                }
                break;
            case Action::Pass:
                down_sent_[key.raw].reset();
                break;
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnKeyUp(ITfContext*, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        auto key = ReadStroke(w, l, false);
        if (GetMessageExtraInfo() == kReplayMarker) return S_OK;
        if (tested_ && tested_->key.raw == key.raw) tested_.reset();
        if (!SameEvent(tested_up_, key)) QueueRelease(key);
        tested_up_.reset();
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnPreservedKey(ITfContext*, REFGUID guid, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        if (!tm_ || HeldMods().win) return S_OK;
        for (const auto& key : preserved_) {
            if (key.guid != guid) continue;
            auto event = ReadStroke(key.key.uVKey, 0);
            event.preserved = true;
            const unsigned mods = key.code >> 8;
            event.chord = {key.code & 0xFF, {bool(mods & 1), bool(mods & 2), bool(mods & 4), false}};
            if (IsReplay(event)) return S_OK;
            if (FocusChanged()) FocusMoved();
            auto decision = Decide(event);
            if (decision.action == Action::Buffer) {
                Buffer(event);
                *e = TRUE;
            } else if (decision.action == Action::Global) {
                *e = RunGlobal(decision.command) ? TRUE : FALSE;
            }
            break;
        }
        return S_OK;
    }

    // -- display attributes ---------------------------------------------------------------
    HRESULT STDMETHODCALLTYPE EnumDisplayAttributeInfo(IEnumTfDisplayAttributeInfo** pp) override {
        if (!pp) return E_POINTER; *pp = new AttributeEnum(); return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetDisplayAttributeInfo(REFGUID guid, ITfDisplayAttributeInfo** pp) override {
        if (!pp) return E_POINTER;
        *pp = nullptr;
        for (int i = 0; i < 3; ++i) if (guid == kAttributeGuids[i]) {
            *pp = new AttributeInfo(i); return S_OK;
        }
        return E_INVALIDARG;
    }

    // -- the taskbar item (DESIGN「状態」, DESIGN「メニュー」) ----------------------------------------------------
    HRESULT STDMETHODCALLTYPE GetInfo(TF_LANGBARITEMINFO* info) override {
        if (!info) return E_INVALIDARG;
        info->clsidService = CLSID_YuragiTip;
        info->guidItem = GUID_LBI_INPUTMODE;
        info->dwStyle = TF_LBI_STYLE_BTN_BUTTON | TF_LBI_STYLE_SHOWNINTRAY;
        info->ulSort = 0;
        wcsncpy_s(info->szDescription, ARRAYSIZE(info->szDescription),
                  L"ゆらぎ 入力モード", _TRUNCATE);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetStatus(DWORD* status) override {
        if (!status) return E_INVALIDARG;
        *status = 0;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Show(BOOL) override { return E_NOTIMPL; }
    HRESULT STDMETHODCALLTYPE GetTooltipString(BSTR* tip) override {
        if (!tip) return E_INVALIDARG;
        const wchar_t* text = L"";
        switch (CurrentMode()) {
            case Mode::Normal:
                text = direct_ ? L"ゆらぎ: 直接入力（クリックでかな入力）"
                               : L"ゆらぎ: かな入力（クリックで直接入力）";
                break;
            case Mode::Preparing: text = L"ゆらぎ: 変換の準備をしています"; break;
            case Mode::Stopped: text = L"ゆらぎ: 日本語変換が止まっています（右クリックで操作）"; break;
            case Mode::Excluded: text = L"ゆらぎ: このアプリでは日本語変換を使えません"; break;
        }
        *tip = SysAllocString(text);
        return *tip ? S_OK : E_OUTOFMEMORY;
    }
    // The menu's items (DESIGN「メニュー」); grayed: shown but not selectable.
    const wchar_t* MenuText(int item, bool* grayed) const {
        *grayed = false;
        switch (item) {
            case tip_logic::MENU_TOGGLE: return direct_ ? L"かな入力に切り替え" : L"直接入力に切り替え";
            case tip_logic::MENU_ADMIN: return L"設定を開く";
            case tip_logic::MENU_RETRY: return L"もう一度試す";
            case tip_logic::MENU_PREPARING:
                *grayed = true;
                return L"（変換の準備をしています）";
        }
        return L"";
    }
    HRESULT STDMETHODCALLTYPE OnClick(TfLBIClick click, POINT pt, const RECT*) override {
        if (click == TF_LBI_CLK_LEFT && tip_logic::Toggles(CurrentMode()) && Eligible()) Toggle();
        // The taskbar input indicator hands a right click over as OnClick and never
        // calls InitMenu, so the menu is shown here (owned by this thread's focus window).
        if (click == TF_LBI_CLK_RIGHT) ShowMenu(GetFocus(), pt, TPM_BOTTOMALIGN);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE InitMenu(ITfMenu* menu) override {
        if (!menu) return E_INVALIDARG;
        for (int item : tip_logic::MenuFor(CurrentMode())) {
            bool grayed;
            const wchar_t* text = MenuText(item, &grayed);
            menu->AddMenuItem(item, grayed ? TF_LBMENUF_GRAYED : 0, nullptr, nullptr, text,
                              (ULONG)wcslen(text), nullptr);
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnMenuSelect(UINT id) override {
        switch (id) {
            case tip_logic::MENU_TOGGLE:
                if (Eligible()) Toggle();
                break;
            case tip_logic::MENU_ADMIN:
                // DESIGN「メニュー」: the broker opens it (the TIP starts no Python).
                OpenAdmin(R"({"op":"open_admin"})");
                break;
            case tip_logic::MENU_RETRY:
                if (link_.Connected()) link_.Write(R"({"op":"retry"})", tip_logic::KEY_BUDGET_MS);
                else TryConnect(true);
                break;
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetIcon(HICON* icon) override {
        if (!icon) return E_INVALIDARG;
        Mode mode = CurrentMode();
        *icon = MakeModeIcon(Utf8ToWide(tip_logic::Glyph(mode, direct_)).c_str(),
                             tip_logic::Faint(mode));  // the caller destroys it
        return *icon ? S_OK : E_FAIL;
    }
    HRESULT STDMETHODCALLTYPE GetText(BSTR* text) override {
        if (!text) return E_INVALIDARG;
        *text = SysAllocString(Utf8ToWide(tip_logic::Glyph(CurrentMode(), direct_)).c_str());
        return *text ? S_OK : E_OUTOFMEMORY;
    }
    // ITfSource: the language bar advises its item sink here.
    HRESULT STDMETHODCALLTYPE AdviseSink(REFIID riid, IUnknown* unk, DWORD* cookie) override {
        if (!unk || !cookie) return E_INVALIDARG;
        if (riid != IID_ITfLangBarItemSink) return CONNECT_E_CANNOTCONNECT;
        if (lb_sink_) return CONNECT_E_ADVISELIMIT;
        if (FAILED(unk->QueryInterface(IID_ITfLangBarItemSink, (void**)&lb_sink_))) {
            lb_sink_ = nullptr;
            return E_NOINTERFACE;
        }
        *cookie = kLangBarCookie;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE UnadviseSink(DWORD cookie) override {
        if (cookie != kLangBarCookie || !lb_sink_) return CONNECT_E_NOCONNECTION;
        lb_sink_->Release();
        lb_sink_ = nullptr;
        return S_OK;
    }

    // Called by the scope and caret edit sessions.
    void ScopeChecked(ITfContext* ctx, uint64_t generation, tip_logic::Scope scope) {
        if (ctx != scope_ctx_ || generation != focus_generation_) return;
        scope_ = scope;
        if (carry_.Active()) PostMessageW(hwnd_, kKeysMessage, 0, 0);
    }
    void PlaceNotice(TfEditCookie ec, ITfContext* ctx, ITfRange* caret) {
        if (notice_ != Notice::None) PlacePopup(ec, ctx, caret, notice_popup_);
    }
    std::shared_ptr<CompositionState> State() { return state_; }

private:
    friend class ReadSession;
    using Scope = tip_logic::Scope;
    static const UINT kLinkMessage = WM_APP + 1;
    static const UINT kMenuMessage = WM_APP + 3;
    static const UINT_PTR kTimerNotice = 3, kTimerReplay = 4, kTimerCarry = 5;
    static const DWORD kLangBarCookie = 0x6f79;

    // -- the TIP's window: link messages and its one-shot timers ---------------------------
    static LRESULT CALLBACK WindowProc(HWND h, UINT m, WPARAM w, LPARAM l) {
        auto* self = (Tip*)GetWindowLongPtrW(h, GWLP_USERDATA);
        if (self && m == kLinkMessage) {
            self->Drain(false, 0);
            return 0;
        }
        if (self && m == kKeysMessage) {
            self->PumpKeys();
            return 0;
        }
        if (self && m == kMenuMessage) {
            self->AddRef();
            self->ShowKeyboardMenu();
            self->Release();
            return 0;
        }
        if (self && m == WM_TIMER) {
            KillTimer(h, w);  // every timer here rings once
            self->OnTimer((UINT_PTR)w);
            return 0;
        }
        return DefWindowProcW(h, m, w, l);
    }

    void EnsureWindow() {
        if (hwnd_) return;
        WNDCLASSW wc{};
        wc.lpfnWndProc = WindowProc;
        wc.hInstance = g_hinst;
        wc.lpszClassName = L"YuragiTip";
        RegisterClassW(&wc);
        hwnd_ = CreateWindowExW(0, wc.lpszClassName, L"", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr,
                                g_hinst, nullptr);
        SetWindowLongPtrW(hwnd_, GWLP_USERDATA, (LONG_PTR)this);
    }

    void OnTimer(UINT_PTR id) {
        if (id != 0 && id == reply_timer_) {
            reply_timer_ = 0;
            if (FocusChanged()) {
                FocusMoved();
                return;
            }
            if (direct_) return;
            std::string at = "\"t\":" + std::to_string(NowMs());
            if (timer_pending_)
                SendRequest("timeout", at);
            else if (!in_flight_.Waiting() && buffered_.empty() && !KeysWaiting())
                SendRequest("suggest", at, false);
        } else if (id == kTimerNotice) {
            HideNotice();
        } else if (id == kTimerReplay) {
            if (retry_replay_) {
                auto key = *retry_replay_;
                retry_replay_.reset();
                if (!ReplayHeld(key)) return;
            } else replay_.reset();
            PumpKeys();
        } else if (id == kTimerCarry) {
            PumpKeys();
        }
    }

    void ArmTimer(UINT_PTR id, ULONGLONG at) {
        ULONGLONG now = NowMs();
        SetTimer(hwnd_, id, at > now ? (UINT)(std::min<ULONGLONG>)(at - now, 0x7fffffff) : 0, nullptr);
    }

    void CancelReplyTimer() {
        if (hwnd_ && reply_timer_) KillTimer(hwnd_, reply_timer_);
        reply_timer_ = 0;
    }

    void ArmReplyTimer(ULONGLONG at) {
        // A queued WM_TIMER survives KillTimer. Give each deadline its own ID.
        reply_timer_ = ++next_reply_timer_;
        ArmTimer(reply_timer_, at);
    }

    // -- connection -------------------------------------------------------------------------
    void TryConnect(bool user = false) {
        if (!link_.Idle()) return;
        if (!user && !connect_gate_.Allow(NowMs())) return;
        if (user) connect_gate_.Allow(NowMs());
        link_.RequestConnect();
    }

    Mode CurrentMode() const { return tip_logic::ModeFor(link_state_, broker_state_); }

    // A kana keystroke (DESIGN「接続」): tries the connection, and when stopped, says so once
    // per focus (DESIGN「小さな表示」).
    void Typed(const Stroke& key) {
        if (direct_ || !tip_logic::Typing(key.chord)) return;
        TryConnect();
        if (CurrentMode() == Mode::Stopped && !stopped_told_) {
            stopped_told_ = true;
            ShowNotice(Notice::Stopped);
        }
    }

    // The settings window, also when there is no connection yet: the request waits for the
    // connection the user's action starts, and goes when it is made (DESIGN「接続」).
    void OpenAdmin(const char* request) {
        if (link_.Connected()) {
            link_.Write(request, tip_logic::KEY_BUDGET_MS);
            return;
        }
        admin_request_ = request;
        TryConnect(true);
    }

    // Apply link changes and replies in order, synchronously when TSF allows it.
    bool Drain(bool sync, long long wanted) {
        bool found = false;
        BrokerLink::Item item;
        Mode before = CurrentMode();
        while (link_.Pop(item)) {
            switch (item.kind) {
                case BrokerLink::Item::Connected:
                    link_state_ = Link::Connected;
                    broker_state_.clear();
                    in_flight_.Clear();
                    if (admin_request_) link_.Write(admin_request_, tip_logic::KEY_BUDGET_MS);
                    admin_request_ = nullptr;
                    break;
                case BrokerLink::Item::Connecting:
                    link_state_ = Link::Connecting;
                    break;
                case BrokerLink::Item::Unavailable:
                    link_state_ = item.link;
                    admin_request_ = nullptr;
                    break;
                case BrokerLink::Item::Lost:
                    // DESIGN「見えている文字の確定」: the broker is gone; what is shown stays.
                    Log(L"broker connection lost");
                    link_state_ = Link::Connecting;
                    broker_state_.clear();
                    in_flight_.Clear();
                    FinishLocal();
                    if (admin_request_) TryConnect(true);  // asked for as the link went
                    break;
                case BrokerLink::Item::Line: {
                    Message m;
                    if (!tip_logic::ParseMessage(item.line, m)) break;
                    if (Handle(m, sync, wanted)) {
                        found = true;
                    }
                    break;
                }
            }
            if (found) break;
        }
        if (CurrentMode() != before) UpdateLangBar();
        return found;
    }

    // One message from the broker. Returns true when it is the reply `wanted`.
    bool Handle(const Message& m, bool sync, long long wanted) {
        // The hello reply, a state event, or {"seq","state"}: a request the
        // engine did not get (it is starting, or down).
        bool was_ready = broker_state_ == "ready";
        if (m.keymap && m.keymap->rev != keymap_.rev) {
            keymap_ = *m.keymap;
            PreserveKeys();
        }
        if (m.hello || m.event == "state" || (m.has_seq && !m.engine)) broker_state_ = m.state;
        // DESIGN「使えない間の打鍵」: a ready engine has opened a new session, in kana input.
        if (!was_ready && broker_state_ == "ready") {
            if (input_mode_ != "hiragana")
                pending_mode_seq_ = SendRequest("set_mode", "\"mode\":" + tip_json::Quote(input_mode_));
            if (direct_) pending_mode_seq_ = SendRequest("set_direct", "\"direct\":true");
        }
        if (!m.has_seq) {
            if (tip_logic::CommitsVisibleText(m)) FinishLocal();
            return false;
        }
        if (!in_flight_.Answer(m.seq) || m.seq <= stale_upto_) {
            if (state_ && !m.commit.empty()) state_->BreakContinuity();
            return false;
        }
        if (m.engine && FocusChanged()) {
            FocusMoved();
            return false;
        }
        if (!m.engine) {
            auto sent = sent_keys_.find(m.seq);
            if (sent != sent_keys_.end()) {
                auto key = sent->second.key;
                key.windows_only = true; // the broker explicitly did not process it
                buffered_.push_front(key);
                sent_keys_.erase(sent);
            }
            if (tip_logic::CommitsVisibleText(m)) FinishLocal();
            if (!buffered_.empty()) PostMessageW(hwnd_, kKeysMessage, 0, 0);
            return m.seq == wanted;
        }
        if (m.suggestion_only) {
            if (state_ && m.seq == in_flight_.Last()) {
                NoteCandidates(m);
                state_->show_candidates = m.ShowsCandidates();
                RequestCandidatePosition();
                if (m.suggest_at) ArmReplyTimer(*m.suggest_at);
            }
            return m.seq == wanted;
        }
        if (tip_logic::CommitsVisibleText(m)) FinishLocal(false);
        if (m.error) {
            sent_keys_.clear();
            pending_mode_seq_ = mode_edit_seq_ = 0;
            NoteReply(m);  // the engine started a clean session; the text stays (DESIGN「見えている文字の確定」)
            PostMessageW(hwnd_, kKeysMessage, 0, 0);
            return m.seq == wanted;
        }
        Log(L"reply client=%p seq=%lld t=%llu pending=%d",
            static_cast<void*>(this), m.seq, NowMs(), m.pending);
        if (settings_.log_text)  // the typed text only on request (tip.json "log_text")
            Log(L"reply text seq=%lld comp=%ls commit=%ls", m.seq,
                Utf8ToWide(m.composition).c_str(), Utf8ToWide(m.commit).c_str());
        if (!m.eat_pending) KeyResult(m.seq, m.eat.value_or(true), m.global, m.seq);
        for (const auto& [seq, eat, global] : m.resolved_keys) KeyResult(seq, eat, global, m.seq);
        if (pending_mode_seq_ && m.seq >= pending_mode_seq_ && !m.pending) {
            pending_mode_seq_ = 0;
            mode_edit_seq_ = m.seq;
        }
        NoteReply(m);
        ApplyReply(m, sync);
        return m.seq == wanted;
    }

    // -- sending ---------------------------------------------------------------------------
    // A numbered request whose reply is applied when it comes (timer polls,
    // resets). Only while keys go to the broker at all.
    long long SendRequest(const std::string& op, const std::string& extra = "", bool blocking = true) {
        if (!link_.Connected() || !tip_logic::SendsKeys(CurrentMode())) return 0;
        long long seq = in_flight_.Next(blocking);
        if (!link_.Write(tip_logic::OpRequest(seq, op, extra), blocking ? tip_logic::KEY_BUDGET_MS : 0)) {
            in_flight_.Answer(seq);
            return 0;
        }
        return seq;
    }

    SendResult SendKey(const Stroke& key, bool capture, ITfContext* ctx, bool sync) {
        if (!link_.Connected() || !tip_logic::SendsKeys(CurrentMode())) return SendResult::Unavailable;
        const ULONGLONG start = NowMs(), deadline = start + tip_logic::KEY_BUDGET_MS;
        std::optional<tip_logic::KeyContext> context;
        bool awaiting = in_flight_.Waiting() || pending_ || (state_ && !state_->pending.empty());
        if (settings_.document_context && key.down && tip_logic::Typing(key.chord)
                && ((!composing_ && fsm_idle_) || awaiting)) {
            context.emplace();
            context->disconnected = !awaiting && state_ && state_->disconnected;
            if (CanReadContext(ctx)) {
                uint64_t generation = focus_generation_;
                *context = ReadContext(ctx);
                if (generation != focus_generation_) return SendResult::FocusMoved;
                if (FocusChanged()) {
                    FocusMoved();
                    return SendResult::FocusMoved;
                }
            }
        }
        if (FocusChanged()) {
            FocusMoved();
            return SendResult::FocusMoved;
        }
        if (!ScopeAllowsInput()) return SendResult::Unavailable;
        long long seq = in_flight_.Next();
        auto request = tip_logic::KeyRequest(seq, key.down, key.chord.vk, key.time, key.chord.mods,
                                            context ? &*context : nullptr);
        ULONGLONG now = NowMs();
        DWORD budget = now < deadline ? (DWORD)(deadline - now) : 0;
        if (!link_.Write(request, budget)) {
            in_flight_.Answer(seq);
            return SendResult::Unavailable;
        }
        if (capture) sent_keys_.emplace(seq, SentKey{key});
        if (key.down && capture) down_sent_[key.raw] = key.chord;
        if (sync) {
            while (in_flight_.Waiting(seq) && !Drain(true, seq)) {
                now = NowMs();
                if (now >= deadline || !in_flight_.Waiting(seq)) break;
                WaitForSingleObject(link_.Arrived(), (DWORD)(deadline - now));
            }
        }
        return SendResult::Sent;
    }

    void SendKeyUp(Stroke key) {
        auto& sent = down_sent_[key.raw];
        if (!sent) return;
        key.chord = *sent;
        sent.reset();
        SendKey(key, false, nullptr, false);
    }

    bool Toggle() { return RunGlobal(tip_logic::GlobalCommand::Toggle); }

    // -- replies --------------------------------------------------------------------------
    tip_logic::Local LocalState() const {
        return {phase_, timer_pending_ || pending_ || in_flight_.Waiting()};
    }

    void NoteReply(const Message& r) {
        bool mode_changed = direct_ != r.direct;
        direct_ = r.direct;
        if (!r.input_mode.empty()) input_mode_ = r.input_mode;
        phase_ = r.phase.value_or(r.direct ? tip_logic::Phase::Direct :
                 r.predicting ? tip_logic::Phase::Predicting :
                 r.converted ? tip_logic::Phase::Selecting :
                 r.n_tokens > 0 || !r.composition.empty() ? tip_logic::Phase::Composing :
                 tip_logic::Phase::Empty);
        if (mode_changed) {
            if (state_) state_->BreakContinuity();
            UpdateLangBar();
        }
        pending_ = r.pending;
        fsm_idle_ = r.fsm_idle;
        composing_ = phase_ != tip_logic::Phase::Empty && phase_ != tip_logic::Phase::Direct;
        timer_pending_ = r.has_timer && !r.direct;
        NoteCandidates(r);
        CancelReplyTimer();
        if (timer_pending_)
            ArmReplyTimer(r.timer);
        else if (!r.direct && r.suggest_at)
            ArmReplyTimer(*r.suggest_at);
    }

    void NoteCandidates(const Message& r) {
        if (r.ShowsCandidates()) {
            std::vector<TipPopup::Row> rows;
            rows.reserve(r.candidates.size());
            for (size_t i = 0; i < r.candidates.size(); ++i) {
                rows.push_back({Utf8ToWide(r.candidates[i]), i < r.candidate_notes.size()
                                ? Utf8ToWide(r.candidate_notes[i]) : std::wstring()});
            }
            std::wstring footer;
            if (r.suggesting) {
                footer = L"Tab で選択";
            } else if (r.page > 0 || r.has_next_page) {
                footer = std::to_wstring((long long)std::max(0, r.page) + 1) + L" ページ";
                if (r.has_next_page) footer += L"  ▾";
            }
            candidate_.SetRows(std::move(rows), r.cand_index, std::move(footer), !r.suggesting);
            Log(L"candidate reply client=%p seq=%lld", static_cast<void*>(this), r.seq);
        } else {
            HideCands();
        }
    }

    void ApplyReply(const Message& r, bool sync) {
        if (r.seq <= stale_upto_) {
            if (state_ && !r.commit.empty()) state_->BreakContinuity();
            return;
        }
        ITfContext* ctx = FocusContext();
        if (!ctx) {
            if (state_) state_->BreakContinuity();
            return;
        }
        if (ctx != scope_ctx_ || (state_ && state_->ctx != ctx)) {
            ctx->Release();
            FocusMoved();
            return;
        }
        if (!state_) {
            state_ = std::make_shared<CompositionState>(ctx, edit_cookie_ != TF_INVALID_COOKIE);
            AdviseLayout(ctx);
        }
        state_->show_candidates = r.ShowsCandidates();
        ctx->Release();
        state_->pending.push_back(r);
        RequestEdit(EditSession::Apply, state_, sync);
    }

    void RequestEdit(EditSession::Kind kind, std::shared_ptr<CompositionState> state, bool sync) {
        auto* es = new EditSession(kind, state, this, atoms_, candidate_, &retired_, hwnd_);
        HRESULT result = S_OK;
        DWORD flags = (kind == EditSession::Position ? TF_ES_READ : TF_ES_READWRITE) |
                      (sync ? TF_ES_SYNC : TF_ES_ASYNCDONTCARE);
        HRESULT hr = state->ctx->RequestEditSession(client_, es, flags, &result);
        if (sync && (hr == TF_E_SYNCHRONOUS || result == TF_E_SYNCHRONOUS))
            hr = state->ctx->RequestEditSession(client_, es, (flags & ~TF_ES_SYNC) | TF_ES_ASYNCDONTCARE,
                                                &result);
        // The application may refuse an edit (a read-only field): nothing more
        // is done about it; the connection is the broker's business, not the app's.
        if (FAILED(hr) || FAILED(result)) {
            if (kind == EditSession::Apply) {
                if (!state->pending.empty()) state->applied_seq = state->pending.back().seq;
                state->pending.clear();
                state->BreakContinuity();
                PostMessageW(hwnd_, kKeysMessage, 0, 0);
            } else if (kind == EditSession::Position) state->position_pending = false;
            Log(L"edit refused hr=%08lx result=%08lx", hr, result);
        }
        es->Release();
    }

    void RequestCandidatePosition() {
        if (!state_ || !state_->active || !state_->show_candidates || state_->position_pending) return;
        state_->position_pending = true;
        RequestEdit(EditSession::Position, state_, false);
    }

    // DESIGN「見えている文字の確定」: the conversion ends with its text on screen; local state starts over.
    void FinishLocal(bool invalidate_replies = true) {
        // The FIFO and any Windows replay belong to the input, which can
        // continue even when the engine's session is reset.
        if (invalidate_replies) {
            stale_upto_ = in_flight_.Last();
            in_flight_.Clear();
            sent_keys_.clear();
            releases_.clear();
            tested_up_.reset();
            pending_mode_seq_ = mode_edit_seq_ = 0;
        }
        CancelReplyTimer();
        auto old = state_;
        state_.reset();
        if (old) {
            old->active = false;
            old->pending.clear();
            old->BreakContinuity();
        }
        UnadviseLayout();
        if (old) {
            retired_.push_back(old);
            if (old->composition && client_ != TF_CLIENTID_NULL) RequestEdit(EditSession::Finalize, old, true);
        }
        retired_.erase(std::remove_if(retired_.begin(), retired_.end(),
            [](const std::shared_ptr<CompositionState>& o) { return !o->composition; }), retired_.end());
        composing_ = pending_ = timer_pending_ = false;
        fsm_idle_ = true;
        phase_ = direct_ ? tip_logic::Phase::Direct : tip_logic::Phase::Empty;
        for (auto& sent : down_sent_) sent.reset();
        HideCands();
        if (!buffered_.empty()) PostMessageW(hwnd_, kKeysMessage, 0, 0);
    }

    // A new field: what was being converted is kept as typed, the engine
    // forgets it, and the field's kind is looked up once (DESIGN「パスワード欄」).
    void FocusMoved() {
        const bool was_carrying = carry_.Active();
        if (!carry_.OnFocusMoved(RootOwner(), buffered_.empty() && !retry_replay_, NowMs())) {
            DropHeld(L"focus");
        } else if (!was_carrying) {
            StartCarryTimer();
        }
        FinishLocal();
        SendRequest("reset");
        stopped_told_ = false;
        HideNotice();
        CheckScope();
    }

    ITfContext* FocusContext() {
        ITfDocumentMgr* dm = nullptr;
        if (!tm_ || FAILED(tm_->GetFocus(&dm)) || !dm) return nullptr;
        ITfContext* ctx = nullptr;
        dm->GetTop(&ctx);
        dm->Release();
        return ctx;
    }
    bool FocusChanged() {
        ITfContext* ctx = FocusContext();
        bool changed = ctx != scope_ctx_;
        if (ctx) ctx->Release();
        return changed;
    }

    void CheckScope();
    tip_logic::KeyContext ReadContext(ITfContext* ctx);
    bool CanReadContext(ITfContext* ctx) {
        return ctx && ctx == scope_ctx_ && scope_ == Scope::Allowed && Eligible() && !direct_
            && !composing_ && fsm_idle_ && !pending_ && !timer_pending_ && !in_flight_.Waiting()
            && (!state_ || (!state_->composition && state_->pending.empty()))
            && std::none_of(retired_.begin(), retired_.end(), [ctx](const auto& old) {
                return old->ctx == ctx && old->composition;
            });
    }

    void UnadviseTextEdit() {
        if (edit_cookie_ == TF_INVALID_COOKIE) return;
        ITfSource* src = nullptr;
        if (SUCCEEDED(scope_ctx_->QueryInterface(IID_ITfSource, (void**)&src))) {
            src->UnadviseSink(edit_cookie_);
            src->Release();
        }
        edit_cookie_ = TF_INVALID_COOKIE;
    }

    // -- keys and replay -------------------------------------------------------------------
    bool Eligible() { return tm_ && !KeyboardDisabled(tm_) && !KeyboardClosed(tm_); }
    bool ScopeAllowsInput() const { return tip_logic::AllowsInput(scope_, carry_.Active()); }
    static uintptr_t RootOwner() {
        HWND foreground = GetForegroundWindow();
        if (GetWindowThreadProcessId(foreground, nullptr) != GetCurrentThreadId()) return 0;
        return reinterpret_cast<uintptr_t>(GetAncestor(foreground, GA_ROOTOWNER));
    }
    size_t HeldCount() const {
        return (retry_replay_ ? 1 : 0) +
            std::count_if(buffered_.begin(), buffered_.end(), [](const Stroke& key) {
                return key.down && !tip_logic::AltVk(key.raw);
            });
    }
    void StartCarryTimer() {
        Log(L"carry start n=%zu", HeldCount());
        ArmTimer(kTimerCarry, carry_.Started() + tip_logic::KEY_BUDGET_MS);
    }
    void AdoptHeld() {
        const auto root = RootOwner();
        const bool continuing = carry_.Active() && carry_.SameRoot(root);
        carry_.Adopt(root, NowMs());
        if (!continuing) StartCarryTimer();
        PostMessageW(hwnd_, kKeysMessage, 0, 0);
    }
    void DropHeld(const wchar_t* reason, size_t extra = 0) {
        const size_t count = HeldCount() + extra;
        if (count) Log(L"held keys dropped n=%zu reason=%ls", count, reason);
        buffered_.clear();
        replay_.reset();
        retry_replay_.reset();
        carry_.Finished();
        KillTimer(hwnd_, kTimerReplay);
        KillTimer(hwnd_, kTimerCarry);
    }
    Stroke ReadStroke(WPARAM w, LPARAM l, bool down = true) {
        UINT vk = VkOf(w);
        return {vk, l, GetMessageTime(), NowMs(), tip_logic::NormalizeKey(vk, HeldMods()), down};
    }
    bool SameTest(const Stroke& key) const {
        return tested_ && SameEvent(tested_->key, key);
    }
    static bool SameEvent(const std::optional<Stroke>& event, const Stroke& key) {
        constexpr LPARAM scan = 0x01FF0000;
        return event && key.raw == event->raw && (key.flags & scan) == (event->flags & scan) &&
               key.message_time == event->message_time;
    }
    bool KeysWaiting() const {
        return !sent_keys_.empty() || pending_mode_seq_ || mode_edit_seq_ || replay_ || retry_replay_ ||
               menu_generation_;
    }
    tip_logic::GlobalCommand GlobalFor(unsigned code, bool closed = false) const {
        using tip_logic::GlobalCommand;
        auto command = keymap_.GlobalAt(closed ? tip_logic::Phase::Direct : phase_, code);
        if (closed && !tip_logic::OpensKeyboard(command)) return GlobalCommand::None;
        if (command == GlobalCommand::Settings) return command;
        if (command == GlobalCommand::Words)
            return tip_logic::SendsKeys(CurrentMode()) ? command : GlobalCommand::None;
        return tip_logic::Toggles(CurrentMode()) ? command : GlobalCommand::None;
    }

    Decision Decide(const Stroke& key, bool buffer = true) {
        using namespace tip_logic;
        if (!tm_ || key.chord.mods.win || UntranslatedJisKey(key.raw, (uint32_t)key.flags)) return {};
        const bool closed = KeyboardClosed(tm_);
        auto reopen = closed ? GlobalFor(key.chord.Code(), true) : GlobalCommand::None;
        if (closed && reopen == GlobalCommand::None) return {};
        const bool can_hold = HoldDuringCarry(key.chord, key.raw, (uint32_t)key.flags,
                                              keymap_.global.count(key.chord.Code()) != 0);
        if (buffer && carry_.Active()) return {can_hold ? Action::Buffer : Action::Pass};
        if (buffer && (!buffered_.empty() || retry_replay_) && can_hold) return {Action::Buffer};
        if (KeyboardDisabled(tm_) || !ScopeAllowsInput()) return {};
        if (closed)
            return buffer && KeysWaiting() ? Decision{Action::Buffer} : Decision{Action::Global, reopen};
        auto local = LocalState();
        bool ready = link_.Connected() && SendsKeys(CurrentMode());
        if (AltVk(key.raw)) {
            if (!direct_ && ready && (local.phase != Phase::Empty || local.unsettled))
                return {Action::ObserveAlt};
            return {};
        }
        if (ModifierVk(key.raw) || KanaLockKey(key.raw, (uint32_t)key.flags)) return {};
        if (buffer && KeysWaiting() && can_hold)
            return {Action::Buffer};
        if (ready && !direct_ && WantKey(key.chord, local, keymap_) == Take::Send)
            return {Action::Send};
        auto global = GlobalFor(key.chord.Code());
        if (global != GlobalCommand::None) return {Action::Global, global};
        return {};
    }

    void Buffer(const Stroke& key) {
        buffered_.push_back(key);
        PostMessageW(hwnd_, kKeysMessage, 0, 0);
    }
    void QueueRelease(const Stroke& key) {
        auto stroke = std::find_if(buffered_.rbegin(), buffered_.rend(),
                                  [&](const Stroke& queued) { return queued.raw == key.raw; });
        if (stroke != buffered_.rend() && stroke->down) {
            Buffer(key);
        } else if (down_sent_[key.raw] && Eligible() && ScopeAllowsInput() && !FocusChanged()) {
            auto release = key;
            release.chord = *down_sent_[key.raw];
            down_sent_[key.raw].reset();
            releases_.push_back(release);
            PostMessageW(hwnd_, kKeysMessage, 0, 0);
        }
    }
    void KeyResult(long long seq, bool eat, std::optional<tip_logic::GlobalCommand> global,
                   long long reply_seq) {
        auto key = sent_keys_.find(seq);
        if (key == sent_keys_.end()) return;
        if (eat && !global) {
            sent_keys_.erase(key);
        } else {
            key->second.run_after = global;
            key->second.replay_after = reply_seq;
        }
    }
    void FlushReleases() {
        while (!releases_.empty()) {
            auto release = releases_.front();
            releases_.pop_front();
            SendKey(release, false, nullptr, false);
        }
    }
    void PumpKeys() {
        if (!tm_ || menu_generation_) return;
        if (FocusChanged() || (carry_.Active() && !carry_.SameRoot(RootOwner()))) {
            FocusMoved();
            return;
        }
        carry_.Pumped();
        FlushReleases();
        if (replay_ || retry_replay_ || pending_mode_seq_) return;
        if (mode_edit_seq_) {
            if (scope_ctx_ && (!state_ || state_->applied_seq < mode_edit_seq_)) return;
            mode_edit_seq_ = 0;
        }
        if (!sent_keys_.empty()) {
            auto sent = sent_keys_.begin();
            auto [key, after, global] = sent->second;
            if (!after || !state_ || state_->applied_seq < after) return;
            sent_keys_.erase(sent);
            if ((!global || !RunGlobal(*global)) && !ReplayHeld(key)) return;
            if (replay_ || retry_replay_ || pending_mode_seq_ || menu_generation_) return;
        }
        if (state_ && !state_->pending.empty()) return;
        while (!buffered_.empty() && !KeysWaiting()) {
            auto started = CarryStarted();
            const auto now = NowMs();
            auto key = buffered_.front();
            const bool eligible = !KeyboardDisabled(tm_) &&
                (!KeyboardClosed(tm_) || (key.down &&
                 GlobalFor(key.chord.Code(), true) != tip_logic::GlobalCommand::None));
            const auto delivery = tip_logic::DeliverHeld({scope_ctx_ != nullptr, eligible, scope_}, now, started);
            if (delivery == tip_logic::Deliver::Wait) {
                ArmTimer(kTimerCarry, *started + tip_logic::KEY_BUDGET_MS);
                return;
            }
            buffered_.pop_front();
            if (delivery == tip_logic::Deliver::Raw || key.windows_only) {
                if (key.down && !tip_logic::AltVk(key.raw)) {
                    if (key.preserved && scope_ == Scope::Password) {
                        Log(L"held command suppressed reason=password n=1");
                        continue;
                    }
                    if (!ReplayHeld(key)) return;
                }
                continue;
            }
            if (!key.down) { SendKeyUp(key); continue; }
            if (tip_logic::AltVk(key.raw)) { SendKey(key, false, nullptr, false); continue; }
            auto decision = Decide(key, false);
            if (decision.action == Action::Global && RunGlobal(decision.command)) continue;
            if (decision.action == Action::Send) {
                if (!SendOrReplay(key, scope_ctx_, false)) return;
            } else if (!ReplayHeld(key)) return;
        }
        if (carry_.Active() && buffered_.empty() && !KeysWaiting()) {
            if (scope_ == Scope::Unavailable) scope_ = Scope::Unknown;
            carry_.Finished();
            KillTimer(hwnd_, kTimerCarry);
        }
    }

    bool IsReplay(const Stroke& key) {
        const bool marked = GetMessageExtraInfo() == kReplayMarker;
        // Some TSF hosts do not expose GetMessageExtraInfo to the key sink.
        // In that case the one outstanding replay matches the key once.
        bool same = replay_ && (key.raw == replay_->raw || key.chord.vk == replay_->chord.vk)
                    && key.chord.mods.Bits() == replay_->chord.mods.Bits();
        if (same) {
            replay_.reset();
            KillTimer(hwnd_, kTimerReplay);
            carry_.ReplayPassed(RootOwner());
            tested_ = TestedKey{key, {}, focus_generation_};
            PostMessageW(hwnd_, kKeysMessage, 0, 0);
        }
        return marked || same;
    }

    std::optional<uint64_t> CarryStarted() const {
        return carry_.Active() ? std::optional{carry_.Started()} : std::nullopt;
    }
    static void LogCarryDelivery(const wchar_t* kind, std::optional<uint64_t> started) {
        if (started) Log(L"carry deliver kind=%ls waited=%llu", kind, NowMs() - *started);
    }

    bool SendOrReplay(const Stroke& key, ITfContext* ctx, bool sync) {
        auto started = CarryStarted();
        switch (SendKey(key, true, ctx, sync)) {
            case SendResult::Sent:
                LogCarryDelivery(L"engine", started);
                return true;
            case SendResult::FocusMoved:
                buffered_.push_front(key);
                AdoptHeld();
                return false;
            case SendResult::Unavailable: return ReplayHeld(key);
        }
        return false;
    }

    bool ReplayHeld(Stroke key) {
        key.windows_only = true;
        auto started = CarryStarted();
        switch (Replay(key)) {
            case ReplayResult::Sent:
                LogCarryDelivery(L"raw", started);
                return true;
            case ReplayResult::Retry: return true;
            case ReplayResult::FocusMoved:
                buffered_.push_front(key);
                FocusMoved();
                return false;
            case ReplayResult::Foreground:
                DropHeld(L"foreground", 1);
                return false;
            case ReplayResult::Failed:
                Log(L"held key replay failed reason=sendinput n=1");
                return true;
        }
        return false;
    }

    ReplayResult Replay(const Stroke& key) {
        DWORD foreground = 0;
        GetWindowThreadProcessId(GetForegroundWindow(), &foreground);
        if (foreground != GetCurrentProcessId()) return ReplayResult::Foreground;
        if (FocusChanged() || (carry_.Active() && !carry_.SameRoot(RootOwner())))
            return ReplayResult::FocusMoved;
        if ((GetAsyncKeyState(VK_LWIN) | GetAsyncKeyState(VK_RWIN)) & 0x8000) {
            retry_replay_ = key;
            SetTimer(hwnd_, kTimerReplay, 25, nullptr);
            return ReplayResult::Retry;
        }
        replay_ = key;
        // SendInput uses the keyboard state at injection time; restore any
        // modifiers the user changed while this key was waiting for its reply.
        std::vector<INPUT> input;
        auto add = [&](UINT vk, bool up, bool extended = false) {
            INPUT event{};
            event.type = INPUT_KEYBOARD;
            event.ki.wVk = (WORD)vk;
            event.ki.dwFlags = (up ? KEYEVENTF_KEYUP : 0) | (extended ? KEYEVENTF_EXTENDEDKEY : 0);
            event.ki.dwExtraInfo = (ULONG_PTR)kReplayMarker;
            input.push_back(event);
        };
        const auto mods = key.chord.mods;
        const std::pair<UINT, bool> wanted[] = {{VK_LSHIFT, mods.shift}, {VK_LCONTROL, mods.ctrl},
                                               {VK_LMENU, mods.alt}};
        std::vector<std::pair<UINT, bool>> restore;
        for (auto [left, need] : wanted) {
            bool left_held = (GetAsyncKeyState(left) & 0x8000) != 0;
            bool right_held = (GetAsyncKeyState(left + 1) & 0x8000) != 0;
            if (need && !left_held && !right_held) {
                add(left, false);
                restore.emplace_back(left, true);
            } else if (!need) {
                if (left_held) {
                    add(left, true);
                    restore.emplace_back(left, false);
                }
                if (right_held) {
                    add(left + 1, true, left != VK_LSHIFT);
                    restore.emplace_back(left + 1, false);
                }
            }
        }
        const bool extended = (key.flags & (1L << 24)) != 0;
        const bool released = !(GetAsyncKeyState(key.raw) & 0x8000);
        add(key.raw, false, extended);
        if (released) add(key.raw, true, extended);
        for (auto it = restore.rbegin(); it != restore.rend(); ++it)
            add(it->first, it->second, it->first == VK_RCONTROL || it->first == VK_RMENU);
        if (SendInput((UINT)input.size(), input.data(), sizeof(INPUT)) != input.size()) {
            replay_.reset();
            return ReplayResult::Failed;
        }
        SetTimer(hwnd_, kTimerReplay, tip_logic::KEY_BUDGET_MS, nullptr);
        return ReplayResult::Sent;
    }

    bool RunGlobal(tip_logic::GlobalCommand command) {
        using tip_logic::GlobalCommand;
        if (KeyboardClosed(tm_)) {
            if (!tip_logic::OpensKeyboard(command) || !tip_logic::Toggles(CurrentMode()) ||
                KeyboardDisabled(tm_) || !ScopeAllowsInput() || !OpenKeyboard(tm_, client_))
                return false;
            // Windows was off even if our last reported mode was kana.
            if (command == GlobalCommand::Toggle || command == GlobalCommand::On)
                command = GlobalCommand::Hiragana;
        }
        if (command == GlobalCommand::Menu) {
            if (!PostMessageW(hwnd_, kMenuMessage, 0, 0))
                return false;
            menu_generation_ = focus_generation_;
            return true;
        }
        if (command == GlobalCommand::Settings || command == GlobalCommand::Words) {
            OpenAdmin(command == GlobalCommand::Settings ? R"({"op":"open_admin"})"
                                                         : R"({"op":"open_admin","tab":"words"})");
            return true;
        }
        if (!tip_logic::Toggles(CurrentMode())) return false;
        const char* mode = command == GlobalCommand::Hiragana ? "hiragana" :
                           command == GlobalCommand::Katakana ? "katakana" :
                           command == GlobalCommand::FullAlnum ? "full_alnum" : nullptr;
        bool direct = command == GlobalCommand::Toggle ? !direct_ : command == GlobalCommand::Off;
        if (mode) {
            pending_mode_seq_ = SendRequest("set_mode", "\"mode\":" + tip_json::Quote(mode));
            if (!pending_mode_seq_) input_mode_ = mode;
        } else {
            pending_mode_seq_ = SendRequest("set_direct", direct ? "\"direct\":true,\"commit\":true" :
                                                                  "\"direct\":false");
        }
        if (!pending_mode_seq_) {
            direct_ = direct;
            FinishLocal();
            UpdateLangBar();
        }
        return true;
    }

    void PreserveKeys() {
        ITfKeystrokeMgr* km = nullptr;
        if (FAILED(tm_->QueryInterface(IID_ITfKeystrokeMgr, (void**)&km))) return;
        UnpreserveKeys(km);
        for (const auto& [code, command] : keymap_.global) {
            unsigned mods = code >> 8;
            if ((mods & 6) != 4 || preserved_.size() == 40) continue;  // Alt without Ctrl
            GUID guid = GUID_YuragiToggle;
            guid.Data1 += (ULONG)preserved_.size();
            UINT vk = code & 0xFF;
            UINT flags = TF_MOD_ALT | ((mods & 1) ? TF_MOD_SHIFT : 0);
            if (vk == VK_OEM_3 && mods == 4) { vk = VK_KANJI; flags = TF_MOD_IGNORE_ALL_MODIFIER; }
            if (vk == VK_CAPITAL && mods == 4) { vk = 0xF1; flags = TF_MOD_IGNORE_ALL_MODIFIER; }
            TF_PRESERVEDKEY preserved{vk, flags};
            if (SUCCEEDED(km->PreserveKey(client_, guid, &preserved, nullptr, 0)))
                preserved_.push_back({guid, preserved, code});
        }
        km->Release();
    }
    void UnpreserveKeys(ITfKeystrokeMgr* km) {
        for (const auto& key : preserved_) km->UnpreserveKey(key.guid, &key.key);
        preserved_.clear();
    }

    // -- the candidate list and the notice --------------------------------------------------------
    void HideCands() { candidate_.Clear(); }
    void ShowNotice(Notice n);
    void HideNotice() {
        notice_ = Notice::None;
        notice_popup_.Clear();
        if (hwnd_) KillTimer(hwnd_, kTimerNotice);
    }

    // -- layout sink ----------------------------------------------------------------------------
    void AdviseLayout(ITfContext* ctx) {
        UnadviseLayout();
        ITfSource* src = nullptr;
        if (SUCCEEDED(ctx->QueryInterface(IID_ITfSource, (void**)&src))) {
            if (SUCCEEDED(src->AdviseSink(IID_ITfTextLayoutSink, (ITfTextLayoutSink*)this,
                                          &layout_cookie_))) {
                layout_ctx_ = ctx;
                layout_ctx_->AddRef();
            }
            src->Release();
        }
    }
    void UnadviseLayout() {
        if (!layout_ctx_) return;
        ITfSource* src = nullptr;
        if (SUCCEEDED(layout_ctx_->QueryInterface(IID_ITfSource, (void**)&src))) {
            src->UnadviseSink(layout_cookie_);
            src->Release();
        }
        layout_ctx_->Release();
        layout_ctx_ = nullptr;
        layout_cookie_ = TF_INVALID_COOKIE;
    }

    void UpdateLangBar() {
        if (lb_sink_) lb_sink_->OnUpdate(TF_LBI_ICON | TF_LBI_TEXT | TF_LBI_TOOLTIP);
    }

    void ShowMenu(HWND owner, POINT pt, UINT vertical_align) {
        if (!owner || GetWindowThreadProcessId(owner, nullptr) != GetCurrentThreadId()) return;
        HMENU popup = CreatePopupMenu();
        if (!popup) return;
        for (int item : tip_logic::MenuFor(CurrentMode())) {
            bool grayed;
            const wchar_t* text = MenuText(item, &grayed);
            AppendMenuW(popup, MF_STRING | (grayed ? MF_GRAYED : 0), item, text);
        }
        UINT align = GetSystemMetrics(SM_MENUDROPALIGNMENT) ? TPM_RIGHTALIGN : TPM_LEFTALIGN;
        UINT id = (UINT)TrackPopupMenuEx(popup, align | vertical_align | TPM_RETURNCMD |
                                         TPM_NONOTIFY | TPM_RIGHTBUTTON, pt.x, pt.y, owner, nullptr);
        DestroyMenu(popup);
        if (id && tm_) OnMenuSelect(id);
    }
    void ShowKeyboardMenu() {
        if (!menu_generation_) return;
        // TrackPopupMenuEx runs a nested message loop. Start it outside the TSF
        // key callback, and wait until it closes before handling buffered keys.
        if (*menu_generation_ == focus_generation_ && RootOwner() && !FocusChanged() &&
            Eligible() && ScopeAllowsInput()) {
            HWND owner = GetFocus();
            POINT pt{};
            GUITHREADINFO gui{sizeof(gui)};
            if (GetGUIThreadInfo(GetCurrentThreadId(), &gui) && gui.hwndCaret == owner)
                pt = {gui.rcCaret.left, gui.rcCaret.bottom};
            if (owner && ClientToScreen(owner, &pt)) ShowMenu(owner, pt, TPM_TOPALIGN);
        }
        menu_generation_.reset();
        if (hwnd_) PostMessageW(hwnd_, kKeysMessage, 0, 0);
    }

    LONG refs_ = 1;
    ITfThreadMgr* tm_ = nullptr;
    TfClientId client_ = TF_CLIENTID_NULL;
    DWORD cookie_tm_ = TF_INVALID_COOKIE;
    TfGuidAtom atoms_[3] = {TF_INVALID_GUIDATOM, TF_INVALID_GUIDATOM, TF_INVALID_GUIDATOM};
    TipConfig settings_;
    std::shared_ptr<CompositionState> state_;
    RetiredStates retired_;
    BrokerLink link_;
    Link link_state_ = Link::Connecting;
    std::string broker_state_;
    tip_logic::InFlight in_flight_;
    long long stale_upto_ = 0;  // last sequence issued before local composition was retired
    UINT_PTR reply_timer_ = 0, next_reply_timer_ = kTimerCarry;
    tip_logic::ConnectGate connect_gate_;
    HWND hwnd_ = nullptr;
    TipPopup candidate_, notice_popup_{true};
    Scope scope_ = Scope::Unknown;
    ITfContext* scope_ctx_ = nullptr;
    uint64_t focus_generation_ = 0;
    DWORD edit_cookie_ = TF_INVALID_COOKIE;
    ITfContext* layout_ctx_ = nullptr;
    DWORD layout_cookie_ = TF_INVALID_COOKIE;
    Notice notice_ = Notice::None;
    bool stopped_told_ = false;
    const char* admin_request_ = nullptr;  // waiting for the connection (OpenAdmin)
    bool direct_ = false;
    std::string input_mode_ = "hiragana";
    bool composing_ = false, pending_ = false, timer_pending_ = false;
    bool fsm_idle_ = true;
    tip_logic::KeyTable keymap_ = tip_logic::DefaultKeyTable();
    tip_logic::Phase phase_ = tip_logic::Phase::Empty;
    std::optional<TestedKey> tested_;
    std::optional<Stroke> tested_up_, replay_, retry_replay_;
    std::array<std::optional<tip_logic::Chord>, 256> down_sent_{};
    std::map<long long, SentKey> sent_keys_;
    std::deque<Stroke> buffered_, releases_;
    tip_logic::Carry carry_;
    std::vector<Registration> preserved_;
    long long pending_mode_seq_ = 0, mode_edit_seq_ = 0;
    std::optional<uint64_t> menu_generation_;
    bool langbar_ = false;
    ITfLangBarItemSink* lb_sink_ = nullptr;
};

// Read-only sessions for the input scope, notices, and the input's left context.
class ReadSession final : public ITfEditSession {
public:
    enum Kind { Scope, Caret, Document };
    ReadSession(Kind kind, Tip* tip, ITfContext* ctx)
        : kind_(kind), tip_(tip), ctx_(ctx), generation_(tip->focus_generation_) {
        tip_->AddRef();
        ctx_->AddRef();
    }
    ~ReadSession() {
        ctx_->Release();
        tip_->Release();
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID id, void** pp) override {
        if (!pp) return E_POINTER;
        *pp = nullptr;
        if (id != IID_IUnknown && id != IID_ITfEditSession) return E_NOINTERFACE;
        *pp = static_cast<ITfEditSession*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n = InterlockedDecrement(&refs_); if (!n) delete this; return n;
    }
    HRESULT STDMETHODCALLTYPE DoEditSession(TfEditCookie ec) override {
        if (kind_ == Scope) {
            tip_->ScopeChecked(ctx_, generation_, SelectionScope(ctx_, ec));
            return S_OK;
        }
        if (kind_ == Document) {
            ReadDocument(ec);
            return S_OK;
        }
        ITfRange* caret = nullptr;
        auto state = tip_->State();
        if (state && state->composition && state->ctx == ctx_) {
            if (SUCCEEDED(state->composition->GetRange(&caret))) caret->Collapse(ec, TF_ANCHOR_END);
        } else {
            TF_SELECTION selection{};
            ULONG fetched = 0;
            if (SUCCEEDED(ctx_->GetSelection(ec, TF_DEFAULT_SELECTION, 1, &selection, &fetched)) &&
                fetched)
                caret = selection.range;
        }
        if (caret) {
            tip_->PlaceNotice(ec, ctx_, caret);
            caret->Release();
        }
        return S_OK;
    }

    tip_logic::KeyContext context;
    bool called_get_text = false;

private:
    void ReadDocument(TfEditCookie ec) {
        if (generation_ != tip_->focus_generation_ || !tip_->CanReadContext(ctx_) ||
            tip_->FocusChanged()) return;

        TF_SELECTION selection{};
        ULONG fetched = 0;
        if (FAILED(ctx_->GetSelection(ec, TF_DEFAULT_SELECTION, 1, &selection, &fetched)) ||
            !fetched) return;
        auto release = [](ITfRange* range) { range->Release(); };
        std::unique_ptr<ITfRange, decltype(release)> selected(selection.range, release);
        ITfRange* clone = nullptr;
        if (FAILED(selected->Clone(&clone))) return;
        std::unique_ptr<ITfRange, decltype(release)> left(clone, release);
        if (FAILED(left->Collapse(ec, TF_ANCHOR_START)) ||
            FieldScope(ctx_, ec, left.get()) != tip_logic::Scope::Allowed ||
            generation_ != tip_->focus_generation_ || !tip_->CanReadContext(ctx_)) return;

        auto state = tip_->State();
        BOOL empty = FALSE;
        if (SUCCEEDED(selected->IsEmpty(ec, &empty))) {
            if (!empty) {
                if (state) state->BreakContinuity();
                context.disconnected = true;
            } else if (state && state->commit_end) {
                LONG order;
                if (SUCCEEDED(left->CompareStart(ec, state->commit_end, TF_ANCHOR_START, &order))) {
                    if (order == 0) context.after_commit_seq = state->commit_seq;
                    else state->BreakContinuity();
                }
            }
        }
        constexpr LONG limit = (LONG)tip_logic::CONTEXT_UNITS;
        LONG shifted;
        if (FAILED(left->ShiftStart(ec, -limit, &shifted, nullptr)) ||
            generation_ != tip_->focus_generation_ || tip_->FocusChanged()) return;
        wchar_t buffer[limit + 1];
        ULONG count = 0;
        called_get_text = true;
        // ShiftStart measured the length of this range in UTF-16 units.
        if (FAILED(left->GetText(ec, 0, buffer, limit, &count)) || count != (ULONG)-shifted)
            return;
        buffer[count] = L'\0';
        bool clipped = shifted == -limit;
        if (clipped && buffer[0] >= 0xdc00 && buffer[0] <= 0xdfff) {
            // A lone low surrogate at the very start is malformed text.
            ITfRange* start = nullptr;
            if (FAILED(ctx_->GetStart(ec, &start))) return;
            LONG order;
            HRESULT hr = left->CompareStart(ec, start, TF_ANCHOR_START, &order);
            start->Release();
            if (FAILED(hr)) return;
            clipped = order > 0;
        }
        auto tail = tip_logic::ContextTail(std::wstring_view(buffer, count), clipped);
        if (!tail) return;
        if (tail->empty()) {
            context.text = "";
            return;
        }
        char utf8[3 * limit];  // At most three UTF-8 bytes per UTF-16 unit.
        int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, tail->data(), (int)tail->size(),
                                       utf8, sizeof(utf8), nullptr, nullptr);
        if (size != 0) context.text.emplace(utf8, size);
    }

    LONG refs_ = 1;
    Kind kind_;
    Tip* tip_;
    ITfContext* ctx_;
    uint64_t generation_;
};

// DESIGN「パスワード欄」: once per focus. Until the answer is known the field is "being looked
// at" and keys pass through.
void Tip::CheckScope() {
    ++focus_generation_;
    UnadviseTextEdit();
    if (scope_ctx_) scope_ctx_->Release();
    scope_ctx_ = FocusContext();
    scope_ = Scope::Unknown;
    if (!scope_ctx_ || client_ == TF_CLIENTID_NULL) return;
    if (settings_.document_context) {
        ITfSource* src = nullptr;
        if (SUCCEEDED(scope_ctx_->QueryInterface(IID_ITfSource, (void**)&src))) {
            DWORD cookie = TF_INVALID_COOKIE;
            if (SUCCEEDED(src->AdviseSink(IID_ITfTextEditSink, (ITfTextEditSink*)this, &cookie)))
                edit_cookie_ = cookie;
            src->Release();
        }
    }
    auto* es = new ReadSession(ReadSession::Scope, this, scope_ctx_);
    HRESULT result = S_OK;
    HRESULT hr = scope_ctx_->RequestEditSession(client_, es, TF_ES_SYNC | TF_ES_READ, &result);
    if (hr == TF_E_SYNCHRONOUS || result == TF_E_SYNCHRONOUS)
        scope_ctx_->RequestEditSession(client_, es, TF_ES_ASYNC | TF_ES_READ, &result);
    es->Release();
}

tip_logic::KeyContext Tip::ReadContext(ITfContext* ctx) {
    auto* es = new ReadSession(ReadSession::Document, this, ctx);
    ULONGLONG start = NowMs();
    HRESULT result = E_FAIL;
    HRESULT hr = ctx->RequestEditSession(client_, es, TF_ES_SYNC | TF_ES_READ, &result);
    tip_logic::KeyContext data;
    if (hr == S_OK && result == S_OK) data = std::move(es->context);
    if (state_ ? state_->disconnected : edit_cookie_ != TF_INVALID_COOKIE)
        data.disconnected = true;
    Log(L"document context t=%llu elapsed=%llu get_text=%d acquired=%d hr=%08lx result=%08lx",
        start, NowMs() - start, es->called_get_text, data.text.has_value(), hr, result);
    es->Release();
    return data;
}

void Tip::ShowNotice(Notice n) {
    if (!hwnd_) return;
    notice_ = n;
    notice_popup_.SetRows({{NoticeText(n), {}}});
    KillTimer(hwnd_, kTimerNotice);
    if (n == Notice::Stopped) ArmTimer(kTimerNotice, NowMs() + tip_logic::NOTICE_SHOW_MS);
    // Placed under the caret by a read-only session.
    ITfContext* ctx = FocusContext();
    if (!ctx) return;
    auto* es = new ReadSession(ReadSession::Caret, this, ctx);
    HRESULT result = S_OK;
    ctx->RequestEditSession(client_, es, TF_ES_ASYNCDONTCARE | TF_ES_READ, &result);
    es->Release();
    ctx->Release();
}

class Factory final : public IClassFactory {
public:
    LONG refs_ = 1;
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** pp) override {
        if (!pp) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *pp = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *pp = nullptr;
        return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&refs_); }
    ULONG STDMETHODCALLTYPE Release() override {
        LONG n = InterlockedDecrement(&refs_);
        if (!n) delete this;
        return n;
    }
    HRESULT STDMETHODCALLTYPE CreateInstance(IUnknown* outer, REFIID riid, void** pp) override {
        if (outer) return CLASS_E_NOAGGREGATION;
        auto* t = new Tip();
        HRESULT hr = t->QueryInterface(riid, pp);
        t->Release();
        return hr;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override {
        if (lock) InterlockedIncrement(&g_locks);
        else InterlockedDecrement(&g_locks);
        return S_OK;
    }
};

// -- registration (DESIGN「共通の仕組み」: run elevated by packaging/elevated.ps1, then read back) ----------

static HRESULT SetSz(HKEY root, const wchar_t* sub, const wchar_t* name, const wchar_t* val) {
    HKEY k = nullptr;
    LONG e = RegCreateKeyExW(root, sub, 0, nullptr, 0, KEY_WRITE, nullptr, &k, nullptr);
    if (e != ERROR_SUCCESS) return HRESULT_FROM_WIN32(e);
    e = RegSetValueExW(k, name, 0, REG_SZ, (const BYTE*)val, (DWORD)((wcslen(val) + 1) * 2));
    RegCloseKey(k);
    return HRESULT_FROM_WIN32(e);
}

static std::wstring DllPath() {
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(g_hinst, path, MAX_PATH);
    return path;
}

static std::wstring GuidStr(const GUID& g) {
    wchar_t s[64];
    StringFromGUID2(g, s, 64);
    return s;
}

static std::wstring ClsidKey() { return L"Software\\Classes\\CLSID\\" + GuidStr(CLSID_YuragiTip); }

// The machine's registration only (every user's applications load the DLL).
static HRESULT RegisterCom() {
    std::wstring clsid = ClsidKey();
    HRESULT hr = SetSz(HKEY_LOCAL_MACHINE, clsid.c_str(), nullptr, L"ゆらぎ");
    if (FAILED(hr)) return hr;
    std::wstring inproc = clsid + L"\\InprocServer32";
    hr = SetSz(HKEY_LOCAL_MACHINE, inproc.c_str(), nullptr, DllPath().c_str());
    if (FAILED(hr)) return hr;
    return SetSz(HKEY_LOCAL_MACHINE, inproc.c_str(), L"ThreadingModel", L"Apartment");
}

static HRESULT RegisterCategories(BOOL add) {
    ITfCategoryMgr* cat = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_ITfCategoryMgr, (void**)&cat);
    if (FAILED(hr)) return hr;
    for (const GUID& g : kCats) {
        HRESULT one = add ? cat->RegisterCategory(CLSID_YuragiTip, g, CLSID_YuragiTip)
                          : cat->UnregisterCategory(CLSID_YuragiTip, g, CLSID_YuragiTip);
        if (FAILED(one) && SUCCEEDED(hr)) hr = one;
    }
    cat->Release();
    return hr;
}

static HRESULT RegisterProfile(BOOL add) {
    // CorvusSKK / SampleIME: ProfileMgr only. The old Register+AddLanguageProfile
    // pair plus this API together made Win11 attach the wrong CJK engine.
    ITfInputProcessorProfileMgr* mgr = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_ITfInputProcessorProfileMgr, (void**)&mgr);
    if (FAILED(hr) || !mgr) return FAILED(hr) ? hr : E_FAIL;
    LANGID ja = MAKELANGID(LANG_JAPANESE, SUBLANG_JAPANESE_JAPAN);
    if (add) {
        std::wstring path = DllPath();
        hr = mgr->RegisterProfile(CLSID_YuragiTip, ja, GUID_YuragiProfile, L"ゆらぎ",
                                  (ULONG)wcslen(L"ゆらぎ"), path.c_str(), (ULONG)path.size(),
                                  (ULONG)-IDI_YURAGI,  // negative: a resource ID, as ExtractIcon reads it
                                  nullptr, 0, TRUE, 0);
        mgr->Release();
        HRESULT categories = RegisterCategories(TRUE);
        return FAILED(hr) ? hr : categories;
    }
    // Categories first: UnregisterProfile deletes the TIP's whole key, categories
    // included, after which UnregisterCategory fails with E_FAIL.
    HRESULT categories = RegisterCategories(FALSE);
    hr = mgr->UnregisterProfile(CLSID_YuragiTip, ja, GUID_YuragiProfile, TF_URP_ALLPROFILES);
    mgr->Release();
    return FAILED(categories) ? categories : hr;
}

BOOL APIENTRY DllMain(HINSTANCE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) g_hinst = h;
    return TRUE;
}

STDAPI DllCanUnloadNow() { return g_locks ? S_FALSE : S_OK; }

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    if (!IsEqualCLSID(rclsid, CLSID_YuragiTip)) return CLASS_E_CLASSNOTAVAILABLE;
    auto* f = new Factory();
    HRESULT hr = f->QueryInterface(riid, ppv);
    f->Release();
    return hr;
}

STDAPI DllRegisterServer() {
    HRESULT co = CoInitialize(nullptr);
    HRESULT hr = RegisterCom();
    if (SUCCEEDED(hr)) hr = RegisterProfile(TRUE);
    if (co == S_OK) CoUninitialize();
    return hr;
}

// Every step runs; the first failure is returned (DESIGN「守ること」6: no false "OK").
// The profile is shared by the 32- and 64-bit builds (DESIGN「32 ビットのアプリ」): the
// second to be unregistered finds it gone, which is not a failure.
STDAPI DllUnregisterServer() {
    HRESULT co = CoInitialize(nullptr);
    std::wstring tip_key = L"Software\\Microsoft\\CTF\\TIP\\" + GuidStr(CLSID_YuragiTip);
    HKEY key = nullptr;
    HRESULT hr = S_OK;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, tip_key.c_str(), 0, KEY_READ, &key) == ERROR_SUCCESS) {
        RegCloseKey(key);
        hr = RegisterProfile(FALSE);
    }
    LONG e = RegDeleteTreeW(HKEY_LOCAL_MACHINE, ClsidKey().c_str());
    if (e != ERROR_SUCCESS && e != ERROR_FILE_NOT_FOUND && SUCCEEDED(hr)) hr = HRESULT_FROM_WIN32(e);
    if (co == S_OK) CoUninitialize();
    return hr;
}
