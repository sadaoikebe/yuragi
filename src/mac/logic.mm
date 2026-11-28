#import "logic.h"

#include <map>
#include "tip_logic.h"

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
    out->_ready = v.Get("ready").kind == tip_json::Value::Boolean && v.Get("ready").boolean;
    out->_event = Text(m.event);
    out->_hasSid = v.Get("sid").Int(out->_sid);
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
