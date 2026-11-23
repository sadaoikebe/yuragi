// Who made a named pipe (DESIGN「通信」). Windows only; the TIP and tests/tip_peer_test.cpp.
#pragma once

#include <windows.h>
#include <aclapi.h>

namespace tip_peer {

// The pipe was made by this user at medium integrity or above: its owner is this
// process's user and it has no mandatory label below medium (no label is medium).
// A sandboxed process of the same user cannot pass: a low-integrity one labels what it
// makes low, and an AppContainer cannot make a pipe of that name at all.
// It needs only the client's own handle, so it works in an AppContainer, which may not
// open the broker's process (OpenProcess is denied there).
inline bool MadeByThisUser(HANDLE pipe) {
    PSID owner = nullptr;
    PACL sacl = nullptr;
    PSECURITY_DESCRIPTOR sd = nullptr;
    if (GetSecurityInfo(pipe, SE_KERNEL_OBJECT, OWNER_SECURITY_INFORMATION | LABEL_SECURITY_INFORMATION,
                        &owner, nullptr, nullptr, &sacl, &sd) != ERROR_SUCCESS)
        return false;
    bool ok = false;
    HANDLE token = nullptr;
    if (owner && OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) {
        alignas(TOKEN_USER) BYTE buffer[sizeof(TOKEN_USER) + SECURITY_MAX_SID_SIZE];
        DWORD size = 0;
        if (GetTokenInformation(token, TokenUser, buffer, sizeof buffer, &size) &&
            EqualSid(owner, reinterpret_cast<TOKEN_USER*>(buffer)->User.Sid)) {
            DWORD level = SECURITY_MANDATORY_MEDIUM_RID;
            for (WORD i = 0; sacl && i < sacl->AceCount; ++i) {
                ACE_HEADER* ace = nullptr;
                if (GetAce(sacl, i, reinterpret_cast<void**>(&ace)) && ace->AceType == SYSTEM_MANDATORY_LABEL_ACE_TYPE) {
                    PSID label = &reinterpret_cast<SYSTEM_MANDATORY_LABEL_ACE*>(ace)->SidStart;
                    level = *GetSidSubAuthority(label, *GetSidSubAuthorityCount(label) - 1);
                }
            }
            ok = level >= SECURITY_MANDATORY_MEDIUM_RID;
        }
        CloseHandle(token);
    }
    LocalFree(sd);
    return ok;
}

}  // namespace tip_peer
