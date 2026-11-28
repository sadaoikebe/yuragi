#import "logic.h"

#include <map>
#include <memory>
#include "tip_logic.h"
#include "../broker/broker_core.h"

static NSString *Text(const std::string &s) {
    return [[NSString alloc] initWithBytes:s.data() length:s.size() encoding:NSUTF8StringEncoding] ?: @"";
}

@implementation YRKeyTable {
    tip_logic::KeyTable _table;
}
- (instancetype)initWithTable:(const tip_logic::KeyTable &)table {
    if ((self = [super init])) _table = table;
    return self;
}
- (NSString *)rev { return Text(_table.rev); }
- (BOOL)sendsVk:(uint32_t)vk shift:(BOOL)shift ctrl:(BOOL)ctrl alt:(BOOL)alt win:(BOOL)win
          phase:(YRPhase)phase unsettled:(BOOL)unsettled {
    tip_logic::Mods mods;
    mods.shift = shift; mods.ctrl = ctrl; mods.alt = alt; mods.win = win;
    tip_logic::Local local;
    local.phase = (tip_logic::Phase)phase;
    local.unsettled = unsettled;
    return tip_logic::WantKey(tip_logic::NormalizeKey(vk, mods), local, _table) == tip_logic::Take::Send;
}
@end

@implementation YRMessage
+ (YRMessage *)parse:(NSString *)line {
    const std::string text(line.UTF8String ?: "");
    tip_logic::Message m;
    if (!tip_logic::ParseMessage(text, m)) return nil;
    tip_json::Value v;
    tip_json::Parser(text).Parse(v);
    YRMessage *out = [YRMessage new];
    out->_event = Text(m.event);
    out->_state = Text(m.state);
    out->_hasSeq = m.has_seq;
    out->_seq = m.seq;
    if (m.keymap) out->_keymap = [[YRKeyTable alloc] initWithTable:*m.keymap];
    out->_composition = Text(m.composition);
    out->_commit = Text(m.commit);
    out->_global = Text(v.Get("global").text);
    out->_pending = m.pending;
    out->_eatPending = m.eat_pending;
    out->_again = m.again;
    out->_error = m.error;
    out->_suggestionOnly = m.suggestion_only;
    out->_hasPhase = m.phase.has_value();
    out->_phase = (YRPhase)m.phase.value_or(tip_logic::Phase::Empty);
    out->_hasEat = m.eat.has_value();
    out->_eat = m.eat.value_or(false);
    out->_focus = m.focus;
    out->_caret = m.caret;
    out->_hasTimer = m.has_timer;
    out->_timer = m.timer;
    NSMutableArray *segments = [NSMutableArray new];
    for (const auto &s : m.segments)
        [segments addObject:[NSValue valueWithRange:NSMakeRange(s.display_start, s.display_end - s.display_start)]];
    out->_segments = segments;
    out->_showsCandidates = m.ShowsCandidates();
    out->_suggesting = m.suggesting;
    out->_hasNextPage = m.has_next_page;
    NSMutableArray *candidates = [NSMutableArray new], *notes = [NSMutableArray new];
    for (const auto &c : m.candidates) [candidates addObject:Text(c)];
    for (const auto &n : m.candidate_notes) [notes addObject:Text(n)];
    out->_candidates = candidates;
    out->_candidateNotes = notes;
    out->_candIndex = m.cand_index;
    out->_page = m.page;
    out->_hasSuggestAt = m.suggest_at.has_value();
    out->_suggestAt = m.suggest_at.value_or(0);
    return out;
}
@end


namespace {
class Platform : public broker::Platform {
public:
    __weak id<YRWatcherPlatform> to;
    int64_t Now() override { return (int64_t)(NSProcessInfo.processInfo.systemUptime * 1000); }
    bool StartEngine(std::string &error) override {
        NSString *problem = [to startEngine];
        if (problem) error = problem.UTF8String;
        return !problem;
    }
    void WriteEngine(const std::string &line) override { [to writeEngine:Text(line)]; }
    void KillEngine() override { [to killEngine]; }
    void WriteClient(broker::ClientId client, const std::string &line) override {
        [to writeSession:client line:Text(line)];
    }
    void NotifyStopped(broker::Stop reason) override { [to engineStopped:Text(broker::StopName(reason))]; }
    void ClearStopped() override {}
    void OpenAdmin() override { [to openAdmin]; }
    void Log(const std::string &line) override { [to log:Text(line)]; }
    void Quit() override {}
};
}  // namespace

@implementation YRWatcher {
    id<YRWatcherPlatform> _owner;
    Platform _platform;
    std::unique_ptr<broker::Broker> _broker;
}
- (instancetype)initWithPlatform:(id<YRWatcherPlatform>)platform {
    if ((self = [super init])) {
        _owner = platform;
        _platform.to = platform;
        _broker = std::make_unique<broker::Broker>(_platform);
    }
    return self;
}
- (YRState)state {
    switch (_broker->State()) {
        case broker::EngineState::Ready: return YRStateReady;
        case broker::EngineState::Failed: return YRStateDown;
        case broker::EngineState::Starting: break;
    }
    return YRStateStarting;
}
- (int64_t)nextDeadline { return _broker->NextDeadline(); }
- (void)start { _broker->Start(); }
- (void)sessionOpened:(uint64_t)sid {
    _broker->OnClientConnected(sid, false);
    _broker->OnClientLine(sid, tip_logic::Hello());
}
- (void)peerConnected:(uint64_t)sid { _broker->OnClientConnected(sid, false); }
- (void)sessionClosed:(uint64_t)sid { _broker->OnClientClosed(sid); }
- (void)session:(uint64_t)sid line:(NSString *)line { _broker->OnClientLine(sid, line.UTF8String ?: ""); }
- (void)engineLine:(NSString *)line { _broker->OnEngineLine(line.UTF8String ?: ""); }
- (void)engineStderrLine:(NSString *)line { _broker->OnEngineStderrLine(line.UTF8String ?: ""); }
- (void)engineExit:(int)code { _broker->OnEngineExit(code); }
- (void)timer { _broker->OnTimer(); }
- (void)retry { _broker->Retry(); }
@end
