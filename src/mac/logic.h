// What the input program takes from src/tip/tip_logic.h (the decisions shared with the Windows TIP):
// reading the engine's lines, and whether a key goes to the engine.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

// tip_logic::Phase, in its order.
typedef NS_ENUM(NSInteger, YRPhase) {
    YRPhaseEmpty, YRPhaseComposing, YRPhaseConverting, YRPhaseSelecting, YRPhaseResizing,
    YRPhasePredicting, YRPhaseEditing, YRPhaseDirect,
};

// The engine's table of the keys it takes in each phase (KEYBIND §7).
@interface YRKeyTable : NSObject
@property(readonly) NSString *rev;
// tip_logic::WantKey: true when the key goes to the engine. unsettled: a reply is awaited.
- (BOOL)sendsVk:(uint32_t)vk shift:(BOOL)shift ctrl:(BOOL)ctrl alt:(BOOL)alt win:(BOOL)win
          phase:(YRPhase)phase unsettled:(BOOL)unsettled;
@end

// One line from the engine (tip_logic::Message; DESIGN「返事の項目」).
@interface YRMessage : NSObject
@property(readonly) BOOL ready;  // {"ready":true,...}
@property(readonly) NSString *event;  // "lm_done", "warning", "keymap", or empty
@property(readonly) BOOL hasSid, hasSeq;
@property(readonly) long long sid, seq;
@property(readonly, nullable) YRKeyTable *keymap;
@property(readonly) NSString *composition, *commit, *global;
@property(readonly) BOOL pending, eatPending, again, error, suggestionOnly, hasPhase, hasEat, eat;
@property(readonly) YRPhase phase;
@property(readonly) NSInteger focus, caret;  // -1: none
@property(readonly) BOOL hasTimer;
@property(readonly) uint64_t timer;
@property(readonly) NSArray<NSValue *> *segments;  // NSRange of code points in composition
// nil when the line is not a JSON object.
+ (nullable YRMessage *)parse:(NSString *)line;
@end

NS_ASSUME_NONNULL_END
