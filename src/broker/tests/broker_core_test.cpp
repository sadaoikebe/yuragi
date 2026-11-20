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
    std::vector<std::string> to_engine;
    std::vector<std::pair<ClientId, std::string>> to_client;
    std::vector<Stop> stops;
    std::vector<std::string> log;

    int64_t Now() override { return now; }
    bool StartEngine(std::string&) override {
        ++starts;
        return true;
    }
    void WriteEngine(const std::string& line) override { to_engine.push_back(line); }
    void KillEngine() override { ++kills; }
    void WriteClient(ClientId c, const std::string& line) override { to_client.push_back({c, line}); }
    void NotifyStopped(Stop reason) override { stops.push_back(reason); }
    void ClearStopped() override { ++cleared; }
    void OpenAdmin() override {}
    void Log(const std::string& line) override { log.push_back(line); }
    void Quit() override {}

    std::vector<std::string> Client(ClientId c) {
        std::vector<std::string> out;
        for (auto& [id, line] : to_client)
            if (id == c) out.push_back(line);
        return out;
    }
};

// Run the broker's timers up to the fake clock's time + ms.
void Advance(Broker& b, Fake& f, int64_t ms) {
    int64_t end = f.now + ms;
    for (;;) {
        int64_t next = b.NextDeadline();
        if (next > end) break;
        f.now = std::max(f.now, next);
        b.OnTimer();
    }
    f.now = end;
    b.OnTimer();
}

void Ready(Broker& b) { b.OnEngineLine(R"({"ready":true,"proto":1,"warnings":[]})"); }

void Hello(Broker& b, ClientId c) {
    b.OnClientConnected(c);
    b.OnClientLine(c, R"({"op":"hello","proto":1,"tag":"t","bits":64,"passes":true})");
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
    assert(f.to_engine.empty());
    Ready(b);
    assert(f.to_engine.back() == R"({"op":"open","sid":1})");
    assert(f.Client(1).back() == R"({"event":"state","state":"ready"})");
    b.OnClientLine(1, R"({"seq":2,"op":"down","vk":74,"t":0,"mods":[],"left_context":"document","after_commit_seq":null})");
    assert(f.to_engine.back() ==
           R"({"sid":1,"seq":2,"op":"down","vk":74,"t":0,"mods":[],"left_context":"document","after_commit_seq":null})");
    b.OnEngineLine(R"({"sid":1,"seq":2,"composition":"x"})");
    assert(f.Client(1).back() == R"({"sid":1,"seq":2,"composition":"x"})");
    b.OnClientLine(1, R"({"seq":3,"op":"down","vk":65,"t":100,"left_context":"\ud800\u0041\udc00"})");
    assert(f.to_engine.back() ==
           R"({"sid":1,"seq":3,"op":"down","vk":65,"t":100,"left_context":"\ud800\u0041\udc00"})");
    b.OnClientClosed(1);
    assert(f.to_engine.back() == R"({"op":"close","sid":1})");
}

// A v0.1.2 TIP (no "passes") eats a key answered with a state: it is told to let the key
// through instead, in its own input mode.
void OldTipIsToldToLetKeysThrough() {
    Fake f;
    Broker b(f);
    b.Start();
    b.OnClientConnected(1);
    b.OnClientLine(1, R"({"op":"hello","proto":1,"tag":"v0.1.2","bits":64})");
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
    Ready(b);
    b.OnClientLine(1, R"({"seq":5,"op":"down","vk":74,"t":0,"mods":[]})");
    b.OnEngineExit(1);
    auto lines = f.Client(1);
    assert(Contains(lines, R"({"seq":5,"state":"starting"})"));
    assert(Contains(lines, R"({"event":"reset"})"));
    assert(lines.back() == R"({"event":"state","state":"starting"})");
    assert(f.starts == 2 && f.stops.empty() && b.State() == EngineState::Starting);
}

// Three exits within ten minutes: down, told once; "もう一度試す" starts it again.
void ThreeExitsStopThenRetry() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    b.OnEngineExit(21);
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

// A request with no reply ends the engine (a hang).
void HungEngineIsKilled() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    Ready(b);
    b.OnClientLine(1, R"({"seq":1,"op":"down","vk":74,"t":0,"mods":[]})");
    Advance(b, f, ENGINE_HANG_MS - 1);
    assert(f.kills == 0);
    Advance(b, f, 1);
    assert(f.kills == 1);
    b.OnEngineExit(9);
    assert(f.starts == 2);
}

// Retry while running (new settings): a fresh engine, not counted as an exit.
void RetryWhileRunningRestartsWithoutCounting() {
    Fake f;
    Broker b(f);
    b.Start();
    Hello(b, 1);
    Ready(b);
    b.OnEngineLine(R"({"event":"warning","warning":"lm"})");
    b.OnClientLine(1, R"({"op":"retry"})");
    assert(f.kills == 1);
    b.OnEngineExit(9);
    Ready(b);
    assert(f.starts == 2 && f.stops.empty() && b.State() == EngineState::Ready);
    Hello(b, 2);  // the new engine's warnings only
    assert(f.Client(2).front() == R"({"proto":1,"state":"ready","warnings":[]})");
}

}  // namespace

int main() {
    KeysPassWhileStartingThenGoToTheEngine();
    OldTipIsToldToLetKeysThrough();
    ExitWhileReadyResetsAndRestarts();
    ThreeExitsStopThenRetry();
    PlannedRestartsAreNotCounted();
    HungEngineIsKilled();
    RetryWhileRunningRestartsWithoutCounting();
    std::puts("broker_core_test: all passed");
    return 0;
}
