// The broker's decisions (DESIGN「ブローカー」), independent of the operating system.
//
// One Broker lives in one thread. The platform layer (platform_win.cpp) owns
// the pipes, the engine process and the clock; it calls the On* methods as
// things happen and OnTimer() when NextDeadline() has passed, and the Broker
// answers through the Platform interface. The tests drive it with a fake
// platform (tests/broker_core_test.cpp).
#pragma once

#include <cstdint>
#include <deque>
#include <map>
#include <string>
#include <vector>

namespace broker {

// DESIGN「定数」.
constexpr int ENGINE_MAX_EXITS = 3;  // this many exits within the window: stop
constexpr int64_t ENGINE_EXIT_WINDOW_MS = 600000;
constexpr int64_t ENGINE_HANG_MS = 5000;
constexpr int64_t ENGINE_START_MS = 600000;  // until ready; a first start builds the dictionary cache
// An engine that was ready and exits with this code asks to be started again
// (DESIGN「見張り」: it chooses its LM device again, e.g. after the power source
// changed). Such an exit is not counted towards ENGINE_MAX_EXITS.
constexpr int ENGINE_RESTART_CODE = 75;
constexpr int64_t NEVER = INT64_MAX;

using ClientId = uint64_t;

// Why the engine was given up, for the log and the management window (DESIGN「通知」).
enum class Stop { None, Exited, Hang };
const char* StopName(Stop stop);

enum class EngineState { Starting, Ready, Failed };

class Platform {
public:
    virtual ~Platform() = default;
    virtual int64_t Now() = 0;  // monotonic milliseconds
    // Start the engine; false when it could not even be started (the exit
    // is then reported by the Broker itself, not by the platform).
    virtual bool StartEngine(std::string& error) = 0;
    virtual void WriteEngine(const std::string& line) = 0;  // without '\n'
    // Forcibly end it; OnEngineExit follows once its output has been read.
    virtual void KillEngine() = 0;
    // Report a failed write via OnClientClosed after the current callback returns.
    virtual void WriteClient(ClientId client, const std::string& line) = 0;
    virtual void NotifyStopped(Stop reason) = 0;  // the one notice (DESIGN「通知」), once per stop
    virtual void ClearStopped() = 0;  // the stop the user was told about is over
    virtual void OpenAdmin(bool words) = 0;
    virtual void Log(const std::string& line) = 0;
    virtual void Quit() = 0;
};

class Broker {
public:
    explicit Broker(Platform& platform) : platform_(platform) {}

    void Start();
    // app_container: an app package's process (DESIGN「通信」); it is only let do what a TIP does.
    void OnClientConnected(ClientId client, bool app_container);
    void OnClientLine(ClientId client, const std::string& line);
    void OnClientClosed(ClientId client);
    void OnEngineLine(const std::string& line);
    void OnEngineStderrLine(const std::string& line);
    void OnEngineExit(int code);
    void OnTimer();
    int64_t NextDeadline() const;
    void Retry();  // the user asked: "もう一度試す", or a settings restart (DESIGN「メニュー」)

    // For the platform and the tests.
    EngineState State() const { return state_; }
    const char* ClientState() const;  // ready, starting, down

private:
    struct Client {
        bool hello = false;
        // The TIP lets keys through by itself while the engine is not ready
        // (hello "passes"). Without it (a v0.1.2 DLL), see DESIGN「使えない間の打鍵」.
        bool passes = false;
        bool direct = false;  // its input mode, as last asked or answered
        bool app_container = false;
    };
    struct InFlight {
        ClientId client;
        long long seq;
        int64_t sent;
    };

    void StartEngine();
    void EngineGone(int code);
    void SetState(EngineState state);
    void Broadcast(const std::string& line);
    void Kill(Stop reason);
    void Warn(const std::string& code);
    void UpdateKeymap(const std::string& json);
    void Log(const std::string& line) { platform_.Log(line); }

    Platform& platform_;
    EngineState state_ = EngineState::Starting;
    std::map<ClientId, Client> clients_;
    std::deque<InFlight> in_flight_;
    std::deque<int64_t> exits_;  // within ENGINE_EXIT_WINDOW_MS
    int64_t started_ = 0;  // when the current engine was started
    bool restarting_ = false;  // killed on purpose to start again (Retry while running)
    bool killing_ = false;
    Stop kill_reason_ = Stop::None;
    std::string last_fatal_;  // the engine's last "fatal ..." stderr line
    std::vector<std::string> warnings_;  // of this engine, in the hello reply (the management window shows them)
    std::string keymap_;  // retained across engine restarts
};

}  // namespace broker
