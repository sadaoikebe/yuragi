// One input field's side of the input program (MACOS.md §4.2): takes the keys, asks the engine,
// draws the text being converted, commits.
import Carbon
import Cocoa
import InputMethodKit

/// DESIGN「定数」 CONTEXT_CHARS: the code points of left context an input start carries.
let contextChars = 200
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
    private var suggestTimer: DispatchSourceTimer?
    private var lastSent = 0  // the newest request: a suggestion answered after it is stale
    private var focusStart = 0  // UTF-16 offset of the focused clause in the marked text
    private var noticed = false  // the notice was shown since this field became active
    private var lastCommit: (seq: Int, text: String)?  // for the engine to tell that the input goes on from it

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
            notice(event)
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
        var request: [String: Any] = ["seq": seq, "op": "down", "vk": vk,
                                      "t": real ?? UInt64(event.timestamp * 1000), "mods": Keys.mods(flags)]
        if flags.contains(.capsLock) { request["caps_lock"] = true }
        if phase == .empty { addContext(&request) }
        waiting.append(seq)
        lastSent = seq
        engine.send(sid, request)
        if Log.debug {
            Log.write("down \(event.keyCode) seq \(seq) phase \(phase.rawValue) tap \(real != nil)"
                      + " late \(real.map { Int(nowMs()) - Int($0) } ?? -1)")
        }
        return (seq, vk)
    }

    /// DESIGN「通信」: the text left of the caret when an input starts, and the commit it follows.
    private func addContext(_ request: inout [String: Any]) {
        // Terminal answers with the text on its screen, prompt included (MACOS.md §6.4).
        guard let field = field, field.bundleIdentifier() != "com.apple.Terminal" else { return }
        let caret = field.selectedRange().location
        var left: String?
        if caret != NSNotFound {
            let units = min(caret, 2 * contextChars)
            let text = units == 0 ? "" : field.attributedSubstring(from: NSRange(location: caret - units, length: units))?.string
            left = text.map { String(String.UnicodeScalarView($0.unicodeScalars.suffix(contextChars))) }
        }
        request["left_context"] = left ?? NSNull()
        if Log.debug { Log.write("context \(left.map { "\($0.count)" } ?? "none") follows \(lastCommit.map { left == nil || left!.hasSuffix($0.text) } ?? false)") }
        if let last = lastCommit {
            // null: the caret is not where that commit ended.
            request["after_commit_seq"] = (left == nil || left!.hasSuffix(last.text)) ? last.seq : NSNull()
        }
    }

    /// DESIGN「小さな表示」: a character key typed for kana while nothing converts, once per field.
    private func notice(_ event: NSEvent) {
        guard !roman, !noticed, let problem = Engine.shared.problem, let field = field,
              event.modifierFlags.intersection([.command, .control, .option]).isEmpty,
              let vk = Keys.vk[event.keyCode], vk >= 0x30 else { return }
        noticed = true
        var caret = NSRect.zero
        field.attributes(forCharacterIndex: 0, lineHeightRectangle: &caret)
        CandidateWindow.shared.notice(problem, at: caret)
    }

    func keyUp(code: UInt16, vk: UInt32, t: UInt64) {
        if Log.debug { Log.write("up \(code) t \(t)") }
        request("up", ["vk": vk, "mods": [String](), "t": t])
    }

    private func request(_ op: String, _ extra: [String: Any] = [:]) {
        let seq = Engine.shared.nextSeq()
        var message: [String: Any] = ["seq": seq, "op": op, "t": nowMs()]
        message.merge(extra) { _, new in new }
        waiting.append(seq)
        lastSent = seq
        Engine.shared.send(sid, message)
    }

    // -- the engine's answers --------------------------------------------------------------

    func receive(_ m: YRMessage) {
        if m.event == "lm_done" { request("resolve") }
        // DESIGN「見えている文字の確定」: the engine ended, and every conversion with it.
        if m.event == "reset" || m.state == "down" { engineLost() }
        if m.event == "state" { noticed = false }
        guard m.hasSeq else { return }
        let seq = Int(m.seq)
        waiting.removeAll { $0 <= seq }
        // The engine did not get this request (it is starting or down): its key stays eaten.
        if !m.state.isEmpty { return }
        if Log.debug {
            Log.write("reply \(seq) eat \(m.hasEat ? "\(m.eat)" : "none") commit \(m.commit.count) shown \(m.composition.count)"
                      + " phase \(m.phase.rawValue) global \(m.global) again \(m.again)")
        }
        if m.hasEat {
            let eat = m.eat || m.eatPending
            if seq == awaited { awaitedEat = eat } else if !eat { Log.write("a late reply passed its key: lost") }
        }
        if seq < ignoreBefore { return }
        guard let field = field else { return }
        if m.suggestionOnly {
            // Only the window and the next deadline; nothing if a key went out since.
            if seq == lastSent {
                showCandidates(m, field)
                setSuggestTimer(m.hasSuggestAt ? m.suggestAt : nil)
            }
            return
        }
        if m.error {
            commitShown(field)
            phase = .empty
            CandidateWindow.shared.hide()
            return
        }
        if !m.commit.isEmpty {
            field.insertText(m.commit, replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
            shown = ""
            placeholder = false
            inserted = true
            lastCommit = (seq, m.commit)
        }
        // The waiting mark stays while the key that will replace it is being answered.
        let keep = placeholder && m.composition.isEmpty && awaited != nil
        if (!m.composition.isEmpty || !shown.isEmpty) && !keep { mark(m, field) }
        if m.hasPhase { phase = m.phase }
        showCandidates(m, field)
        setSuggestTimer(m.hasSuggestAt ? m.suggestAt : nil)
        if !m.global.isEmpty { run(m.global, field) }
        setTimer(m.hasTimer && !m.pending ? m.timer : nil)
    }

    private func showCandidates(_ m: YRMessage, _ field: IMKTextInput) {
        guard m.showsCandidates else { CandidateWindow.shared.hide(); return }
        var caret = NSRect.zero
        field.attributes(forCharacterIndex: m.suggesting ? 0 : focusStart, lineHeightRectangle: &caret)
        if Log.debug { Log.write("candidates \(m.candidates.count) selected \(m.candIndex) suggesting \(m.suggesting) at \(Int(caret.minX)),\(Int(caret.minY)) h \(Int(caret.height))") }
        CandidateWindow.shared.show(
            CandidateList(items: m.candidates, notes: m.candidateNotes, selected: m.candIndex, page: m.page,
                          hasNextPage: m.hasNextPage, suggesting: m.suggesting), at: caret)
    }

    /// A command the engine leaves to the input program (KEYBIND §7.5).
    private func run(_ command: String, _ field: IMKTextInput) {
        switch command {
        case "ime_off", "ime_toggle":
            field.selectMode("com.apple.inputmethod.Roman")  // the kana mode off is the Roman mode (MACOS.md §4.3)
        case "mode_hiragana": request("set_mode", ["mode": "hiragana"])
        case "mode_katakana": request("set_mode", ["mode": "katakana"])
        case "mode_full_alnum": request("set_mode", ["mode": "full_alnum"])
        case "open_settings", "open_word_register": Engine.shared.openSettings()
        default: Log.write("command \(command) not handled yet")
        }
    }

    private func engineLost() {
        waiting.removeAll()
        setTimer(nil)
        setSuggestTimer(nil)
        CandidateWindow.shared.hide()
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
        focusStart = 0
        for (index, value) in m.segments.enumerated() {
            let from = min(utf16(value.rangeValue.location), length)
            let to = min(utf16(value.rangeValue.location + value.rangeValue.length), length)
            guard to > from else { continue }
            let focused = index == m.focus
            marked.addAttributes([.underlineStyle: (focused ? NSUnderlineStyle.thick : .single).rawValue,
                                  .markedClauseSegment: index], range: NSRange(location: from, length: to - from))
            if focused {
                focusStart = from
                if m.phase == .editing { caret = to }
            }
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

    /// DESIGN「タイマー」: predictions are asked for at the engine's deadline, unless a key is being answered.
    private func setSuggestTimer(_ at: UInt64?) {
        suggestTimer?.cancel()
        suggestTimer = nil
        guard let at = at else { return }
        let source = DispatchSource.makeTimerSource(queue: .main)
        let now = nowMs()
        source.schedule(deadline: .now() + .milliseconds(Int(at > now ? at - now : 0)))
        source.setEventHandler { [weak self] in
            guard let self = self else { return }
            self.suggestTimer = nil
            if self.waiting.isEmpty { self.request("suggest") }
        }
        suggestTimer = source
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
        CandidateWindow.shared.hide()
        setSuggestTimer(nil)
        guard phase != .empty || !waiting.isEmpty else { return }
        setTimer(nil)
        phase = .empty
        request("reset")
        ignoreBefore = waiting.last ?? ignoreBefore
    }

    // -- the input menu (DESIGN「メニュー」) ----------------------------------------------------

    override func menu() -> NSMenu! {
        let menu = NSMenu()
        func add(_ title: String, _ action: Selector?) {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
            item.target = self
            menu.addItem(item)
        }
        if !KeyTap.shared.running {
            add("「入力監視」の許可が要ります", nil)
            add("許可の設定を開く", #selector(openPermission(_:)))
        } else if Engine.shared.state == .down {
            add("もう一度試す", #selector(retry(_:)))
        } else if Engine.shared.state == .starting {
            add("（変換の準備をしています）", nil)
        }
        // A menu without items makes the OS end the input after every change of the marked text.
        add("設定を開く", #selector(openSettings(_:)))
        return menu
    }

    @objc func openPermission(_ sender: Any?) {
        KeyTap.shared.start(ask: true)
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc func openSettings(_ sender: Any?) { Engine.shared.openSettings() }

    @objc func retry(_ sender: Any?) { Engine.shared.retry() }

    override func activateServer(_ sender: Any!) {
        noticed = false
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
