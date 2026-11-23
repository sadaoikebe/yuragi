// The key probe: a small text service, separate from ゆらぎ, for measuring how TSF calls a
// keyboard TIP (docs/keybind/windows.md). See tools/keyprobe/README.md.
//
// While %USERPROFILE%\.yuragi-ime\probe.json exists with "on": true, it eats exactly the
// chords the file lists, registers the listed PreservedKeys, and logs every key callback
// (and, from a thread keyboard hook, every key message the thread retrieves) to probe.log
// next to it. Otherwise it eats nothing and logs nothing. The file is re-read every 200 ms.
// A chord is [vk, mods] with shift=1, ctrl=2, alt=4 (16 = any modifiers, for preserve).
//   {"on":true,"seq":1,"eat":[[85,2]],"test_only":[[116,0]],"preserve":[[25,16]]}

#include <windows.h>
#include <olectl.h>
#include <initguid.h>
#include <msctf.h>

#include <cstdarg>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

#include "tip_json.h"

// {B3F0A501-6C2E-4D8A-9B47-2E5D1C0F7A11}
static const CLSID CLSID_KeyProbeTip = {
    0xb3f0a501, 0x6c2e, 0x4d8a, {0x9b, 0x47, 0x2e, 0x5d, 0x1c, 0x0f, 0x7a, 0x11}};
// {B3F0A502-6C2E-4D8A-9B47-2E5D1C0F7A11}
static const GUID GUID_KeyProbeProfile = {
    0xb3f0a502, 0x6c2e, 0x4d8a, {0x9b, 0x47, 0x2e, 0x5d, 0x1c, 0x0f, 0x7a, 0x11}};
// The categories of ゆらぎ that concern keys (not its display attributes), so TSF treats both alike.
static const GUID kCats[] = {
    GUID_TFCAT_TIP_KEYBOARD,
    GUID_TFCAT_TIPCAP_COMLESS,
    GUID_TFCAT_TIPCAP_INPUTMODECOMPARTMENT,
    GUID_TFCAT_TIPCAP_IMMERSIVESUPPORT,
    GUID_TFCAT_TIPCAP_SYSTRAYSUPPORT,
};
static const wchar_t kName[] = L"キーの確認（keyprobe）";

static LONG g_locks = 0;
static HINSTANCE g_hinst = nullptr;

static GUID PreserveGuid(size_t i) {
    // {B3F0A6xx-6C2E-4D8A-9B47-2E5D1C0F7A11}
    return {0xb3f0a600 + (unsigned long)i, 0x6c2e, 0x4d8a, {0x9b, 0x47, 0x2e, 0x5d, 0x1c, 0x0f, 0x7a, 0x11}};
}
static const size_t kPreserveGuids = 40;

static UINT VkOf(WPARAM w) { return (UINT)(w & 0xFF); }

static unsigned HeldMods() {
    return ((GetKeyState(VK_SHIFT) & 0x8000) ? 1u : 0u) | ((GetKeyState(VK_CONTROL) & 0x8000) ? 2u : 0u) |
           ((GetKeyState(VK_MENU) & 0x8000) ? 4u : 0u) |
           (((GetKeyState(VK_LWIN) | GetKeyState(VK_RWIN)) & 0x8000) ? 8u : 0u);
}

static std::wstring ProfilePath(const wchar_t* name) {
    wchar_t profile[MAX_PATH];
    DWORD n = GetEnvironmentVariableW(L"USERPROFILE", profile, MAX_PATH);
    if (!n || n >= MAX_PATH) return {};
    return std::wstring(profile) + L"\\.yuragi-ime\\" + name;
}

static void ProbeLog(const wchar_t* fmt, ...) {
    static std::wstring path = ProfilePath(L"probe.log");
    static std::wstring exe = [] {
        wchar_t p[MAX_PATH];
        GetModuleFileNameW(nullptr, p, MAX_PATH);
        std::wstring s(p);
        size_t slash = s.find_last_of(L"\\/");
        return slash == std::wstring::npos ? s : s.substr(slash + 1);
    }();
    if (path.empty()) return;
    wchar_t body[1024];
    va_list ap;
    va_start(ap, fmt);
    vswprintf_s(body, fmt, ap);
    va_end(ap);
    wchar_t line[1400];
    swprintf_s(line, L"%llu pid=%lu tid=%lu exe=%s %s\n", GetTickCount64(), GetCurrentProcessId(),
               GetCurrentThreadId(), exe.c_str(), body);
    int bytes = WideCharToMultiByte(CP_UTF8, 0, line, -1, nullptr, 0, nullptr, nullptr);
    std::string utf8(bytes > 0 ? bytes - 1 : 0, '\0');
    if (bytes > 1) WideCharToMultiByte(CP_UTF8, 0, line, -1, &utf8[0], bytes, nullptr, nullptr);
    HANDLE f = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                           nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(f, utf8.data(), (DWORD)utf8.size(), &written, nullptr);
    CloseHandle(f);
}

// Every key message this thread retrieves, to compare with the TSF callbacks.
static LRESULT CALLBACK KeyboardHook(int code, WPARAM w, LPARAM l) {
    if (code >= 0)
        ProbeLog(L"Hook code=%d vk=0x%02X lp=0x%08X scan=0x%02X prev=%d up=%d", code, (unsigned)(w & 0xFFFF),
                 (unsigned)l, (unsigned)((l >> 16) & 0xFF), (int)((l >> 30) & 1), (int)((l >> 31) & 1));
    return CallNextHookEx(nullptr, code, w, l);
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

struct ProbeConfig {
    using Chords = std::vector<std::pair<UINT, unsigned>>;
    bool on = false;
    long long seq = 0;
    Chords eat, test_only, preserve;

    static bool Read(const tip_json::Value& v, Chords& out) {
        out.clear();
        for (const auto& c : v.array) {
            long long vk, mods;
            if (c.kind != tip_json::Value::Array || c.array.size() != 2 || !c.array[0].Int(vk) ||
                !c.array[1].Int(mods) || vk <= 0 || vk > 255 || mods < 0 || mods > 31)
                return false;
            out.push_back({(UINT)vk, (unsigned)mods});
        }
        return true;
    }
    // False when the file is missing or unreadable: the probe is then off.
    bool Load() {
        *this = ProbeConfig();
        tip_json::Value v;
        if (!ReadJsonFile(ProfilePath(L"probe.json"), v)) return false;
        const auto& on_value = v.Get("on");
        on = on_value.kind == tip_json::Value::Boolean && on_value.boolean;
        v.Get("seq").Int(seq);
        if (!Read(v.Get("eat"), eat) || !Read(v.Get("test_only"), test_only) || !Read(v.Get("preserve"), preserve)) {
            on = false;
            return false;
        }
        return true;
    }
    static bool Has(const Chords& list, UINT vk, unsigned mods) {
        for (const auto& c : list)
            if (c.first == vk && c.second == mods) return true;
        return false;
    }
};

static void SetKeyboardOpen(ITfThreadMgr* tm, TfClientId id) {
    ITfCompartmentMgr* cm = nullptr;
    if (FAILED(tm->QueryInterface(IID_ITfCompartmentMgr, (void**)&cm)) || !cm) return;
    ITfCompartment* c = nullptr;
    if (SUCCEEDED(cm->GetCompartment(GUID_COMPARTMENT_KEYBOARD_OPENCLOSE, &c)) && c) {
        VARIANT v;
        VariantInit(&v);
        v.vt = VT_I4;
        v.lVal = 1;
        c->SetValue(id, &v);
        c->Release();
    }
    cm->Release();
}

class ProbeTip final : public ITfTextInputProcessorEx, public ITfKeyEventSink {
public:
    ProbeTip() { InterlockedIncrement(&g_locks); }
    ~ProbeTip() { InterlockedDecrement(&g_locks); }

    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** pp) override {
        if (!pp) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_ITfTextInputProcessor || riid == IID_ITfTextInputProcessorEx)
            *pp = (ITfTextInputProcessorEx*)this;
        else if (riid == IID_ITfKeyEventSink)
            *pp = (ITfKeyEventSink*)this;
        else {
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

    // -- ITfTextInputProcessorEx ------------------------------------------------------------
    HRESULT STDMETHODCALLTYPE Activate(ITfThreadMgr* tm, TfClientId id) override { return ActivateEx(tm, id, 0); }
    HRESULT STDMETHODCALLTYPE ActivateEx(ITfThreadMgr* tm, TfClientId id, DWORD) override {
        tm_ = tm;
        tm_->AddRef();
        client_ = id;
        ITfKeystrokeMgr* km = nullptr;
        if (SUCCEEDED(tm_->QueryInterface(IID_ITfKeystrokeMgr, (void**)&km))) {
            km->AdviseKeyEventSink(client_, this, TRUE);
            km->Release();
        }
        SetKeyboardOpen(tm_, client_);
        EnsureWindow();
        Tick();
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Deactivate() override {
        if (hwnd_) {
            KillTimer(hwnd_, kTimer);
            DestroyWindow(hwnd_);
            hwnd_ = nullptr;
        }
        if (hook_) {
            UnhookWindowsHookEx(hook_);
            hook_ = nullptr;
        }
        if (tm_) {
            ITfKeystrokeMgr* km = nullptr;
            if (SUCCEEDED(tm_->QueryInterface(IID_ITfKeystrokeMgr, (void**)&km))) {
                Unpreserve(km);
                km->UnadviseKeyEventSink(client_);
                km->Release();
            }
            tm_->Release();
            tm_ = nullptr;
        }
        if (watching_) ProbeLog(L"Deactivate");
        config_ = ProbeConfig();
        watching_ = loaded_ = false;
        client_ = TF_CLIENTID_NULL;
        return S_OK;
    }

    // -- ITfKeyEventSink ---------------------------------------------------------------------
    HRESULT STDMETHODCALLTYPE OnSetFocus(BOOL) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnTestKeyDown(ITfContext* ctx, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        if (!config_.on) return S_OK;
        UINT vk = VkOf(w);
        unsigned mods = HeldMods();
        *e = ProbeConfig::Has(config_.eat, vk, mods) || ProbeConfig::Has(config_.test_only, vk, mods);
        KeyLog(L"TestKeyDown", ctx, w, l, *e);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnTestKeyUp(ITfContext* ctx, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        if (!config_.on) return S_OK;
        *e = down_[VkOf(w)] ? TRUE : FALSE;
        KeyLog(L"TestKeyUp", ctx, w, l, *e);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnKeyDown(ITfContext* ctx, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        if (!config_.on) return S_OK;
        UINT vk = VkOf(w);
        down_[vk] = ProbeConfig::Has(config_.eat, vk, HeldMods());
        *e = down_[vk] ? TRUE : FALSE;
        KeyLog(L"KeyDown", ctx, w, l, *e);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnKeyUp(ITfContext* ctx, WPARAM w, LPARAM l, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        if (!config_.on) return S_OK;
        UINT vk = VkOf(w);
        *e = down_[vk] ? TRUE : FALSE;
        down_[vk] = false;
        KeyLog(L"KeyUp", ctx, w, l, *e);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE OnPreservedKey(ITfContext*, REFGUID guid, BOOL* e) override {
        if (!e) return E_INVALIDARG;
        *e = FALSE;
        if (!config_.on) return S_OK;
        long index = -1;
        for (size_t i : preserved_index_)
            if (guid == PreserveGuid(i)) index = (long)i;
        *e = TRUE;
        ProbeLog(L"PreservedKey index=%ld mods=%u ret=1", index, HeldMods());
        return S_OK;
    }

private:
    static const UINT_PTR kTimer = 1;

    void KeyLog(const wchar_t* what, ITfContext* ctx, WPARAM w, LPARAM l, BOOL ret) {
        ProbeLog(L"%s vk=0x%02X lp=0x%08X scan=0x%02X ext=%d prev=%d rep=%u mods=%u ret=%d ctx=%d "
                 L"ks_oem3=%04X ks_kanji=%04X ks_capital=%04X ks_kana=%04X ks_menu=%04X",
                 what, (unsigned)(w & 0xFFFF), (unsigned)l, (unsigned)((l >> 16) & 0xFF), (int)((l >> 24) & 1),
                 (int)((l >> 30) & 1), (unsigned)(l & 0xFFFF), HeldMods(), ret ? 1 : 0, ctx ? 1 : 0,
                 (unsigned)(USHORT)GetKeyState(VK_OEM_3), (unsigned)(USHORT)GetKeyState(VK_KANJI),
                 (unsigned)(USHORT)GetKeyState(VK_CAPITAL), (unsigned)(USHORT)GetKeyState(VK_KANA),
                 (unsigned)(USHORT)GetKeyState(VK_MENU));
    }

    static LRESULT CALLBACK WndProc(HWND h, UINT m, WPARAM w, LPARAM l) {
        if (m == WM_TIMER && w == kTimer) {
            if (auto* self = (ProbeTip*)GetWindowLongPtrW(h, GWLP_USERDATA)) self->Tick();
            return 0;
        }
        return DefWindowProcW(h, m, w, l);
    }
    void EnsureWindow() {
        static const wchar_t kClass[] = L"YuragiKeyProbeTip";
        WNDCLASSW wc{};
        wc.lpfnWndProc = WndProc;
        wc.hInstance = g_hinst;
        wc.lpszClassName = kClass;
        RegisterClassW(&wc);  // fails harmlessly when already registered in this process
        hwnd_ = CreateWindowExW(0, kClass, L"", 0, 0, 0, 0, 0, HWND_MESSAGE, nullptr, g_hinst, nullptr);
        if (hwnd_) SetWindowLongPtrW(hwnd_, GWLP_USERDATA, (LONG_PTR)this);
    }

    // Polled from the window, so (un)registering never runs inside a key callback.
    void Tick() {
        if (!hwnd_ || !tm_) return;
        WIN32_FILE_ATTRIBUTE_DATA a{};
        bool exists = GetFileAttributesExW(ProfilePath(L"probe.json").c_str(), GetFileExInfoStandard, &a) != 0;
        FILETIME stamp = exists ? a.ftLastWriteTime : FILETIME{};
        DWORD size = exists ? a.nFileSizeLow : 0;
        if (!loaded_ || CompareFileTime(&stamp, &stamp_) != 0 || size != size_) {
            loaded_ = true;
            stamp_ = stamp;
            size_ = size;
            ProbeConfig old = config_;
            bool ok = exists && config_.Load();
            if (!exists) config_ = ProbeConfig();
            // Log only while the probe is on: with no file or "on": false, nothing is written.
            if (config_.on && !watching_) ProbeLog(L"ActivateEx client=%u", (unsigned)client_);
            watching_ = config_.on;
            Apply(old, ok);
        }
        SetTimer(hwnd_, kTimer, 200, nullptr);
    }
    void Apply(const ProbeConfig& old, bool ok) {
        ITfKeystrokeMgr* km = nullptr;
        if (FAILED(tm_->QueryInterface(IID_ITfKeystrokeMgr, (void**)&km))) return;
        if (config_.on != old.on || config_.seq != old.seq || config_.preserve != old.preserve) {
            Unpreserve(km);
            for (size_t i = 0; config_.on && i < config_.preserve.size() && i < kPreserveGuids; ++i) {
                TF_PRESERVEDKEY k{config_.preserve[i].first, 0};
                unsigned m = config_.preserve[i].second;
                if (m & 1) k.uModifiers |= TF_MOD_SHIFT;
                if (m & 2) k.uModifiers |= TF_MOD_CONTROL;
                if (m & 4) k.uModifiers |= TF_MOD_ALT;
                if (m & 16) k.uModifiers = TF_MOD_IGNORE_ALL_MODIFIER;
                HRESULT hr = km->PreserveKey(client_, PreserveGuid(i), &k, L"probe", 5);
                ProbeLog(L"PreserveKey index=%zu vk=0x%02X mods=%u hr=0x%08lX", i, k.uVKey, m, (unsigned long)hr);
                if (SUCCEEDED(hr)) {
                    preserved_.push_back(k);
                    preserved_index_.push_back(i);
                }
            }
        }
        km->Release();
        for (bool& d : down_) d = false;
        if (config_.on && !hook_) hook_ = SetWindowsHookExW(WH_KEYBOARD, KeyboardHook, nullptr, GetCurrentThreadId());
        if (!config_.on && hook_) {
            UnhookWindowsHookEx(hook_);
            hook_ = nullptr;
        }
        if (watching_)
            ProbeLog(L"config ok=%d on=%d seq=%lld eat=%zu test_only=%zu preserve=%zu registered=%zu", ok ? 1 : 0,
                     config_.on ? 1 : 0, config_.seq, config_.eat.size(), config_.test_only.size(),
                     config_.preserve.size(), preserved_.size());
    }
    void Unpreserve(ITfKeystrokeMgr* km) {
        for (size_t i = 0; i < preserved_.size(); ++i) {
            HRESULT hr = km->UnpreserveKey(PreserveGuid(preserved_index_[i]), &preserved_[i]);
            if (watching_) ProbeLog(L"UnpreserveKey index=%zu hr=0x%08lX", preserved_index_[i], (unsigned long)hr);
        }
        preserved_.clear();
        preserved_index_.clear();
    }

    LONG refs_ = 1;
    ITfThreadMgr* tm_ = nullptr;
    TfClientId client_ = TF_CLIENTID_NULL;
    HWND hwnd_ = nullptr;
    HHOOK hook_ = nullptr;
    ProbeConfig config_;
    bool watching_ = false, loaded_ = false;
    FILETIME stamp_{};
    DWORD size_ = 0;
    bool down_[256]{};
    std::vector<TF_PRESERVEDKEY> preserved_;
    std::vector<size_t> preserved_index_;
};

class Factory final : public IClassFactory {
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** pp) override {
        if (!pp) return E_POINTER;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *pp = (IClassFactory*)this;
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
        auto* t = new ProbeTip();
        HRESULT hr = t->QueryInterface(riid, pp);
        t->Release();
        return hr;
    }
    HRESULT STDMETHODCALLTYPE LockServer(BOOL lock) override {
        if (lock) InterlockedIncrement(&g_locks);
        else InterlockedDecrement(&g_locks);
        return S_OK;
    }

private:
    LONG refs_ = 1;
};

// -- registration (as ゆらぎ registers itself: ITfInputProcessorProfileMgr only) --------------------

static std::wstring GuidStr(const GUID& g) {
    wchar_t s[64];
    StringFromGUID2(g, s, 64);
    return s;
}
static std::wstring ClsidKey() { return L"Software\\Classes\\CLSID\\" + GuidStr(CLSID_KeyProbeTip); }
static std::wstring DllPath() {
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(g_hinst, path, MAX_PATH);
    return path;
}

static HRESULT SetSz(const std::wstring& sub, const wchar_t* name, const std::wstring& val) {
    HKEY k = nullptr;
    LONG e = RegCreateKeyExW(HKEY_LOCAL_MACHINE, sub.c_str(), 0, nullptr, 0, KEY_WRITE, nullptr, &k, nullptr);
    if (e != ERROR_SUCCESS) return HRESULT_FROM_WIN32(e);
    e = RegSetValueExW(k, name, 0, REG_SZ, (const BYTE*)val.c_str(), (DWORD)((val.size() + 1) * 2));
    RegCloseKey(k);
    return HRESULT_FROM_WIN32(e);
}

static HRESULT RegisterCategories(BOOL add) {
    ITfCategoryMgr* cat = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_TF_CategoryMgr, nullptr, CLSCTX_INPROC_SERVER, IID_ITfCategoryMgr,
                                  (void**)&cat);
    if (FAILED(hr)) return hr;
    for (const GUID& g : kCats) {
        HRESULT one = add ? cat->RegisterCategory(CLSID_KeyProbeTip, g, CLSID_KeyProbeTip)
                          : cat->UnregisterCategory(CLSID_KeyProbeTip, g, CLSID_KeyProbeTip);
        if (FAILED(one) && SUCCEEDED(hr)) hr = one;
    }
    cat->Release();
    return hr;
}

static HRESULT RegisterProfile(BOOL add) {
    ITfInputProcessorProfileMgr* mgr = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_TF_InputProcessorProfiles, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_ITfInputProcessorProfileMgr, (void**)&mgr);
    if (FAILED(hr) || !mgr) return FAILED(hr) ? hr : E_FAIL;
    LANGID ja = MAKELANGID(LANG_JAPANESE, SUBLANG_JAPANESE_JAPAN);
    if (add) {
        hr = mgr->RegisterProfile(CLSID_KeyProbeTip, ja, GUID_KeyProbeProfile, kName, (ULONG)wcslen(kName), L"", 0,
                                  0, nullptr, 0, TRUE, 0);
        mgr->Release();
        HRESULT categories = RegisterCategories(TRUE);
        return FAILED(hr) ? hr : categories;
    }
    HRESULT categories = RegisterCategories(FALSE);
    hr = mgr->UnregisterProfile(CLSID_KeyProbeTip, ja, GUID_KeyProbeProfile, TF_URP_ALLPROFILES);
    mgr->Release();
    return FAILED(categories) ? categories : hr;
}

BOOL APIENTRY DllMain(HINSTANCE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) g_hinst = h;
    return TRUE;
}

STDAPI DllCanUnloadNow() { return g_locks ? S_FALSE : S_OK; }

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv) {
    if (!IsEqualCLSID(rclsid, CLSID_KeyProbeTip)) return CLASS_E_CLASSNOTAVAILABLE;
    auto* f = new Factory();
    HRESULT hr = f->QueryInterface(riid, ppv);
    f->Release();
    return hr;
}

STDAPI DllRegisterServer() {
    HRESULT co = CoInitialize(nullptr);
    std::wstring clsid = ClsidKey();
    HRESULT hr = SetSz(clsid, nullptr, kName);
    if (SUCCEEDED(hr)) hr = SetSz(clsid + L"\\InprocServer32", nullptr, DllPath());
    if (SUCCEEDED(hr)) hr = SetSz(clsid + L"\\InprocServer32", L"ThreadingModel", L"Apartment");
    if (SUCCEEDED(hr)) hr = RegisterProfile(TRUE);
    if (co == S_OK) CoUninitialize();
    return hr;
}

STDAPI DllUnregisterServer() {
    HRESULT co = CoInitialize(nullptr);
    HRESULT hr = RegisterProfile(FALSE);
    LONG e = RegDeleteTreeW(HKEY_LOCAL_MACHINE, ClsidKey().c_str());
    if (e != ERROR_SUCCESS && e != ERROR_FILE_NOT_FOUND && SUCCEEDED(hr)) hr = HRESULT_FROM_WIN32(e);
    if (co == S_OK) CoUninitialize();
    return hr;
}
