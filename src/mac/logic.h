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

// One line from the watcher to a session (tip_logic::Message; DESIGN「返事の項目」).
@interface YRMessage : NSObject
@property(readonly) NSString *event;  // "state", "reset", "keymap", "lm_done", or empty
@property(readonly) NSString *state;  // of the hello reply, a state event, or a request the engine did not get
@property(readonly) BOOL hasSeq;
@property(readonly) long long seq;
@property(readonly, nullable) YRKeyTable *keymap;
@property(readonly) NSString *composition, *commit, *global;
@property(readonly) BOOL pending, eatPending, again, error, suggestionOnly, hasPhase, hasEat, eat;
@property(readonly) YRPhase phase;
@property(readonly) NSInteger focus, caret;  // -1: none
@property(readonly) BOOL hasTimer;
@property(readonly) uint64_t timer;
@property(readonly) NSArray<NSValue *> *segments;  // NSRange of code points in composition
// The candidate window: the focused clause's page, or predictions offered without the focus (suggesting).
@property(readonly) BOOL showsCandidates, suggesting, hasNextPage;
@property(readonly) NSArray<NSString *> *candidates, *candidateNotes;  // notes: empty, or one per candidate
@property(readonly) NSInteger candIndex, page;
@property(readonly) BOOL hasSuggestAt;  // when to send "suggest"
@property(readonly) uint64_t suggestAt;
// nil when the line is not a JSON object.
+ (nullable YRMessage *)parse:(NSString *)line;
@end

// What the watcher asks of the process around it (broker::Platform). All on the main thread.
@protocol YRWatcherPlatform
- (nullable NSString *)startEngine;  // nil: started; else why not
- (void)writeEngine:(NSString *)line;
- (void)killEngine;  // engineExit: follows once its output has been read
- (void)writeSession:(uint64_t)sid line:(NSString *)line;  // called inside a watcher call: deliver after it returns
- (void)engineStopped:(NSString *)reason;  // given up: "exited" or "hang"
- (void)openAdmin;
- (void)log:(NSString *)line;
@end

typedef NS_ENUM(NSInteger, YRState) { YRStateStarting, YRStateReady, YRStateDown };

// The engine's watcher (broker::Broker; DESIGN「見張り」): starts it again when it ends, gives up
// after repeated exits, ends one that does not answer.
@interface YRWatcher : NSObject
- (instancetype)initWithPlatform:(id<YRWatcherPlatform>)platform;
@property(readonly) YRState state;
@property(readonly) int64_t nextDeadline;  // milliseconds on the platform's clock; INT64_MAX: none
- (void)start;
- (void)sessionOpened:(uint64_t)sid;  // an input field: connected, and its hello said
- (void)peerConnected:(uint64_t)sid;  // the settings window's connection: it says hello itself
- (void)sessionClosed:(uint64_t)sid;
- (void)session:(uint64_t)sid line:(NSString *)line;
- (void)engineLine:(NSString *)line;
- (void)engineStderrLine:(NSString *)line;
- (void)engineExit:(int)code;
- (void)timer;
- (void)retry;
@end

NS_ASSUME_NONNULL_END
