// The TIP's decisions without TSF.
#include "../tip_logic.h"

#include <cassert>
#include <cstdio>
#include <iostream>
#include <tuple>

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
    assert(r.candidate_notes.empty());  // older engines still show their candidates
    assert(r.segments.size() == 1 && r.segments[0].display_end == 1);

    Message annotated = Parse(R"({"candidates":["花",false,"ハナ","はな"],
        "candidate_notes":[null,"記号","カタカナ"]})");
    assert((annotated.candidate_notes == std::vector<std::string>{"", "カタカナ", ""}));

    // DESIGN「互換の規則」: missing fields default, unknown ones are ignored.
    Message sparse = Parse(R"({"seq":3,"new_field":{"x":[1]}})");
    assert(sparse.engine && sparse.composition.empty() && !sparse.has_timer);
    assert(sparse.focus == -1 && sparse.candidates.empty() && !sparse.error && sparse.fsm_idle);
    Message held = Parse(R"({"seq":4,"fsm":"S6","commit":"　"})");
    assert(held.composition.empty() && !held.has_timer && !held.fsm_idle);

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
}

static void EatingKeys() {
    const auto table = DefaultKeyTable();
    // An earlier engine still supplies a usable key table without the editing row.
    tip_json::Value older;
    const std::string encoded(kDefaultKeyTable);
    assert(tip_json::Parser(encoded).Parse(older));
    assert(older.object.at("phases").object.erase("editing") == 1);
    auto old_table = ParseKeyTable(older);
    assert(old_table && old_table->rev == table.rev);

    auto take = [&](uint32_t vk, Mods mods, Phase phase, bool unsettled = false) {
        return WantKey(NormalizeKey(vk, mods), {phase, unsettled}, table);
    };
    Mods none, shift, ctrl, alt, win;
    shift.shift = ctrl.ctrl = alt.alt = win.win = true;
    assert(take(VK_RETURN_, none, Phase::Empty) == Take::Pass);
    assert(take(VK_RETURN_, none, Phase::Empty, true) == Take::Send);
    assert(take(VK_LEFT_, none, Phase::Empty, true) == Take::Send);
    assert(take(0x61, none, Phase::Empty) == Take::Send);  // numpad
    assert(take(VK_SPACE_, shift, Phase::Empty) == Take::Send);
    assert(take('C', ctrl, Phase::Composing) == Take::Send); // commit, then replay
    assert(take(VK_F6_, shift, Phase::Selecting, true) == Take::Pass);
    assert(take(0x12, alt, Phase::Composing) == Take::Pass); // Alt is observed separately
    assert(take('C', win, Phase::Composing) == Take::Pass);
    assert(take('A', none, Phase::Direct) == Take::Pass);

    auto kanji = NormalizeKey(0x19, none);
    assert(kanji.vk == 0xC0 && kanji.mods.alt);
    assert(table.global.at(kanji.Code()) == GlobalCommand::Toggle);
    assert(NormalizeKey(0xF3, none).Code() == NormalizeKey(0xF4, none).Code());
    assert(take(0xF3, none, Phase::Composing) == Take::Pass);
    assert(take(0xC0, none, Phase::Composing) == Take::Send);  // repeats after Alt up
    auto caps = NormalizeKey(0xF0, none);
    auto ctrl_caps = NormalizeKey(0x14, ctrl);
    assert(UseGlobal(caps.Code(), {Phase::Empty, true}, table) == GlobalUse::Ask);
    assert(UseGlobal(ctrl_caps.Code(), {Phase::Empty, true}, table) == GlobalUse::Run);
    assert(UseGlobal(caps.Code(), {Phase::Empty, false}, table) == GlobalUse::Run);
    assert(UseGlobal(caps.Code(), {Phase::Composing, false}, table) == GlobalUse::None);
    assert(WantKey(caps, {Phase::Empty, true}, table) == Take::Send);
    assert(WantKey(caps, {Phase::Predicting, false}, table) == Take::Send);

    auto toggle = Parse(R"({"seq":1,"eat":false,"global":"ime_toggle"})");
    assert(toggle.eat == false && toggle.global == GlobalCommand::Toggle);
    auto final = Parse(R"({"seq":4,"phase":"empty","commit":"x","global":"future_command",
        "resolved_keys":[{"seq":2,"eat":false,"global":"ime_toggle"},{"seq":3,"eat":false}]})");
    assert(final.phase == Phase::Empty && !final.eat && final.commit == "x");
    assert(!final.global && final.resolved_keys.size() == 2);
    const auto& [seq, eat, global] = final.resolved_keys[0];
    assert(seq == 2 && !eat && global == GlobalCommand::Toggle);
    assert(!final.resolved_keys[1].global);
    auto pending = Parse(R"({"seq":2,"eat":true,"eat_pending":true,"pending":true})");
    assert(pending.eat_pending && pending.eat == true);
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

    const auto suggestion = f.Next(1400, false);
    assert(!f.Waiting() && f.Waiting(suggestion));
    const auto key = f.Next(1401);
    assert(f.Waiting() && f.Answer(suggestion) && f.Waiting(key));
    assert(f.Answer(key) && !f.Waiting());
}

static void CarryFollowsOnlyTheReplayAndItsRoot() {
    constexpr uintptr_t form = 11, another_window = 22;
    Carry carry;
    assert(!carry.OnFocusMoved(form, false, 90));  // ordinary focus change
    carry.ReplayPassed(form);
    carry.Pumped();
    assert(!carry.OnFocusMoved(form, false, 95));  // focus moved after the pump

    carry.ReplayPassed(form);
    assert(carry.OnFocusMoved(form, false, 100));
    carry.Pumped();
    assert(carry.OnFocusMoved(form, false, 175));  // another notification for the move
    assert(carry.Started() == 100);
    assert(!carry.OnFocusMoved(another_window, false, 180));
    assert(!carry.Active());

    carry.ReplayPassed(form);
    assert(!carry.OnFocusMoved(form, true, 200));
    carry.ReplayPassed(0);
    assert(!carry.OnFocusMoved(0, false, 210));

    carry.Adopt(form, 220); // Windows delivered a promised down to the new field
    assert(carry.Active() && carry.Started() == 220);
    carry.Finished();
    assert(!carry.OnFocusMoved(form, false, 230));
}

static void HeldKeysRespectScopeAndSystemKeys() {
    constexpr uint64_t start = 100, deadline = start + KEY_BUDGET_MS;
    assert(DeliverHeld({true, true, Scope::Allowed}, start, start) == Deliver::Decide);
    assert(DeliverHeld({true, true, Scope::Password}, start, start) == Deliver::Raw);
    assert(DeliverHeld({true, false, Scope::Unknown}, start, start) == Deliver::Raw);
    assert(DeliverHeld({false, true, Scope::Unknown}, start, start) == Deliver::Raw);
    assert(DeliverHeld({true, true, Scope::Unknown}, deadline - 1, start) == Deliver::Wait);
    assert(DeliverHeld({true, true, Scope::Unknown}, deadline, start) == Deliver::Raw);
    assert(DeliverHeld({true, true, Scope::Unavailable}, deadline - 1, start) == Deliver::Wait);
    assert(DeliverHeld({true, true, Scope::Unavailable}, deadline, start) == Deliver::Raw);
    assert(DeliverHeld({true, true, Scope::Unavailable}, start, std::nullopt) == Deliver::Decide);

    Mods alt{}, ctrl_alt{}, win{};
    alt.alt = ctrl_alt.alt = ctrl_alt.ctrl = win.win = true;
    assert(HoldDuringCarry({'A', {}}, 'A', 0, false));
    assert(!HoldDuringCarry({'A', win}, 'A', 0, false));
    assert(!HoldDuringCarry({0x12, alt}, 0x12, 0, false));
    assert(!HoldDuringCarry({0xA0, {}}, 0xA0, 0, false));
    assert(!HoldDuringCarry({0x15, {}}, 0x15, 0x3A << 16, false));
    assert(!HoldDuringCarry({'F', alt}, 'F', 0, false));
    assert(HoldDuringCarry({'F', ctrl_alt}, 'F', 0, false));
    assert(HoldDuringCarry({0xC0, alt}, 0x19, 0, true));
}

static void HeldKeysDrainInOrderAfterTab() {
    constexpr uintptr_t form = 11;
    for (auto [first, second, when, expected_a, expected_b] : {
        std::tuple{Scope::Allowed, Scope::Allowed, 120u, Deliver::Decide, Deliver::Decide},
        std::tuple{Scope::Password, Scope::Password, 120u, Deliver::Raw, Deliver::Raw},
        std::tuple{Scope::Unknown, Scope::Unknown, 100u + KEY_BUDGET_MS, Deliver::Raw, Deliver::Raw},
        std::tuple{Scope::Unknown, Scope::Allowed, 100u + KEY_BUDGET_MS, Deliver::Raw, Deliver::Decide},
    }) {
        Carry carry;
        std::deque<uint32_t> held{'A'}; // Enter committed, then the replayed Tab passed
        std::vector<std::pair<uint32_t, Deliver>> destinations;
        carry.ReplayPassed(form);
        if (!carry.OnFocusMoved(form, held.empty(), 100)) held.clear();
        carry.Pumped();
        auto down = [&](uint32_t vk) {
            if (carry.Active() && HoldDuringCarry({vk, {}}, vk, 0, false)) held.push_back(vk);
            else destinations.emplace_back(vk, Deliver::Raw);
        };
        auto pump = [&](Scope current, uint64_t now) {
            auto started = carry.Active() ? std::optional{carry.Started()} : std::nullopt;
            auto route = DeliverHeld({true, true, current}, now, started);
            if (!held.empty() && route != Deliver::Wait) {
                destinations.emplace_back(held.front(), route);
                held.pop_front();
            }
        };
        pump(Scope::Unknown, 105);
        down('B'); // arrives before the destination has reported its scope
        assert(destinations.empty());
        pump(first, when);
        pump(second, when + 1); // after the first down is delivered
        assert((destinations == std::vector<std::pair<uint32_t, Deliver>>{
            {'A', expected_a}, {'B', expected_b},
        }));
    }
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

static void CandidatePopupLayout() {
    const auto m = ScalePopup(144);
    const auto compact = MeasurePopup(m, 1920, 1, -1, m.text_font, 0, 0, false);
    const auto paged = MeasurePopup(m, 1920, 9, 8, 2000, 60, 100, false);
    assert(compact.width < paged.width && compact.selected == -1);
    assert(compact.footer_top == compact.height);
    assert(paged.width == m.max_width && paged.text_right - paged.text_left < 2000);
    assert(paged.text_right < paged.note_left);
    assert(paged.Row(m, paged.selected).bottom < paged.footer_top && paged.footer_top < paged.height);
    const auto narrow = MeasurePopup(m, 320, 1, 8, 2000, 60, 0, false);
    assert(narrow.width <= 320 && narrow.selected == -1);
    assert(narrow.text_left < narrow.text_right && narrow.text_right < narrow.note_left);

    const PopupColors windows{1, 2, 3, 4, 5, 6, 7};
    const auto contrast = PopupPalette(true, 9, windows);
    assert(contrast.surface == windows.surface && contrast.text == windows.text &&
           contrast.secondary == windows.secondary && contrast.border == windows.border &&
           contrast.selected == windows.selected && contrast.selected_text == windows.selected_text &&
           contrast.mark == windows.mark);
}

static void Requests() {
    Mods m;
    m.shift = m.alt = true;
    assert(KeyRequest(7, true, 74, 123, m) ==
           R"({"seq":7,"op":"down","vk":74,"t":123,"mods":["shift","alt"]})");
    KeyContext context;
    assert(KeyRequest(8, true, 65, 124, {}, &context) ==
           R"({"seq":8,"op":"down","vk":65,"t":124,"mods":[],"left_context":null})");
    context.disconnected = true;
    context.text = "";
    assert(KeyRequest(8, true, 65, 124, {}, &context) ==
           R"({"seq":8,"op":"down","vk":65,"t":124,"mods":[],"left_context":"","after_commit_seq":null})");
    context.disconnected = false;
    context.text.reset();
    context.after_commit_seq = 7;
    assert(KeyRequest(8, true, 65, 124, {}, &context) ==
           R"({"seq":8,"op":"down","vk":65,"t":124,"mods":[],"left_context":null,"after_commit_seq":7})");
    context.text = "原稿の誤字を\"\n";
    tip_json::Value key;
    assert(tip_json::Parser(KeyRequest(8, true, 65, 124, {}, &context)).Parse(key));
    assert(key.Get("left_context").text == *context.text);
    assert(OpRequest(8, "set_direct", "\"direct\":true") ==
           R"({"seq":8,"op":"set_direct","direct":true})");
    std::string hello = Hello("v0.2.0");
    Message parsed;
    assert(ParseMessage(hello, parsed));
    tip_json::Value v;
    assert(tip_json::Parser(hello).Parse(v) && v.Get("op").text == "hello" &&
           v.Get("tag").text == "v0.2.0" && v.Get("passes").boolean);
}

static void LeftContextTail() {
    std::wstring tail = {0xd842, 0xdfb7};  // U+20BB7
    tail.append(199, L'あ');
    assert(ContextTail(L"それより前" + tail, false) == tail);
    assert(ContextTail(tail, false) == tail);
    assert(ContextTail(L"", false) == L"");
    auto cut = std::wstring(1, 0xdfb7) + tail;
    assert(ContextTail(cut, true) == tail);
    assert(!ContextTail(cut, false));
    assert(!ContextTail(tail + std::wstring(1, 0xd842), true));
    std::wstring astral;
    for (size_t i = 0; i < CONTEXT_CHARS; ++i) astral += {0xd842, 0xdfb7};
    assert(ContextTail(astral, true) == astral);
}

static int CompareEngineKeys() {
    const auto table = DefaultKeyTable();
    std::string name;
    unsigned vk, flags;
    bool sends;
    size_t checked = 0;
    while (std::cin >> name >> vk >> flags >> sends) {
        auto it = std::find(kPhaseNames.begin(), kPhaseNames.end(), name);
        assert(it != kPhaseNames.end());
        auto phase = static_cast<Phase>(it - kPhaseNames.begin());
        Mods mods{bool(flags & 1), bool(flags & 2), bool(flags & 4), bool(flags & 8)};
        if ((WantKey({vk, mods}, {phase, false}, table) == Take::Send) != sends) {
            std::fprintf(stderr, "%s vk=%u mods=%u disagrees with engine\n", name.c_str(), vk, flags);
            return 1;
        }
        ++checked;
    }
    return std::cin.eof() && checked > 0 ? 0 : 1;
}

int main(int argc, char** argv) {
    if (argc == 2 && std::string_view(argv[1]) == "--key-cases") return CompareEngineKeys();
    ReadingReplies();
    ReadingBrokerMessages();
    CommittingVisibleText();
    StatesAndWhatTheUserSees();
    EatingKeys();
    OrderOfReplies();
    CarryFollowsOnlyTheReplayAndItsRoot();
    HeldKeysRespectScopeAndSystemKeys();
    HeldKeysDrainInOrderAfterTab();
    ConnectingAndSpawning();
    CandidatePlacement();
    CandidatePopupLayout();
    Requests();
    LeftContextTail();
    std::puts("tip_logic_test: all passed");
    return 0;
}
