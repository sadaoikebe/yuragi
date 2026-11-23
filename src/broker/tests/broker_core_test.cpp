// The broker's decisions with a fake platform and a fake clock (DESIGN「ブローカー」).
#include "../broker_core.h"

#include <cassert>
#include <cstdio>
#include <string>
#include <vector>

using namespace broker;

namespace {

struct Fake : Platform {
    int64_t now = 1000;
    int starts = 0;
    int kills = 0;
    int cleared = 0;
    int quits = 0;
    bool can_start = true;
    std::vector<std::string> to_engine;
    std::vector<std::pair<ClientId, std::string>> to_client;
    std::vector<Stop> stops;
    std::vector<std::string> log;

    int64_t Now() override { return now; }
    bool StartEngine(std::string& error) override {
        ++starts;
        if (!can_start) error = "engine executable unavailable";
        return can_start;
    }
    void WriteEngine(const std::string& line) override { to_engine.push_back(line); }
    void KillEngine() override { ++kills; }
    void WriteClient(ClientId c, const std::string& line) override { to_client.push_back({c, line}); }
    void NotifyStopped(Stop reason) override { stops.push_back(reason); }
    void ClearStopped() override { ++cleared; }
    void OpenAdmin(bool) override {}
    void Log(const std::string& line) override { log.push_back(line); }
    void Quit() override { ++quits; }

    std::vector<std::string> Client(ClientId c) {
        std::vector<std::string> out;
        for (auto& [id, line] : to_client)
            if (id == c) out.push_back(line);
        return out;
    }
};

// Deliver a timer callback only when its deadline has arrived.
void Advance(Broker& b, Fake& f, int64_t ms) {
    f.now += ms;
    if (b.NextDeadline() <= f.now) b.OnTimer();
}

void Ready(Broker& b) { b.OnEngineLine(R"({"ready":true,"proto":1,"warnings":[]})"); }

void Hello(Broker& b, ClientId c, bool app_container = false) {
    b.OnClientConnected(c, app_container);
    b.OnClientLine(c, R"({"op":"hello","proto":1,"passes":true})");
}

bool Contains(const std::vector<std::string>& lines, const std::string& text) {
    for (auto& l : lines)
        if (l.find(text) != std::string::npos) return true;
    return false;
}

// DESIGN「使えない間の打鍵」: nothing is held while the engine starts; the TIP is told and lets keys through.
void KeysPassWhileStartingThenGoToTheEngine() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    assert(f.Client(1).back() == R"({"proto":1,"state":"starting","warnings":[]})");
    b.OnClientLine(1, R"({"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
    assert(f.Client(1).back() == R"({"seq":1,"state":"starting"})");
    b.OnClientLine(1, R"({"seq":2,"op":"reload_keymap"})");
    assert(f.Client(1).back() == R"({"seq":2,"keymap_reload":"deferred"})");
    assert(f.to_engine.empty());
    Ready(b);
    assert(f.to_engine.back() == R"({"op":"open","sid":1})");
    assert(f.Client(1).back() == R"({"event":"state","state":"ready"})");
    b.OnClientLine(1, R"({"seq":3,"op":"down","vk":74,"t":0,"mods":[],"left_context":"document","after_commit_seq":null})");
    assert(f.to_engine.back() ==
           R"({"sid":1,"seq":3,"op":"down","vk":74,"t":0,"mods":[],"left_context":"document","after_commit_seq":null})");
    b.OnEngineLine(R"({"sid":1,"seq":3,"composition":"x"})");
    assert(f.Client(1).back() == R"({"sid":1,"seq":3,"composition":"x"})");
    Advance(b, f, ENGINE_HANG_MS);
    assert(f.kills == 0);
    b.OnClientLine(1, R"({"seq":4,"op":"down","vk":65,"t":100,"left_context":"\ud800\u0041\udc00"})");
    assert(f.to_engine.back() ==
           R"({"sid":1,"seq":4,"op":"down","vk":65,"t":100,"left_context":"\ud800\u0041\udc00"})");
    b.OnClientClosed(1);
    assert(f.to_engine.back() == R"({"op":"close","sid":1})");
}

void SessionsOpenOnlyAfterHello() {
    Fake f;
    Broker b(f);
    b.Start();
    b.OnClientConnected(1, false);
    Ready(b);
    b.OnClientLine(1, R"({"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
    b.OnClientClosed(1);
    assert(f.to_engine.empty() && f.to_client.empty());

    Hello(b, 2);
    assert(f.to_engine.size() == 1 && f.to_engine.back() == R"({"op":"open","sid":2})");
    assert(f.Client(2).back() == R"({"proto":1,"state":"ready","warnings":[]})");
    b.OnClientLine(2, R"({"op":"hello","proto":1,"passes":true})");
    b.OnClientLine(2, R"({"op":"down","vk":74,"t":0,"mods":[]})");
    assert(f.to_engine.size() == 1 && f.Client(2).size() == 1);
    b.OnClientClosed(2);
    assert(f.to_engine.size() == 2 && f.to_engine.back() == R"({"op":"close","sid":2})");
}

void ReplyOnlyAnswersTheMatchingSession() {
    Fake f;
    Broker b(f);
    b.Start();
    Ready(b);
    Hello(b, 1);
    Hello(b, 2);
    b.OnClientLine(1, R"({"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
    Advance(b, f, 1);
    b.OnClientLine(2, R"({"seq":1,"op":"down","vk":65,"t":1,"mods":[]})");
    f.to_client.clear();
    // A reply out of order must leave the other session's request pending.
    b.OnEngineLine(R"({"sid":2,"seq":1,"composition":"a"})");
    assert(f.Client(1).empty());
    assert(f.Client(2).size() == 1 &&
           f.Client(2).back() == R"({"sid":2,"seq":1,"composition":"a"})");
    Advance(b, f, ENGINE_HANG_MS - 1);
    assert(f.kills == 1);
    b.OnEngineExit(9);
    assert(Contains(f.Client(1), R"({"seq":1,"state":"starting"})"));
    assert(!Contains(f.Client(2), R"({"seq":1,"state":"starting"})"));
}

// DESIGN「通信」: an app package (a sandboxed app's TIP) converts, but cannot end the broker.
void AnAppPackageCannotQuit() {
    Fake f;
    Broker b(f);
    b.Start();
    Ready(b);
    Hello(b, 1, /*app_container=*/true);
    b.OnClientLine(1, R"({"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
    assert(f.to_engine.back() == R"({"sid":1,"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
    b.OnClientLine(1, R"({"op":"quit"})");
    assert(f.quits == 0);
    Hello(b, 2);  // the installer
    b.OnClientLine(2, R"({"op":"quit"})");
    assert(f.quits == 1);
}

// A v0.1.2 TIP (no "passes") eats a key answered with a state: it is told to let the key
// through instead, in its own input mode.
void OldTipIsToldToLetKeysThrough() {
    Fake f;
    Broker b(f);
    b.Start();
    b.OnClientConnected(1, false);
    b.OnClientLine(1, R"({"op":"hello","proto":1})");
    b.OnClientLine(1, R"({"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
    assert(f.Client(1).back() == R"({"seq":1,"pass_through":true,"direct":false})");
    b.OnClientLine(1, R"({"seq":2,"op":"set_direct","direct":true})");
    assert(f.Client(1).back() == R"({"seq":2,"pass_through":true,"direct":true})");
    assert(f.to_engine.empty());
}

// DESIGN「見張り」: an exit restarts at once; the lost key and composition are told.
void ExitWhileReadyResetsAndRestarts() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    const std::string table = R"({"future":[true,17,"x"],"rev":"preset"})";
    b.OnEngineLine("{\"ready\":true,\"keymap\":" + table + "}");
    assert(Contains(f.Client(1), "{\"event\":\"keymap\",\"keymap\":" + table + "}"));
    f.to_client.clear();
    b.OnEngineLine("{\"event\":\"keymap\",\"keymap\":" + table + "}");
    assert(f.to_client.empty());
    const std::string changed_table = R"({"rev":"custom"})";
    b.OnEngineLine("{\"event\":\"keymap\",\"keymap\":" + changed_table + "}");
    const auto changed_lines = f.Client(1);
    assert(changed_lines.size() == 1 &&
           changed_lines.back() == "{\"event\":\"keymap\",\"keymap\":" + changed_table + "}");
    b.OnClientLine(1, R"({"seq":5,"op":"down","vk":74,"t":0,"mods":[]})");
    b.OnEngineExit(1);
    auto lines = f.Client(1);
    assert(Contains(lines, R"({"seq":5,"state":"starting"})"));
    assert(Contains(lines, R"({"event":"reset"})"));
    assert(lines.back() == R"({"event":"state","state":"starting"})");
    assert(f.starts == 2 && f.stops.empty() && b.State() == EngineState::Starting);
    Hello(b, 2);
    assert(f.Client(2).back().find("\"keymap\":" + changed_table) != std::string::npos);
}

// DESIGN「見張り」: an exit is logged with the fatal line of that engine, not of an earlier one.
void ExitIsLoggedWithItsOwnFatalLine() {
    Fake f;
    Broker b(f);
    b.Start();
    b.OnEngineStderrLine("fatal dictionary-unreadable");
    b.OnEngineExit(3);
    assert(Contains(f.log, "engine exited with code 3 before ready (fatal dictionary-unreadable)"));
    Ready(b);
    b.OnEngineExit(9);
    assert(Contains(f.log, "engine exited with code 9") && !Contains(f.log, "code 9 ("));
}

// Three exits within ten minutes: down, told once; "もう一度試す" starts it again.
void ThreeExitsStopThenRetry() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    b.OnEngineExit(ENGINE_RESTART_CODE);  // Before ready, this counts as a failure.
    b.OnEngineExit(21);
    assert(f.starts == 3 && f.stops.empty());
    b.OnEngineExit(21);
    assert(f.starts == 3 && b.State() == EngineState::Failed);
    assert(f.stops.size() == 1 && f.stops[0] == Stop::Exited);
    assert(f.Client(1).back() == R"({"event":"state","state":"down"})");
    b.OnClientLine(1, R"({"seq":7,"op":"down","vk":74,"t":0,"mods":[]})");
    assert(f.Client(1).back() == R"({"seq":7,"state":"down"})");
    b.OnClientLine(1, R"({"op":"retry"})");
    assert(f.cleared == 1 && f.starts == 4 && b.State() == EngineState::Starting);
    Ready(b);
    assert(b.State() == EngineState::Ready);
    b.OnEngineExit(21);
    assert(f.starts == 5 && f.stops.size() == 1 && b.State() == EngineState::Starting);
}

void ExitAtWindowBoundaryDoesNotCount() {
    Fake f;
    Broker b(f);
    b.Start();
    b.OnEngineExit(21);
    Advance(b, f, ENGINE_EXIT_WINDOW_MS);
    b.OnEngineExit(21);
    b.OnEngineExit(21);
    assert(f.starts == 4 && f.stops.empty() && b.State() == EngineState::Starting);
    b.OnEngineExit(21);
    assert(f.starts == 4 && f.stops.size() == 1 && b.State() == EngineState::Failed);
}

void StartFailuresStopAndAllowRetry() {
    Fake f;
    f.can_start = false;
    Broker b(f);
    b.Start();
    assert(f.starts == ENGINE_MAX_EXITS && f.stops == std::vector{Stop::Exited});
    Hello(b, 1);
    assert(f.Client(1).back() == R"({"proto":1,"state":"down","warnings":[]})");

    f.can_start = true;
    b.OnClientLine(1, R"({"op":"retry"})");
    assert(f.starts == ENGINE_MAX_EXITS + 1 && f.cleared == 1);
    Ready(b);
    assert(f.Client(1).back() == R"({"event":"state","state":"ready"})");
}

// A ready engine that exits with ENGINE_RESTART_CODE is started again without
// counting: it may do so any number of times (the power source changes).
void PlannedRestartsAreNotCounted() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    for (int i = 0; i < ENGINE_MAX_EXITS + 2; ++i) {
        Ready(b);
        b.OnEngineExit(ENGINE_RESTART_CODE);
        assert(b.State() == EngineState::Starting);
    }
    assert(f.starts == ENGINE_MAX_EXITS + 3 && f.stops.empty());
    assert(Contains(f.Client(1), R"({"event":"reset"})"));
}

// The oldest request sets the deadline. Repeated hangs eventually stop the engine.
void RepeatedHangsStopTheEngine() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    for (int attempt = 1; attempt <= ENGINE_MAX_EXITS; ++attempt) {
        Ready(b);
        b.OnClientLine(1, R"({"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
        Advance(b, f, ENGINE_HANG_MS - 1);
        assert(f.kills == attempt - 1);
        b.OnClientLine(1, R"({"seq":2,"op":"down","vk":65,"t":4999,"mods":[]})");
        Advance(b, f, 1);
        assert(f.kills == attempt);
        f.to_client.clear();
        b.OnEngineExit(9);
        const auto lines = f.Client(1);
        if (attempt < ENGINE_MAX_EXITS) {
            assert(f.starts == attempt + 1 && f.stops.empty());
            assert(Contains(lines, R"({"seq":1,"state":"starting"})"));
            assert(Contains(lines, R"({"seq":2,"state":"starting"})"));
        } else {
            assert(f.starts == attempt && f.stops == std::vector{Stop::Hang});
            assert(Contains(lines, R"({"seq":1,"state":"down"})"));
            assert(Contains(lines, R"({"seq":2,"state":"down"})"));
        }
    }
}

// Retry while running (new settings): a fresh engine, not counted as an exit.
void RetryWhileRunningRestartsWithoutCounting() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    Ready(b);
    b.OnEngineLine(R"({"event":"warning","warning":"lm"})");
    Hello(b, 2);
    assert(f.Client(2).back() == R"({"proto":1,"state":"ready","warnings":["lm"]})");
    for (int attempt = 1; attempt <= ENGINE_MAX_EXITS; ++attempt) {
        b.OnClientLine(1, R"({"op":"retry"})");
        assert(f.kills == attempt);
        b.OnEngineExit(9);
        Ready(b);
        assert(f.starts == attempt + 1 && f.stops.empty() && b.State() == EngineState::Ready);
    }
    Hello(b, 3);  // the new engine's warnings only
    assert(f.Client(3).back() == R"({"proto":1,"state":"ready","warnings":[]})");
    for (int attempt = 1; attempt < ENGINE_MAX_EXITS; ++attempt) {
        b.OnEngineExit(21);
        assert(f.stops.empty() && b.State() == EngineState::Starting);
    }
    b.OnEngineExit(21);
    assert(f.stops == std::vector{Stop::Exited} && b.State() == EngineState::Failed);
}

}  // namespace

int main() {
    KeysPassWhileStartingThenGoToTheEngine();
    SessionsOpenOnlyAfterHello();
    ReplyOnlyAnswersTheMatchingSession();
    AnAppPackageCannotQuit();
    OldTipIsToldToLetKeysThrough();
    ExitWhileReadyResetsAndRestarts();
    ExitIsLoggedWithItsOwnFatalLine();
    ThreeExitsStopThenRetry();
    ExitAtWindowBoundaryDoesNotCount();
    StartFailuresStopAndAllowRetry();
    PlannedRestartsAreNotCounted();
    RepeatedHangsStopTheEngine();
    RetryWhileRunningRestartsWithoutCounting();
    std::puts("broker_core_test: all passed");
    return 0;
}
