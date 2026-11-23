// tip_peer::MadeByThisUser (DESIGN「通信」), Windows only. Each case runs a copy of this
// program in the sandbox it is about:
//   - an application in an AppContainer reaches the broker's pipe, may not open the broker's
//     process (why the TIP falls back to this check), and accepts the pipe by its maker;
//   - a pipe that a low-integrity process of the same user made is refused;
//   - an AppContainer cannot make a pipe of that name at all.
// The pipe has the broker's security (src/broker/platform_win.cpp).
#include <windows.h>
#include <aclapi.h>
#include <sddl.h>
#include <userenv.h>

#include <cassert>
#include <cstdio>
#include <string>

#include "../tip_peer.h"

static std::wstring UserSid() {
    HANDLE token = nullptr;
    OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token);
    alignas(TOKEN_USER) BYTE buffer[sizeof(TOKEN_USER) + SECURITY_MAX_SID_SIZE];
    DWORD size = 0;
    GetTokenInformation(token, TokenUser, buffer, sizeof buffer, &size);
    CloseHandle(token);
    LPWSTR text = nullptr;
    ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(buffer)->User.Sid, &text);
    std::wstring sid(text);
    LocalFree(text);
    return sid;
}

// The broker's pipe: this user, and AppContainers may read and write.
static HANDLE MakePipe(const std::wstring& name) {
    std::wstring sddl = L"D:P(A;;GA;;;" + UserSid() + L")(A;;GRGW;;;AC)";
    SECURITY_ATTRIBUTES sa{sizeof sa, nullptr, FALSE};
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(), SDDL_REVISION_1,
                                                              &sa.lpSecurityDescriptor, nullptr))
        return INVALID_HANDLE_VALUE;
    HANDLE pipe = CreateNamedPipeW(name.c_str(), PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
                                   PIPE_TYPE_BYTE | PIPE_REJECT_REMOTE_CLIENTS, PIPE_UNLIMITED_INSTANCES,
                                   4096, 4096, 0, &sa);
    LocalFree(sa.lpSecurityDescriptor);
    return pipe;
}

// As the TIP opens it.
static HANDLE Connect(const std::wstring& name) {
    for (int i = 0; i < 100; ++i) {
        HANDLE pipe = CreateFileW(name.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING,
                                  FILE_FLAG_OVERLAPPED | SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, nullptr);
        if (pipe != INVALID_HANDLE_VALUE || GetLastError() != ERROR_FILE_NOT_FOUND) return pipe;
        Sleep(50);
    }
    return INVALID_HANDLE_VALUE;
}

// --- the copies --------------------------------------------------------------------------

// In an AppContainer: 0 when the TIP's fallback applies and accepts the broker's pipe.
static int Client(const std::wstring& name) {
    HANDLE pipe = Connect(name);
    if (pipe == INVALID_HANDLE_VALUE) return 10;
    ULONG pid = 0;
    if (!GetNamedPipeServerProcessId(pipe, &pid)) return 11;
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (process || GetLastError() != ERROR_ACCESS_DENIED) return 12;  // the reason for the fallback
    if (!tip_peer::MadeByThisUser(pipe)) return 13;
    CloseHandle(pipe);
    return 0;
}

// Makes a pipe and keeps it until the parent ends this process (at most 30 s, so that a
// parent that stopped at a failed check leaves nothing behind); 20 when it cannot.
static int Serve(const std::wstring& name) {
    HANDLE pipe = MakePipe(name);
    if (pipe == INVALID_HANDLE_VALUE) return 20;
    Sleep(30000);
    return 0;
}

// --- the parent -----------------------------------------------------------------------------

enum class Box { AppContainer, LowIntegrity };

struct Copy {
    std::wstring dir, exe;
    Copy() {
        // An AppContainer may not read the build folder: a copy in a folder it may read.
        wchar_t temp[MAX_PATH], self[MAX_PATH];
        GetTempPathW(MAX_PATH, temp);
        GetModuleFileNameW(nullptr, self, MAX_PATH);
        dir = std::wstring(temp) + L"tip_peer_test-" + std::to_wstring(GetCurrentProcessId());
        CreateDirectoryW(dir.c_str(), nullptr);
        exe = dir + L"\\tip_peer_test.exe";
        assert(CopyFileW(self, exe.c_str(), FALSE));
        PSID packages = nullptr;
        assert(ConvertStringSidToSidW(L"S-1-15-2-1", &packages));  // ALL APPLICATION PACKAGES
        EXPLICIT_ACCESSW access{};
        access.grfAccessPermissions = GENERIC_READ | GENERIC_EXECUTE;
        access.grfAccessMode = GRANT_ACCESS;
        access.grfInheritance = SUB_CONTAINERS_AND_OBJECTS_INHERIT;
        access.Trustee.TrusteeForm = TRUSTEE_IS_SID;
        access.Trustee.ptstrName = static_cast<LPWSTR>(packages);
        PACL old = nullptr, acl = nullptr;
        PSECURITY_DESCRIPTOR sd = nullptr;
        assert(GetNamedSecurityInfoW(dir.c_str(), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, nullptr, nullptr,
                                     &old, nullptr, &sd) == ERROR_SUCCESS);
        assert(SetEntriesInAclW(1, &access, old, &acl) == ERROR_SUCCESS);
        assert(SetNamedSecurityInfoW(&dir[0], SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, nullptr, nullptr, acl,
                                     nullptr) == ERROR_SUCCESS);
        LocalFree(acl);
        LocalFree(sd);
        LocalFree(packages);
    }
    ~Copy() {
        DeleteFileW(exe.c_str());
        RemoveDirectoryW(dir.c_str());
    }
};

static HANDLE Start(const Copy& copy, Box box, const wchar_t* mode, const std::wstring& name) {
    std::wstring command = L"\"" + copy.exe + L"\" " + mode + L" " + name;
    STARTUPINFOEXW si{};
    si.StartupInfo.cb = sizeof si;
    PROCESS_INFORMATION pi{};
    BOOL started = FALSE;
    if (box == Box::AppContainer) {
        const wchar_t* container = L"yuragi.tip-peer-test";
        PSID sid = nullptr;
        HRESULT hr = CreateAppContainerProfile(container, container, container, nullptr, 0, &sid);
        if (hr == HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)) hr = DeriveAppContainerSidFromAppContainerName(container, &sid);
        assert(SUCCEEDED(hr));
        SECURITY_CAPABILITIES capabilities{};
        capabilities.AppContainerSid = sid;
        SIZE_T size = 0;
        InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
        std::string list(size, '\0');
        si.lpAttributeList = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(&list[0]);
        assert(InitializeProcThreadAttributeList(si.lpAttributeList, 1, 0, &size));
        assert(UpdateProcThreadAttribute(si.lpAttributeList, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                                         &capabilities, sizeof capabilities, nullptr, nullptr));
        started = CreateProcessW(copy.exe.c_str(), &command[0], nullptr, nullptr, FALSE,
                                 EXTENDED_STARTUPINFO_PRESENT, nullptr, nullptr, &si.StartupInfo, &pi);
        DeleteProcThreadAttributeList(si.lpAttributeList);
        FreeSid(sid);
    } else {
        HANDLE mine = nullptr, token = nullptr;
        assert(OpenProcessToken(GetCurrentProcess(),
                                TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ADJUST_DEFAULT | TOKEN_ASSIGN_PRIMARY, &mine));
        assert(DuplicateTokenEx(mine, 0, nullptr, SecurityImpersonation, TokenPrimary, &token));
        PSID low = nullptr;
        assert(ConvertStringSidToSidW(L"S-1-16-4096", &low));
        TOKEN_MANDATORY_LABEL label{};
        label.Label.Attributes = SE_GROUP_INTEGRITY;
        label.Label.Sid = low;
        assert(SetTokenInformation(token, TokenIntegrityLevel, &label, sizeof label + GetLengthSid(low)));
        started = CreateProcessAsUserW(token, copy.exe.c_str(), &command[0], nullptr, nullptr, FALSE, 0, nullptr,
                                       nullptr, &si.StartupInfo, &pi);
        LocalFree(low);
        CloseHandle(token);
        CloseHandle(mine);
    }
    assert(started);
    CloseHandle(pi.hThread);
    return pi.hProcess;
}

static DWORD Finish(HANDLE process, DWORD wait_ms) {
    DWORD code = STILL_ACTIVE;
    if (WaitForSingleObject(process, wait_ms) == WAIT_OBJECT_0) GetExitCodeProcess(process, &code);
    else TerminateProcess(process, 0);
    CloseHandle(process);
    return code;
}

static std::wstring PipeName(const wchar_t* what) {
    return L"\\\\.\\pipe\\yuragi-ime-tip-peer-test-" + std::to_wstring(GetCurrentProcessId()) + L"-" + what;
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 3 && wcscmp(argv[1], L"client") == 0) return Client(argv[2]);
    if (argc == 3 && wcscmp(argv[1], L"serve") == 0) return Serve(argv[2]);

    // The broker's pipe, made by this user at medium integrity.
    std::wstring name = PipeName(L"broker");
    HANDLE server = MakePipe(name);
    assert(server != INVALID_HANDLE_VALUE);
    HANDLE client = Connect(name);
    assert(client != INVALID_HANDLE_VALUE);
    assert(tip_peer::MadeByThisUser(client));
    CloseHandle(client);

    Copy copy;
    // From an AppContainer: reached, the process not openable, the pipe accepted.
    HANDLE second = MakePipe(name);  // an instance for the copy to connect to
    assert(second != INVALID_HANDLE_VALUE);
    DWORD code = Finish(Start(copy, Box::AppContainer, L"client", name), 30000);
    std::printf("AppContainer client: %lu\n", code);
    assert(code == 0);
    CloseHandle(second);
    CloseHandle(server);

    // A pipe made at low integrity by this user: refused.
    std::wstring fake = PipeName(L"low");
    HANDLE low = Start(copy, Box::LowIntegrity, L"serve", fake);
    client = Connect(fake);
    const bool reached = client != INVALID_HANDLE_VALUE;
    const bool accepted = reached && tip_peer::MadeByThisUser(client);
    if (reached) CloseHandle(client);
    Finish(low, 0);  // before the checks: a failed one ends this process
    std::printf("low-integrity pipe: reached %d, accepted %d\n", reached, accepted);
    assert(reached);
    assert(!accepted);

    // An AppContainer cannot make a pipe of that name.
    code = Finish(Start(copy, Box::AppContainer, L"serve", PipeName(L"appcontainer")), 30000);
    std::printf("AppContainer serve: %lu\n", code);
    assert(code == 20);

    DeleteAppContainerProfile(L"yuragi.tip-peer-test");
    std::printf("tip_peer OK\n");
    return 0;
}
