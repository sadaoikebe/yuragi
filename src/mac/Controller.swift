// One input field's side of the input program (MACOS.md §4.2): takes the keys, asks the engine,
// draws the text being converted, commits.
import Carbon
import Cocoa
import InputMethodKit

/// DESIGN「定数」 KEY_BUDGET_MS: how long one key may keep the application waiting.
let keyBudget = 0.2
/// Marked text for an eaten key that shows nothing yet (the chord is still being judged): a zero
/// width space. Chromium types the key's own character when an eaten key leaves no marked text
/// and inserts nothing (docs/MACOS.md §6.4).
let waitingMark = "\u{200B}"

@objc(YuragiController)
final class YuragiController: IMKInputController, EngineSession, KeyUpReceiver {
    private var sid = 0
    private var phase = YRPhase.empty
    private var shown = ""  // the marked text on screen
    private var placeholder = false  // shown is only `waitingMark`
    private var inserted = false  // a reply committed text since handle() began
    private var waiting: [Int] = []  // requests without a reply yet, oldest first
    private var awaited: Int?  // the down handle() is waiting for
    private var awaitedEat: Bool?  // what its reply said
    private var ignoreBefore = 0  // replies to requests older than this change nothing (a reset followed)
    private var roman = false
    private var timer: DispatchSourceTimer?

    override init!(server: IMKServer!, delegate: Any!, client inputClient: Any!) {
        super.init(server: server, delegate: delegate, client: inputClient)
        sid = Engine.shared.open(self)
    }

    deinit { Engine.shared.close(sid) }

    private var field: IMKTextInput? { client() }

    // -- keys ---------------------------------------------------------------------------

    override func handle(_ event: NSEvent!, client sender: Any!) -> Bool {
        guard let event = event, event.type == .keyDown else { return false }
        let tap = KeyTap.shared
        // Every down the tap saw is answered here, also the ones that are not sent on.
        let real = event.isARepeat ? nil : tap.arrive(event.keyCode)
        guard let (seq, vk) = send(event, at: real) else {
            if Log.debug { Log.write("passed \(event.keyCode)") }
            if !event.isARepeat { tap.settle(event.keyCode, vk: 0, sentTo: nil) }
            return false
        }
        if !event.isARepeat {
            tap.settle(event.keyCode, vk: vk, sentTo: real != nil ? self : nil)
            // A key the tap did not see was made by a program: it is not held.
            if real == nil { request("up", ["vk": vk, "mods": [String]()]) }
        }
        awaited = seq
        awaitedEat = nil
        inserted = false
        let hadText = !shown.isEmpty
        let answered = Engine.shared.wait(until: Date(timeIntervalSinceNow: keyBudget)) { !self.waiting.contains(seq) }
        awaited = nil
        if !answered { Log.write("no reply within the key budget") }
        if Log.debug { Log.write("handled seq \(seq) eat \(awaitedEat.map { "\($0)" } ?? "none")") }
        // No reply in time: the table said the engine takes this key, so it is eaten.
        let eat = awaitedEat ?? true
        // Only where it is needed: Chromium reports a document length of 0 (MACOS.md §6.4).
        if eat && !hadText && shown.isEmpty && !inserted, let field = field, field.length() == 0 {
            field.setMarkedText(waitingMark, selectionRange: NSRange(location: 1, length: 0),
                                replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
            shown = waitingMark
            placeholder = true
        }
        return eat
    }

    /// Sends the down to the engine if the engine takes this key now: its request number and vk.
    private func send(_ event: NSEvent, at real: UInt64?) -> (Int, UInt32)? {
        let engine = Engine.shared
        // Without the event tap there are no key ups to judge chords with: nothing is converted.
        guard !roman, KeyTap.shared.running, engine.state == .ready, let table = engine.table, let vk = Keys.vk[event.keyCode] else { return nil }
        let flags = event.modifierFlags
        guard table.sendsVk(vk, shift: flags.contains(.shift), ctrl: flags.contains(.control),
                            alt: flags.contains(.option), win: flags.contains(.command),
                            phase: phase, unsettled: !waiting.isEmpty) else { return nil }
        let seq = engine.nextSeq()
        var request: [String: Any] = ["sid": sid, "seq": seq, "op": "down", "vk": vk,
                                      "t": real ?? UInt64(event.timestamp * 1000), "mods": Keys.mods(flags)]
        if flags.contains(.capsLock) { request["caps_lock"] = true }
        guard engine.send(request) else { return nil }
        waiting.append(seq)
        if Log.debug {
            Log.write("down \(event.keyCode) seq \(seq) phase \(phase.rawValue) tap \(real != nil)"
                      + " late \(real.map { Int(nowMs()) - Int($0) } ?? -1)")
        }
        return (seq, vk)
    }

    func keyUp(code: UInt16, vk: UInt32, t: UInt64) {
        if Log.debug { Log.write("up \(code) t \(t)") }
        request("up", ["vk": vk, "mods": [String](), "t": t])
    }

    private func request(_ op: String, _ extra: [String: Any] = [:]) {
        let seq = Engine.shared.nextSeq()
        var message: [String: Any] = ["sid": sid, "seq": seq, "op": op, "t": nowMs()]
        message.merge(extra) { _, new in new }
        if Engine.shared.send(message) { waiting.append(seq) }
    }

    // -- the engine's answers --------------------------------------------------------------

    func reply(_ m: YRMessage) {
        let seq = Int(m.seq)
        waiting.removeAll { $0 <= seq }
        if Log.debug {
            Log.write("reply \(seq) eat \(m.hasEat ? "\(m.eat)" : "none") commit \(m.commit.count) shown \(m.composition.count)"
                      + " phase \(m.phase.rawValue) global \(m.global) again \(m.again)")
        }
        if m.hasEat {
            let eat = m.eat || m.eatPending
            if seq == awaited { awaitedEat = eat } else if !eat { Log.write("a late reply passed its key: lost") }
        }
        if seq < ignoreBefore || m.suggestionOnly { return }
        guard let field = field else { return }
        if m.error {
            commitShown(field)
            phase = .empty
            return
        }
        if !m.commit.isEmpty {
            field.insertText(m.commit, replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
            shown = ""
            placeholder = false
            inserted = true
        }
        // The waiting mark stays while the key that will replace it is being answered.
        let keep = placeholder && m.composition.isEmpty && awaited != nil
        if (!m.composition.isEmpty || !shown.isEmpty) && !keep { mark(m, field) }
        if m.hasPhase { phase = m.phase }
        if !m.global.isEmpty { Log.write("command \(m.global) not handled yet") }
        setTimer(m.hasTimer && !m.pending ? m.timer : nil)
    }

    func lmDone() { request("resolve") }

    func engineLost() {
        waiting.removeAll()
        setTimer(nil)
        phase = .empty
        if let field = field { commitShown(field) }
    }

    /// The text being converted: a thick underline under the focused clause, a thin one elsewhere.
    private func mark(_ m: YRMessage, _ field: IMKTextInput) {
        let text = m.composition
        let scalars = Array(text.unicodeScalars)
        func utf16(_ codePoints: Int) -> Int {
            scalars.prefix(max(0, codePoints)).reduce(0) { $0 + $1.utf16.count }
        }
        let length = (text as NSString).length
        let marked = NSMutableAttributedString(string: text)
        if length > 0 {
            marked.addAttributes([.underlineStyle: NSUnderlineStyle.single.rawValue, .markedClauseSegment: 0],
                                 range: NSRange(location: 0, length: length))
        }
        var caret = length
        for (index, value) in m.segments.enumerated() {
            let from = min(utf16(value.rangeValue.location), length)
            let to = min(utf16(value.rangeValue.location + value.rangeValue.length), length)
            guard to > from else { continue }
            let focused = index == m.focus
            marked.addAttributes([.underlineStyle: (focused ? NSUnderlineStyle.thick : .single).rawValue,
                                  .markedClauseSegment: index], range: NSRange(location: from, length: to - from))
            if focused && m.phase == .editing { caret = to }
        }
        if m.caret >= 0 { caret = min(utf16(m.caret), length) }
        field.setMarkedText(marked, selectionRange: NSRange(location: caret, length: 0),
                            replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
        shown = text
        placeholder = false
    }

    private func setTimer(_ at: UInt64?) {
        timer?.cancel()
        timer = nil
        guard let at = at else { return }
        let source = DispatchSource.makeTimerSource(queue: .main)
        let now = nowMs()
        source.schedule(deadline: .now() + .milliseconds(Int(at > now ? at - now : 0)))
        source.setEventHandler { [weak self] in
            guard let self = self else { return }
            self.timer = nil
            self.request("timeout", ["t": max(at, nowMs())])
        }
        timer = source
        source.resume()
    }

    // -- ending the input -------------------------------------------------------------------

    private func commitShown(_ field: IMKTextInput) {
        guard !shown.isEmpty else { return }
        if placeholder {
            field.setMarkedText("", selectionRange: NSRange(location: 0, length: 0),
                                replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
        } else {
            field.insertText(shown, replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
        }
        shown = ""
        placeholder = false
    }

    /// The OS ends the input (a click, another field, another input source): what is on screen is
    /// committed as it is, and the engine starts afresh.
    override func commitComposition(_ sender: Any!) {
        if Log.debug { Log.write("commitComposition shown \(shown.count) phase \(phase.rawValue)") }
        if let field = (sender as? IMKTextInput) ?? field { commitShown(field) }
        guard phase != .empty || !waiting.isEmpty else { return }
        setTimer(nil)
        phase = .empty
        request("reset")
        ignoreBefore = waiting.last ?? ignoreBefore
    }

    override func activateServer(_ sender: Any!) {
        Engine.shared.start()
        KeyTap.shared.start(ask: true)
        KeyTap.shared.listening = !roman
        super.activateServer(sender)
    }

    override func deactivateServer(_ sender: Any!) {
        KeyTap.shared.listening = false
        commitComposition(sender)
        super.deactivateServer(sender)
    }

    override func setValue(_ value: Any!, forTag tag: Int, client sender: Any!) {
        if tag == kTextServiceInputModePropertyTag, let mode = value as? String {
            let nowRoman = mode == "com.apple.inputmethod.Roman"
            if nowRoman && !roman { commitComposition(sender) }
            roman = nowRoman
            KeyTap.shared.listening = !roman
        }
        super.setValue(value, forTag: tag, client: sender)
    }

    override func recognizedEvents(_ sender: Any!) -> Int { Int(NSEvent.EventTypeMask.keyDown.rawValue) }
}
