// The TIP's decisions without TSF.
#include "../tip_logic.h"

#include <cassert>
#include <cstdio>

using namespace tip_logic;

static Message Parse(const std::string& line) {
    Message m;
    assert(ParseMessage(line, m));
    return m;
}

static void ReadingReplies() {
    // An engine reply as the broker forwards it (with the sid it added).
    Message r = Parse(R"({"sid":4,"seq":17,"direct":false,"pass_through":false,
        "composition":"か","commit":"","converted":true,"fsm":"S1","n_tokens":1,
        "timer":1234,"candidates":["花","x"],"cand_index":1,"segments":[
        {"start":0,"end":1,"display_start":0,"display_end":1}],"focus":0,
        "candidate_page":2,"candidate_kinds":["dictionary"],"has_next_page":true,
        "predicting":false,"pending":true})");
    assert(r.has_seq && r.seq == 17 && r.engine && !r.hello);
    assert(r.composition == "\xE3\x81\x8B" && r.converted && r.pending);
    assert(r.has_timer && r.timer == 1234 && r.n_tokens == 1 && r.page == 2);
    assert(r.candidates.size() == 2 && r.cand_index == 1 && r.has_next_page);
    assert(r.segments.size() == 1 && r.segments[0].display_end == 1);

    // DESIGN「互換の規則」: missing fields default, unknown ones are ignored.
    Message sparse = Parse(R"({"seq":3,"new_field":{"x":[1]}})");
    assert(sparse.engine && sparse.composition.empty() && !sparse.has_timer);
    assert(sparse.focus == -1 && sparse.candidates.empty() && !sparse.error);

    Message notjson;
    assert(!ParseMessage("not json", notjson) && !ParseMessage("[1]", notjson));
}

static void ReadingBrokerMessages() {
    Message hello = Parse(R"({"proto":1,"state":"starting","warnings":["config","lm"]})");
    assert(hello.hello && hello.proto == 1 && hello.state == "starting");
    assert(hello.warnings.size() == 2 && !hello.engine);
    Message down = Parse(R"({"seq":9,"state":"down"})");
    assert(down.has_seq && !down.engine && down.state == "down");
    Message event = Parse(R"({"event":"state","state":"ready"})");
    assert(event.event == "state" && event.state == "ready" && !event.has_seq);
}

static void CommittingVisibleText() {
    assert(CommitsVisibleText(Parse(R"({"event":"reset"})")));
    assert(CommitsVisibleText(Parse(R"({"seq":1,"error":true,"composition":""})")));
    assert(CommitsVisibleText(Parse(R"({"seq":2,"state":"down"})")));
    assert(CommitsVisibleText(Parse(R"({"event":"state","state":"down"})")));
    assert(!CommitsVisibleText(Parse(R"({"event":"state","state":"starting"})")));
    assert(!CommitsVisibleText(Parse(R"({"event":"state","state":"ready"})")));
    assert(!CommitsVisibleText(Parse(R"({"seq":3,"composition":"x"})")));
}

static void StatesAndWhatTheUserSees() {
    assert(ModeFor(Link::Connected, "ready") == Mode::Normal);
    assert(ModeFor(Link::Connected, "starting") == Mode::Preparing);
    assert(ModeFor(Link::Connected, "") == Mode::Preparing);  // before the hello reply
    assert(ModeFor(Link::Connected, "down") == Mode::Stopped);
    assert(ModeFor(Link::Connecting, "") == Mode::Preparing);
    assert(ModeFor(Link::Unreachable, "ready") == Mode::Stopped);
    assert(ModeFor(Link::NotAllowed, "") == Mode::Excluded);

    // While the engine starts, keys pass through (nothing is held for later).
    assert(SendsKeys(Mode::Normal) && !SendsKeys(Mode::Preparing));
    assert(!SendsKeys(Mode::Stopped) && !SendsKeys(Mode::Excluded));
    // The toggle works while preparing, so a direct input left by a lost connection can be undone.
    assert(Toggles(Mode::Normal) && Toggles(Mode::Preparing));
    assert(!Toggles(Mode::Stopped) && !Toggles(Mode::Excluded));
    assert(std::string(Glyph(Mode::Preparing, true)) == "Y");
    assert(std::string(Glyph(Mode::Normal, false)) == "\xE3\x82\x86");  // ゆ
    assert(std::string(Glyph(Mode::Normal, true)) == "Y");
    assert(std::string(Glyph(Mode::Stopped, false)) == "!");
    assert(std::string(Glyph(Mode::Excluded, false)) == "Y");
    assert(Faint(Mode::Preparing) && !Faint(Mode::Normal));

    assert((MenuFor(Mode::Normal) == std::vector<int>{MENU_TOGGLE, MENU_ADMIN}));
    assert((MenuFor(Mode::Preparing) == std::vector<int>{MENU_PREPARING, MENU_ADMIN}));
    assert((MenuFor(Mode::Stopped) == std::vector<int>{MENU_RETRY, MENU_ADMIN}));
}

static void EatingKeys() {
    Mods none, shift, ctrl;
    shift.shift = true;
    ctrl.ctrl = true;
    Local idle;
    assert(WantKey('J', none, idle) && WantKey(VK_SPACE_, none, idle));
    assert(!WantKey('J', ctrl, idle));  // shortcuts belong to the application
    assert(!WantKey(VK_RETURN_, none, idle) && !WantKey(VK_BACK_, none, idle));
    // DESIGN「打鍵の処理」: a character whose reply has not come yet makes Enter ours.
    Local awaiting;
    awaiting.awaiting = true;
    assert(WantKey(VK_RETURN_, none, awaiting) && WantKey(VK_BACK_, none, awaiting));
    assert(!WantKey(VK_LEFT_, none, awaiting));
    Local converted;
    converted.composing = converted.converted = converted.candidates = true;
    assert(WantKey(VK_LEFT_, none, converted) && WantKey(VK_DOWN_, none, converted));
    assert(!WantKey(VK_DOWN_, shift, converted) && WantKey(VK_RIGHT_, shift, converted));
    assert(!WantKey(VK_F8_, shift, converted) && WantKey(VK_F8_, none, converted));
    // 部分確定: Ctrl+↓ is ours while composing (awaiting included), Ctrl alone.
    Mods ctrl_alt = ctrl, ctrl_shift = ctrl, ctrl_win = ctrl;
    ctrl_alt.alt = true;
    ctrl_shift.shift = true;
    ctrl_win.win = true;
    Local typing;
    typing.composing = true;
    assert(WantKey(VK_DOWN_, ctrl, converted) && WantKey(VK_DOWN_, ctrl, typing));
    assert(WantKey(VK_DOWN_, ctrl, awaiting) && !WantKey(VK_DOWN_, ctrl, idle));
    assert(!WantKey(VK_DOWN_, ctrl_alt, converted) && !WantKey(VK_DOWN_, ctrl_shift, converted));
    assert(!WantKey(VK_DOWN_, ctrl_win, converted) && !WantKey(VK_UP_, ctrl, converted));

    Message reply = Parse(R"({"seq":1,"composition":"x","n_tokens":1})");
    assert(EatAfterReply(true, 'J', none, idle, false, 0, reply));
    Message passed = Parse(R"({"seq":1,"pass_through":true})");
    assert(!EatAfterReply(true, 'J', none, idle, false, 0, passed));
    Message empty = Parse(R"({"seq":1})");
    assert(!EatAfterReply(true, VK_RETURN_, none, idle, false, 0, empty));
    assert(EatAfterReply(false, 'J', none, idle, false, 0, empty));  // a consumed down's up
    Message tab = Parse(R"({"seq":1,"predicting":true})");
    Local composing;
    composing.composing = true;
    assert(EatAfterReply(true, VK_TAB_, none, composing, false, 1, tab));
    // Tab with no prediction stays ours while composing; with no input it is the app's.
    Message typed = Parse(R"({"seq":1,"composition":"x","n_tokens":1})");
    assert(EatAfterReply(true, VK_TAB_, none, composing, false, 1, typed));
    assert(!EatAfterReply(true, VK_TAB_, none, idle, false, 0, empty));
    // F6/F7 with no input are the application's, Shift or not.
    assert(!WantKey(VK_F7_, none, idle) && !WantKey(VK_F6_, none, idle));
    assert(WantKey(VK_F7_, none, typing) && !WantKey(VK_F7_, shift, idle));
    assert(!WantKey(VK_F7_, shift, typing) && WantKey(VK_F6_, shift, typing));  // the engine has no Shift+F7
    assert(!EatAfterReply(true, VK_F7_, none, idle, false, 0, empty));
    assert(EatAfterReply(true, VK_F7_, none, composing, false, 1, typed));
    // Ctrl+↓ as Enter: eaten after input, whether the rest stays or not.
    Message rest = Parse(R"({"seq":1,"composition":"y","commit":"x","n_tokens":1,"converted":true})");
    Message whole = Parse(R"({"seq":1,"commit":"x"})");
    assert(EatAfterReply(true, VK_DOWN_, ctrl, converted, false, 2, rest));
    assert(EatAfterReply(true, VK_DOWN_, ctrl, composing, false, 1, whole));
    assert(!EatAfterReply(true, VK_DOWN_, ctrl, idle, false, 0, empty));
    assert(!EatAfterReply(true, VK_DOWN_, ctrl_alt, converted, false, 2, rest));
    assert(EatAfterReply(false, VK_DOWN_, ctrl, converted, false, 2, rest));  // its up
}

static void OrderOfReplies() {
    InFlight f;
    assert(!f.Waiting());
    long long a = f.Next(1000), b = f.Next(1050), c = f.Next(1100);
    assert(a == 1 && b == 2 && c == 3 && f.Waiting(2));
    assert(f.Answer(1));
    assert(!f.Answer(1));  // already answered
    assert(f.Answer(2) && f.Answer(3));
    assert(!f.Waiting() && f.Last() == 3);

    const auto old = f.Next(1200);
    f.Clear();  // retiring the context drops outstanding requests
    const auto current = f.Next(1300);
    assert(current > old);
    assert(!f.Answer(old) && f.Waiting(current));
    assert(f.Answer(current));
}

static void ConnectingAndSpawning() {
    ConnectGate gate;
    assert(gate.Allow(5000));
    assert(!gate.Allow(6999));
    assert(gate.Allow(7000));

    SpawnFacts f;
    f.tag_matches = f.medium_integrity = true;
    assert(MaySpawn(f));
    SpawnFacts old_dll = f;
    old_dll.tag_matches = false;  // uninstalled or updated: never starts anything
    assert(!MaySpawn(old_dll));
    SpawnFacts installing = f;
    installing.maintenance = true;
    assert(!MaySpawn(installing));
    SpawnFacts sandboxed = f;
    sandboxed.medium_integrity = false;
    assert(!MaySpawn(sandboxed));
}

static void CandidatePlacement() {
    assert(CandidateTop(400, 420, 176, 4, 1000) == 424);  // room below
    assert(CandidateTop(800, 820, 176, 4, 1000) == 824);  // exactly fits
    assert(CandidateTop(800, 820, 177, 4, 1000) == 619);  // one pixel past: above
    assert(CandidateTop(-120, -100, 176, 4, 0) == -300);  // monitor above the primary
    assert(CandidateTop(1180, 1210, 264, 6, 1440) == 910);  // scaled height and gap
}

static void Requests() {
    Mods m;
    m.shift = m.alt = true;
    assert(KeyRequest(7, true, 74, 123, m) ==
           R"({"seq":7,"op":"down","vk":74,"t":123,"mods":["shift","alt"]})");
    assert(OpRequest(8, "set_direct", "\"direct\":true") ==
           R"({"seq":8,"op":"set_direct","direct":true})");
    std::string hello = Hello("v0.2.0");
    Message parsed;
    assert(ParseMessage(hello, parsed));
    tip_json::Value v;
    assert(tip_json::Parser(hello).Parse(v) && v.Get("op").text == "hello" &&
           v.Get("tag").text == "v0.2.0" && v.Get("passes").boolean);
}

int main() {
    ReadingReplies();
    ReadingBrokerMessages();
    CommittingVisibleText();
    StatesAndWhatTheUserSees();
    EatingKeys();
    OrderOfReplies();
    ConnectingAndSpawning();
    CandidatePlacement();
    Requests();
    std::puts("tip_logic_test: all passed");
    return 0;
}
