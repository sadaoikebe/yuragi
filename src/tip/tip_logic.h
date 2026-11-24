// The TIP's decisions that do not need TSF (DESIGN「TIP」), tested on any OS by
// src/tip/tests/tip_logic_test.cpp: reading the broker's messages, whether to eat a key,
// the order of replies, and what the user sees for each state.
#pragma once

#include <algorithm>
#include <array>
#include <cstdint>
#include <deque>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "tip_json.h"
#include "default_keymap.h"

namespace tip_logic {

// DESIGN「定数」.
constexpr uint32_t KEY_BUDGET_MS = 200;
constexpr uint32_t CONNECT_MIN_INTERVAL_MS = 2000;
constexpr uint32_t BROKER_WAIT_MS = 10000;
constexpr uint32_t BROKER_POLL_MS = 100;
constexpr uint32_t NOTICE_SHOW_MS = 4000;  // DESIGN「小さな表示」: the notices that go by themselves
constexpr size_t CONTEXT_CHARS = 200;
// Not a setting: the UTF-16 units that can hold CONTEXT_CHARS code points.
constexpr size_t CONTEXT_UNITS = 2 * CONTEXT_CHARS;

// The last CONTEXT_CHARS code points; none when they hold a lone surrogate (what lies
// before them is not looked at). The input uses UTF-16 units even on the platforms that
// only run these tests.
inline std::optional<std::wstring_view> ContextTail(std::wstring_view text, bool clipped) {
    auto low = [](wchar_t c) { return c >= 0xdc00 && c <= 0xdfff; };
    if (clipped && !text.empty() && low(text.front())) text.remove_prefix(1);
    size_t end = text.size();
    for (size_t count = 0; end && count < CONTEXT_CHARS; ++count) {
        wchar_t c = text[--end];
        if (low(c)) {
            if (!end || text[end - 1] < 0xd800 || text[end - 1] > 0xdbff)
                return std::nullopt;
            --end;
        } else if (c >= 0xd800 && c <= 0xdbff) {
            return std::nullopt;
        }
    }
    return text.substr(end);
}

// Win32 virtual keys used here (no windows.h in this header).
enum : uint32_t {
    VK_RETURN_ = 0x0D, VK_SPACE_ = 0x20, VK_LEFT_ = 0x25, VK_F6_ = 0x75,
};

struct Segment {
    int display_start = 0, display_end = 0;
};

enum class Phase { Empty, Composing, Converting, Selecting, Resizing, Predicting, Editing, Direct };
inline constexpr std::array<const char*, 8> kPhaseNames = {
    "empty", "composing", "converting", "selecting", "resizing", "predicting", "editing", "direct"
};

enum class GlobalCommand {
    None, Toggle, On, Off, Hiragana, Katakana, FullAlnum, Settings, Words, Menu,
    SendBackspace, SendDelete, SendLeft, SendRight, SendUp, SendDown, SendHome, SendEnd,
    SendPageUp, SendPageDown, SendEnter, SendEscape, SendTab,
};
inline bool OpensKeyboard(GlobalCommand command) {
    return command == GlobalCommand::Toggle || command == GlobalCommand::On ||
           command == GlobalCommand::Hiragana || command == GlobalCommand::Katakana ||
           command == GlobalCommand::FullAlnum;
}

// The send_* commands (KEYBIND §7.5): the key the application gets in place of the pressed one.
struct SentKey {
    const char* id;
    GlobalCommand command;
    uint32_t vk;
    bool extended;  // the navigation keys beside the main block
};
inline constexpr std::array<SentKey, 13> kSentKeys = {{
    {"send_backspace", GlobalCommand::SendBackspace, 0x08, false},
    {"send_delete", GlobalCommand::SendDelete, 0x2E, true},
    {"send_left", GlobalCommand::SendLeft, 0x25, true},
    {"send_right", GlobalCommand::SendRight, 0x27, true},
    {"send_up", GlobalCommand::SendUp, 0x26, true},
    {"send_down", GlobalCommand::SendDown, 0x28, true},
    {"send_home", GlobalCommand::SendHome, 0x24, true},
    {"send_end", GlobalCommand::SendEnd, 0x23, true},
    {"send_page_up", GlobalCommand::SendPageUp, 0x21, true},
    {"send_page_down", GlobalCommand::SendPageDown, 0x22, true},
    {"send_enter", GlobalCommand::SendEnter, 0x0D, false},
    {"send_escape", GlobalCommand::SendEscape, 0x1B, false},
    {"send_tab", GlobalCommand::SendTab, 0x09, false},
}};
inline const SentKey* SentKeyOf(GlobalCommand command) {
    for (const auto& sent : kSentKeys)
        if (sent.command == command) return &sent;
    return nullptr;
}
// What runs while the keyboard is closed (IME off in Windows' sense).
inline bool WorksClosed(GlobalCommand command) {
    return OpensKeyboard(command) || SentKeyOf(command);
}

inline GlobalCommand ParseGlobal(const std::string& id) {
    for (const auto& sent : kSentKeys)
        if (id == sent.id) return sent.command;
    if (id == "ime_toggle") return GlobalCommand::Toggle;
    if (id == "ime_on") return GlobalCommand::On;
    if (id == "ime_off") return GlobalCommand::Off;
    if (id == "mode_hiragana") return GlobalCommand::Hiragana;
    if (id == "mode_katakana") return GlobalCommand::Katakana;
    if (id == "mode_full_alnum") return GlobalCommand::FullAlnum;
    if (id == "open_settings") return GlobalCommand::Settings;
    if (id == "open_word_register") return GlobalCommand::Words;
    if (id == "open_menu") return GlobalCommand::Menu;
    return GlobalCommand::None;
}

struct KeyTable {
    struct Row {
        std::vector<unsigned> eat, pass;
        bool rest = false;
        bool Has(const std::vector<unsigned>& codes, unsigned code) const {
            return std::find(codes.begin(), codes.end(), code) != codes.end();
        }
    };
    std::string rev;
    std::array<Row, (size_t)Phase::Direct> phases;
    std::map<unsigned, GlobalCommand> global;

    bool Overrides(Phase phase, unsigned code) const {
        if (phase == Phase::Direct) return false;
        const auto& row = phases[(size_t)phase];
        return row.Has(row.eat, code) || row.Has(row.pass, code);
    }
    bool Sends(Phase phase, unsigned code) const {
        if (phase == Phase::Direct) return false;
        const auto& row = phases[(size_t)phase];
        return row.Has(row.eat, code) || (row.rest && !row.Has(row.pass, code));
    }
    GlobalCommand GlobalAt(Phase phase, unsigned code) const {
        auto found = global.find(code);
        return found == global.end() || Overrides(phase, code) ? GlobalCommand::None : found->second;
    }
};

inline std::optional<KeyTable> ParseKeyTable(const tip_json::Value& json) {
    const auto& phases = json.Get("phases");
    const auto& global = json.Get("global");
    if (json.kind != tip_json::Value::Object || json.Get("rev").kind != tip_json::Value::String ||
        phases.kind != tip_json::Value::Object || global.kind != tip_json::Value::Array) return {};
    KeyTable table;
    table.rev = json.Get("rev").text;
    for (size_t i = 0; i < table.phases.size(); ++i) {
        const auto& from = phases.Get(kPhaseNames[i]);
        auto& row = table.phases[i];
        if (i == (size_t)Phase::Editing && from.kind == tip_json::Value::Null) {
            row = table.phases[(size_t)Phase::Converting];  // earlier engines omit this phase
            continue;
        }
        const auto& eat = from.Get("eat");
        const auto& pass = from.Get("pass");
        if (eat.kind != tip_json::Value::Array || pass.kind != tip_json::Value::Array) return {};
        auto read_codes = [](const auto& list, auto& out) {
            for (const auto& item : list.array) {
                long long code;
                if (item.Int(code) && code > 0 && code <= 0x7FF) out.push_back((unsigned)code);
            }
        };
        read_codes(eat, row.eat);
        read_codes(pass, row.pass);
        row.rest = from.Get("rest").text == "eat";
    }
    for (const auto& entry : global.array) {
        long long code;
        auto command = ParseGlobal(entry.Get("command").text);
        if (command != GlobalCommand::None && entry.Get("code").Int(code) && code > 0 && code <= 0x7FF)
            table.global[(unsigned)code] = command;
    }
    return table;
}

inline KeyTable DefaultKeyTable() {
    const std::string text(kDefaultKeyTable);
    tip_json::Value json;
    tip_json::Parser(text).Parse(json);
    return ParseKeyTable(json).value(); // generated from the engine preset at build time
}

struct ResolvedKey {
    long long seq;
    bool eat;
    std::optional<GlobalCommand> global;
};

// One line from the broker. Every field has a default; a field that is absent
// or of another type takes it (DESIGN「互換の規則」: unknown fields are ignored, missing ones
// default, nothing is counted or rejected).
struct Message {
    // The broker's own fields.
    bool hello = false;  // the reply to hello: {"proto":1,"state":..,"warnings":[..],"keymap":{..}}
    std::string event;  // "state", "reset", or empty
    std::string state;  // ready, starting, down
    bool has_seq = false;
    long long seq = 0;
    std::optional<KeyTable> keymap;
    // The engine's reply (yuragi.ime.server.snapshot).
    bool engine = false;  // carries the engine's state (not just {"seq","state"})
    std::string composition, commit;  // UTF-8
    bool direct = false, converted = false, pending = false;
    bool eat_pending = false;
    std::optional<bool> eat;
    std::optional<GlobalCommand> global;
    std::vector<ResolvedKey> resolved_keys;
    std::optional<Phase> phase;
    std::string input_mode;
    bool predicting = false, error = false, has_next_page = false;
    bool suggesting = false, suggestion_only = false;
    bool fsm_idle = true;
    int n_tokens = 0, focus = -1, page = 0, cand_index = 0;
    int caret = -1, commit_caret = -1;
    bool has_timer = false;
    uint64_t timer = 0;
    std::optional<uint64_t> suggest_at;
    std::vector<std::string> candidates, candidate_notes;
    std::vector<Segment> segments;

    bool ShowsCandidates() const { return !direct && (converted || suggesting) && !candidates.empty(); }
};

inline bool ReadInt(const tip_json::Value& v, const char* key, int& out) {
    long long n;
    if (!v.Get(key).Int(n) || n < -2147483647LL || n > 2147483647LL) return false;
    out = (int)n;
    return true;
}
inline void ReadBool(const tip_json::Value& v, const char* key, bool& out) {
    const auto& x = v.Get(key);
    if (x.kind == tip_json::Value::Boolean) out = x.boolean;
}
inline void ReadText(const tip_json::Value& v, const char* key, std::string& out) {
    const auto& x = v.Get(key);
    if (x.kind == tip_json::Value::String) out = x.text;
}
inline std::optional<GlobalCommand> ReadGlobal(const tip_json::Value& v) {
    auto command = ParseGlobal(v.Get("global").text);
    if (command == GlobalCommand::None) return std::nullopt;
    return command;
}

// false only when the line is not a JSON object.
inline bool ParseMessage(const std::string& line, Message& m) {
    tip_json::Value v;
    if (!tip_json::Parser(line).Parse(v) || v.kind != tip_json::Value::Object) return false;
    m = Message();
    m.hello = v.Get("proto").kind == tip_json::Value::Number;
    ReadText(v, "event", m.event);
    ReadText(v, "state", m.state);
    m.keymap = ParseKeyTable(v.Get("keymap"));
    m.has_seq = v.Get("seq").Int(m.seq);
    m.engine = m.has_seq && m.state.empty();
    ReadText(v, "composition", m.composition);
    ReadText(v, "commit", m.commit);
    ReadBool(v, "direct", m.direct);
    ReadBool(v, "converted", m.converted);
    ReadBool(v, "pending", m.pending);
    ReadBool(v, "eat_pending", m.eat_pending);
    if (v.Get("eat").kind == tip_json::Value::Boolean) m.eat = v.Get("eat").boolean;
    m.global = ReadGlobal(v);
    for (const auto& result : v.Get("resolved_keys").array) {
        long long seq;
        if (result.Get("seq").Int(seq) && result.Get("eat").kind == tip_json::Value::Boolean)
            m.resolved_keys.push_back({seq, result.Get("eat").boolean, ReadGlobal(result)});
    }
    for (size_t i = 0; i < kPhaseNames.size(); ++i)
        if (v.Get("phase").text == kPhaseNames[i]) m.phase = (Phase)i;
    ReadText(v, "input_mode", m.input_mode);
    ReadBool(v, "predicting", m.predicting);
    ReadBool(v, "suggesting", m.suggesting);
    ReadBool(v, "suggestion_only", m.suggestion_only);
    ReadBool(v, "error", m.error);
    ReadBool(v, "has_next_page", m.has_next_page);
    const auto& fsm = v.Get("fsm");
    if (fsm.kind == tip_json::Value::String) m.fsm_idle = fsm.text == "S1";
    ReadInt(v, "n_tokens", m.n_tokens);
    ReadInt(v, "focus", m.focus);
    ReadInt(v, "caret", m.caret);
    ReadInt(v, "commit_caret", m.commit_caret);
    ReadInt(v, "candidate_page", m.page);
    ReadInt(v, "cand_index", m.cand_index);
    long long timer;
    if (v.Get("timer").Int(timer) && timer >= 0) {
        m.has_timer = true;
        m.timer = (uint64_t)timer;
    }
    if (v.Get("suggest_at").Int(timer) && timer >= 0) m.suggest_at = (uint64_t)timer;
    const auto& candidates = v.Get("candidates").array;
    const auto& notes = v.Get("candidate_notes").array;
    for (size_t i = 0; i < candidates.size(); ++i) {
        if (candidates[i].kind != tip_json::Value::String) continue;
        m.candidates.push_back(candidates[i].text);
        if (!notes.empty()) {
            m.candidate_notes.push_back(i < notes.size() && notes[i].kind == tip_json::Value::String
                                        ? notes[i].text : std::string());
        }
    }
    for (const auto& s : v.Get("segments").array) {
        Segment seg;
        if (!ReadInt(s, "display_start", seg.display_start) ||
            !ReadInt(s, "display_end", seg.display_end))
            continue;
        m.segments.push_back(seg);
    }
    return true;
}

// DESIGN「見えている文字の確定」: the text on screen stays and the conversion ends (nothing is erased).
inline bool CommitsVisibleText(const Message& m) {
    return m.event == "reset" || m.error || m.state == "down";
}

// -- what the user sees (DESIGN「状態」) ---------------------------------------------------

enum class Mode { Normal, Preparing, Stopped, Excluded };

// Why there is no connection to the broker.
enum class Link { Connected, Connecting, Unreachable, NotAllowed };
//   Connecting   waiting for the pipe (a broker was just started)
//   Unreachable  no broker, and starting one did not give a pipe in time
//   NotAllowed   this process must not start one (DESIGN「ブローカーを起動する条件」: another version,
//                sandboxed or elevated): it only ever connects; or the pipe's server is not the broker

inline Mode ModeFor(Link link, const std::string& state) {
    switch (link) {
        case Link::Connecting: return Mode::Preparing;
        case Link::Unreachable: return Mode::Stopped;
        case Link::NotAllowed: return Mode::Excluded;
        case Link::Connected: break;
    }
    if (state == "ready") return Mode::Normal;
    if (state == "down") return Mode::Stopped;
    return Mode::Preparing;  // starting, or before the hello reply
}

// Keys go to the engine only when it is ready; otherwise (also while it is
// starting) they pass through as in direct input.
inline bool SendsKeys(Mode mode) { return mode == Mode::Normal; }
// The toggle key also works while preparing: the input mode changes here, and
// the engine is told once it is ready (DESIGN「使えない間の打鍵」).
inline bool Toggles(Mode mode) { return mode == Mode::Normal || mode == Mode::Preparing; }

// The taskbar glyph and whether it is drawn faint.
inline const char* Glyph(Mode mode, bool direct) {
    switch (mode) {
        // ゆ and Y (yuragi), not あ/A: told apart from Microsoft IME at a glance.
        case Mode::Normal: return direct ? "Y" : "\xE3\x82\x86";  // ゆ
        case Mode::Preparing: return direct ? "Y" : "\xE3\x82\x86";
        case Mode::Stopped: return "!";
        case Mode::Excluded: return "Y";
    }
    return "Y";
}
inline bool Faint(Mode mode) { return mode == Mode::Preparing; }

// The IME menu (DESIGN「メニュー」).
enum MenuItem { MENU_TOGGLE = 1, MENU_ADMIN = 2, MENU_RETRY = 3, MENU_PREPARING = 5 };
inline std::vector<int> MenuFor(Mode mode) {
    switch (mode) {
        case Mode::Normal: return {MENU_TOGGLE, MENU_ADMIN};
        case Mode::Preparing: return {MENU_PREPARING, MENU_ADMIN};
        case Mode::Stopped: return {MENU_RETRY, MENU_ADMIN};
        case Mode::Excluded: return {MENU_ADMIN};
    }
    return {};
}

// The one-line notice under the caret (DESIGN「小さな表示」).
enum class Notice { None, Stopped };

// -- keys -------------------------------------------------------------------------

struct Mods {
    bool shift = false, ctrl = false, alt = false, win = false;
    bool Shortcut() const { return ctrl || alt || win; }
    unsigned Bits() const { return shift + 2u * ctrl + 4u * alt + 8u * win; }
};

struct Chord {
    uint32_t vk;
    Mods mods;
    unsigned Code() const { return vk | (mods.Bits() << 8); }
};

inline bool AltVk(uint32_t vk) { return vk == 0x12 || vk == 0xA4 || vk == 0xA5; }
inline bool ModifierVk(uint32_t vk) {
    return (vk >= 0x10 && vk <= 0x12) || vk == 0x5B || vk == 0x5C ||
           (vk >= 0xA0 && vk <= 0xA5);
}

inline Chord NormalizeKey(uint32_t vk, Mods mods) {
    // kbd101 reports the translated virtual key even if GetKeyState
    // has moved on. Recover the modifiers from that event's VK.
    Mods shift{}, ctrl{}, alt{};
    shift.shift = ctrl.ctrl = alt.alt = true;
    shift.win = ctrl.win = alt.win = mods.win;
    switch (vk) {
        case 0x19: return {0xC0, alt};   // VK_KANJI
        case 0xF0: return {0x14, shift}; // VK_DBE_ALPHANUMERIC
        case 0xF1: return {0x14, alt};   // VK_DBE_KATAKANA
        case 0xF2: return {0x14, ctrl};  // VK_DBE_HIRAGANA
        case 0xF3: case 0xF4: return {0xC0, ctrl}; // VK_DBE_SBCSCHAR / DBCSCHAR
        default: return {vk, mods};
    }
}

// Generated from the same keyboard as the engine's key table (data/keyboards).
inline bool CharacterVk(uint32_t vk) {
    return std::binary_search(kCharacterVks.begin(), kCharacterVks.end(), vk);
}

// keys.THUMBS: Space, 無変換 and 変換 on every keyboard.
inline bool ThumbVk(uint32_t vk) { return vk == VK_SPACE_ || vk == 0x1C || vk == 0x1D; }

inline bool Typing(Chord chord) {
    return !chord.mods.Shortcut() &&
           (CharacterVk(chord.vk) || (ThumbVk(chord.vk) && !chord.mods.shift));
}

struct Local {
    Phase phase = Phase::Empty;
    bool unsettled = false;
};

enum class Scope { Unknown, Allowed, Password, Unavailable };
enum class Deliver { Wait, Raw, Decide };
struct FieldFacts {
    bool has_document;
    bool eligible;
    Scope scope;
};

inline bool AllowsInput(Scope scope, bool carrying) {
    return scope == Scope::Allowed || (scope == Scope::Unavailable && !carrying);
}

inline Deliver DeliverHeld(const FieldFacts& field, uint64_t now, std::optional<uint64_t> carry_started) {
    if (!field.has_document || !field.eligible || field.scope == Scope::Password) return Deliver::Raw;
    if (AllowsInput(field.scope, carry_started.has_value())) return Deliver::Decide;
    return carry_started && now - *carry_started < KEY_BUDGET_MS ? Deliver::Wait : Deliver::Raw;
}

inline bool KanaLockKey(uint32_t vk, uint32_t flags) {
    return vk == 0x15 && ((flags >> 16) & 0xFF) == 0x3A; // kbd101 already changed the lock
}

inline bool UntranslatedJisKey(uint32_t vk, uint32_t flags) {
    const unsigned scan = (flags >> 16) & 0x1FF;  // include the extended bit
    return (scan == 0x79 && vk == 0xFF) || (scan == 0x7B && vk == 0xEB);
}

inline bool HoldDuringCarry(Chord chord, uint32_t raw_vk, uint32_t flags, bool is_global) {
    return !chord.mods.win && !ModifierVk(raw_vk) && !KanaLockKey(raw_vk, flags) &&
           !UntranslatedJisKey(raw_vk, flags) &&
           (!chord.mods.alt || chord.mods.ctrl || is_global);
}

// A replay opens a window between the echoed down and the next pump. Once
// the queue follows a focus change, subsequent notifications use its root.
class Carry {
public:
    void ReplayPassed(uintptr_t root) { replay_root_ = root; }
    void Pumped() { replay_root_ = 0; }

    bool OnFocusMoved(uintptr_t root, bool held_empty, uint64_t now) {
        if (!held_empty && root) {
            if (Active() && SameRoot(root)) return true;
            if (!Active() && root == replay_root_) {
                Adopt(root, now);
                return true;
            }
        }
        Finished();
        return false;
    }

    void Adopt(uintptr_t root, uint64_t now) {
        if (!Active() || !SameRoot(root)) started_ = now;
        root_ = root;
        Pumped();
    }

    void Finished() {
        started_.reset();
        root_ = 0;
        Pumped();
    }

    bool Active() const { return started_.has_value(); }
    uint64_t Started() const { return started_.value(); }
    bool SameRoot(uintptr_t root) const { return root && root == root_; }

private:
    uintptr_t replay_root_ = 0, root_ = 0;
    std::optional<uint64_t> started_;
};

enum class GlobalUse { None, Run, Ask };

inline GlobalUse UseGlobal(unsigned code, const Local& local, const KeyTable& table) {
    auto found = table.global.find(code);
    if (found == table.global.end()) return GlobalUse::None;
    if (local.phase == Phase::Direct) return GlobalUse::Run;
    // A key sent in place of another goes after the input: the engine commits it first.
    const bool sent = SentKeyOf(found->second) != nullptr;
    if (!local.unsettled) {
        if (table.Overrides(local.phase, code)) return GlobalUse::None;
        return sent && local.phase != Phase::Empty ? GlobalUse::Ask : GlobalUse::Run;
    }
    for (size_t i = 0; i < table.phases.size(); ++i)
        if (table.Overrides(static_cast<Phase>(i), code)) return GlobalUse::Ask;
    return sent ? GlobalUse::Ask : GlobalUse::Run;
}

enum class Take { Pass, Send };

inline Take WantKey(Chord chord, const Local& local, const KeyTable& table) {
    if (local.phase == Phase::Direct || chord.mods.win || ModifierVk(chord.vk) ||
        (chord.mods.alt && !chord.mods.ctrl)) return Take::Pass;
    switch (UseGlobal(chord.Code(), local, table)) {
        case GlobalUse::Run: return Take::Pass;
        case GlobalUse::Ask: return Take::Send;
        case GlobalUse::None: break;
    }
    if (Typing(chord)) return Take::Send;
    auto sends = [&](Phase phase) { return table.Sends(phase, chord.Code()); };
    if (sends(local.phase)) return Take::Send;
    if (local.unsettled) {
        for (Phase phase : {Phase::Composing, Phase::Converting, Phase::Selecting,
                            Phase::Resizing, Phase::Predicting, Phase::Editing}) {
            if (sends(phase)) return Take::Send;
        }
    }
    return Take::Pass;
}

// -- order (DESIGN「打鍵の処理」) ---------------------------------------------------------------

// The requests in flight, oldest first. Replies come back in the order the
// requests went out (one reader, one broker, one engine thread).
class InFlight {
public:
    long long Next(bool blocking = true) {
        long long seq = ++last_;
        sent_.push_back({seq, blocking});
        return seq;
    }
    // A reply for seq: true when it is the oldest one in flight (as it must be);
    // replies for requests that were given up are dropped by the caller.
    bool Answer(long long seq) {
        while (!sent_.empty() && sent_.front().seq < seq) sent_.pop_front();  // never answered
        if (sent_.empty() || sent_.front().seq != seq) return false;
        sent_.pop_front();
        return true;
    }
    bool Waiting() const {
        return std::any_of(sent_.begin(), sent_.end(), [](const Sent& s) { return s.blocking; });
    }
    bool Waiting(long long seq) const {
        for (const auto& s : sent_)
            if (s.seq == seq) return true;
        return false;
    }
    void Clear() { sent_.clear(); }
    long long Last() const { return last_; }  // the newest number given out

private:
    struct Sent {
        long long seq;
        bool blocking;  // a suggestion only changes the popup
    };
    std::deque<Sent> sent_;
    long long last_ = 0;
};

// DESIGN「接続」: limit connect signals from activation and kana keystrokes.
// Explicit retry and settings shortcuts bypass this gate.
class ConnectGate {
public:
    bool Allow(uint64_t now) {
        if (tried_ && now - last_ < CONNECT_MIN_INTERVAL_MS) return false;
        tried_ = true;
        last_ = now;
        return true;
    }

private:
    bool tried_ = false;
    uint64_t last_ = 0;
};

// DESIGN「ブローカーを起動する条件」: whether this TIP may start the broker. Every condition must hold.
// The broker's own single-instance lock and CONNECT_MIN_INTERVAL_MS bound how
// often it is started; there is no count.
struct SpawnFacts {
    bool tag_matches = false;  // HKCU\Software\yuragi-ime\Tag == this DLL's tag
    bool medium_integrity = false;  // not sandboxed (AppContainer/low), not elevated
};
inline bool MaySpawn(const SpawnFacts& f) {
    return f.tag_matches && f.medium_integrity;
}

// Keep the candidate list below the caret unless its bottom would leave the work area.
inline int CandidateTop(int caret_top, int caret_bottom, int height, int gap, int work_bottom) {
    int below = caret_bottom + gap;
    return below + height > work_bottom ? caret_top - gap - height : below;
}

// Popup colors use the GDI byte order so the painter can pass them through.
constexpr uint32_t PopupRgb(int r, int g, int b) { return r | (g << 8) | (b << 16); }

struct PopupColors {
    uint32_t surface, text, secondary, border, selected, selected_text, mark;
};

inline PopupColors PopupPalette(bool dark, uint32_t accent,
                                std::optional<PopupColors> high_contrast) {
    if (high_contrast) return *high_contrast;
    if (dark) return {PopupRgb(38, 39, 42), PopupRgb(246, 246, 247), PopupRgb(180, 183, 190),
                      PopupRgb(82, 83, 88), PopupRgb(57, 59, 64), PopupRgb(246, 246, 247), accent};
    return {PopupRgb(252, 252, 253), PopupRgb(28, 29, 32), PopupRgb(87, 89, 96),
            PopupRgb(211, 212, 216), PopupRgb(235, 237, 241), PopupRgb(28, 29, 32), accent};
}

struct PopupMetrics {
    int inset, padding, row, number_column, note_gap, note_max;
    int min_width, max_width, footer, rounding, mark_width, mark_height, gap;
    int text_font, small_font;
};

inline PopupMetrics ScalePopup(int dpi) {
    auto px = [dpi](int dip) { return (dip * dpi + 48) / 96; };
    return {px(5), px(12), px(32), px(22), px(16), px(72), px(148), px(520),
            px(26), px(8), px(3), px(16), px(4), px(18), px(14)};
}

struct PopupRect { int left, top, right, bottom; };

struct PopupLayout {
    int width, height, text_left, text_right, note_left;
    int rows, selected, footer_top;

    PopupRect Row(const PopupMetrics& m, int index) const {
        const int y = m.inset + index * m.row;
        return {m.inset, y, width - m.inset, y + m.row};
    }
};

inline PopupLayout MeasurePopup(const PopupMetrics& m, int work_width, int rows, int selected,
                                int text, int notes, int footer, bool notice, bool numbered = true) {
    const int left = m.inset + m.padding + (notice || !numbered ? 0 : m.number_column);
    const int right_padding = m.inset + m.padding;
    const int limit = std::min(m.max_width, work_width);
    const int note_width = std::min({notes, m.note_max,
                                     std::max(0, limit - left - right_padding - m.note_gap) / 2});
    const int note_column = note_width > 0 ? m.note_gap + note_width : 0;
    const int width = std::min(limit, std::max({notice ? 0 : m.min_width,
        left + text + note_column + right_padding, footer + 2 * right_padding}));
    const int bottom = 2 * m.inset + rows * m.row;
    return {width, bottom + (footer > 0 ? m.footer : 0), left,
            width - right_padding - note_column, width - right_padding - note_width,
            rows, selected >= 0 && selected < rows ? selected : -1, bottom};
}

// Requests (the TIP -> broker messages, DESIGN「通信」).
inline std::string Hello() {
    return R"({"op":"hello","proto":1})";
}
inline std::string ModsJson(Mods m) {
    std::string out = "[";
    auto add = [&](const char* name) {
        if (out.size() > 1) out += ',';
        out += tip_json::Quote(name);
    };
    if (m.shift) add("shift");
    if (m.ctrl) add("ctrl");
    if (m.alt) add("alt");
    if (m.win) add("win");
    return out + ']';
}
struct KeyContext {
    std::optional<std::string> text;
    std::optional<long long> after_commit_seq;
    bool disconnected = false;
};

inline std::string KeyRequest(long long seq, bool down, uint32_t vk, uint64_t t, Mods mods,
                              const KeyContext* context = nullptr) {
    std::string request = "{\"seq\":" + std::to_string(seq) + ",\"op\":\"" + (down ? "down" : "up") +
           "\",\"vk\":" + std::to_string(vk) + ",\"t\":" + std::to_string(t) +
           ",\"mods\":" + ModsJson(mods);
    if (context) {
        request += ",\"left_context\":" +
                   (context->text ? tip_json::Quote(*context->text) : "null");
        if (context->after_commit_seq)
            request += ",\"after_commit_seq\":" + std::to_string(*context->after_commit_seq);
        else if (context->disconnected)
            request += ",\"after_commit_seq\":null";
    }
    return request + "}";
}
inline std::string OpRequest(long long seq, const std::string& op, const std::string& extra = "") {
    return "{\"seq\":" + std::to_string(seq) + ",\"op\":\"" + op + "\"" +
           (extra.empty() ? "" : "," + extra) + "}";
}

}  // namespace tip_logic
