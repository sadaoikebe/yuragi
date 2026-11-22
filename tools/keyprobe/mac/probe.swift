// A window whose view implements NSTextInputClient and logs everything the
// input method does (one JSON object per line on stdout), driven by synthetic key events.
//
//   probe <inject> <input-source-id> "<keys>" [shot-dir]
//   probe table <cases.json>          (one JSON line per case; see table.py)
//   probe guide <steps.json>          (a person presses the key shown in the window; see guide.py)
//
// inject   app  NSApp.sendEvent, in-process, no permission (the one to use)
//          ns   the view's keyDown directly; mode keys (Eisu/Kana, Ctrl+Shift+J) do not work
//          pid  CGEvent.postToPid(self); dropped without the Accessibility permission
//          hid  CGEvent.post to the system; needs Accessibility, sent only while frontmost (untested)
// keys     "kyouhaamedesu {Space} {Shift+Left}": {Name} / {Ctrl+Shift+Name} is one chord, other words
//          are typed letter by letter, {Wait} presses nothing. Modifiers: Shift Ctrl Opt Cmd. Names: KEY.
// shot-dir when given, every other visible window (candidate window, input source indicator) is captured to <shot-dir>/win-<key index>.png
//          (screencapture; needs the Screen Recording permission)
import Carbon
import Cocoa

var recording: [[String: Any]]? = nil
// guide mode (declared here: top-level code after app.run() never runs, so globals there stay uninitialized)
var realEvents: [[String: Any]] = []
var lastReal = Date.distantPast
var injecting = false

func emit(_ d: [String: Any]) {
    if recording != nil { recording!.append(d); return }
    let data = try! JSONSerialization.data(withJSONObject: d, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

let KEY: [String: Int] = [
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12, "w": 13,
    "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25,
    "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "Return": 36,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "Tab": 48, "Space": 49, "`": 50, "Delete": 51, "Esc": 53, "Clear": 71, "F5": 96, "F6": 97, "F7": 98,
    "F3": 99, "F8": 100, "F9": 101, "Eisu": 102, "F11": 103, "Kana": 104, "F10": 109, "F12": 111,
    "Home": 115, "PageUp": 116, "ForwardDelete": 117, "F4": 118, "End": 119, "F2": 120, "PageDown": 121,
    "F1": 122, "Left": 123, "Right": 124, "Down": 125, "Up": 126, "Yen": 93, "Underscore": 94,
    "ShiftKey": 56, "CapsLock": 57, "OptKey": 58, "CtrlKey": 59, "CmdKey": 55, "Fn": 63,
]
// a lone modifier: flagsChanged down (with its flag) and up (without)
let MODKEYS: [Int: CGEventFlags] = [56: .maskShift, 57: .maskAlphaShift, 58: .maskAlternate, 59: .maskControl, 55: .maskCommand, 63: .maskSecondaryFn]
let ARROWS: Set<Int> = [123, 124, 125, 126]
let FUNCS: Set<Int> = [96, 97, 98, 99, 100, 101, 103, 109, 111, 115, 116, 117, 118, 119, 120, 121, 122]

class ProbeView: NSView, NSTextInputClient {
    var text = ""
    var marked = NSAttributedString()
    var markedSel = NSRange(location: 0, length: 0)

    override var acceptsFirstResponder: Bool { true }
    var banner = ""

    override func flagsChanged(with e: NSEvent) {
        let h = inputContext?.handleEvent(e) ?? false
        emit(["ev": "flagsChanged", "code": Int(e.keyCode), "mods": e.modifierFlags.rawValue & 0xFFFF_0000, "handled": h])
    }

    override func keyDown(with e: NSEvent) {
        let h = inputContext?.handleEvent(e) ?? false
        emit(["ev": "keyDown", "code": Int(e.keyCode), "chars": e.characters ?? "", "mods": e.modifierFlags.rawValue & 0xFFFF_0000,
              "handled": h])
    }

    func describe(_ s: Any) -> (String, [[String: Any]]) {
        guard let a = s as? NSAttributedString else { return (s as? String ?? "", []) }
        var segs: [[String: Any]] = []
        a.enumerateAttributes(in: NSRange(location: 0, length: a.length)) { attrs, r, _ in
            var d: [String: Any] = ["at": r.location, "len": r.length, "s": (a.string as NSString).substring(with: r)]
            for (k, v) in attrs {
                if let n = v as? NSNumber { d[k.rawValue] = n } else { d[k.rawValue] = "\(type(of: v))" }
            }
            segs.append(d)
        }
        return (a.string, segs)
    }

    var selection: NSRange? = nil  // a selection in the committed text ({Sel:n}); the composition then replaces it

    // The composition sits at the end of the text. A replacement range (reconversion, undo of a commit)
    // is cut out of the text; the new string takes its place at the end (fine for the last word).
    func cut(_ r: NSRange) {
        guard r.location != NSNotFound, r.location + r.length <= (text as NSString).length else { return }
        text = (text as NSString).replacingCharacters(in: r, with: "")
    }

    func insertText(_ s: Any, replacementRange: NSRange) {
        let (str, _) = describe(s)
        cut(replacementRange)
        selection = nil
        text += str
        marked = NSAttributedString()
        emit(["ev": "insertText", "s": str, "rep": [replacementRange.location == NSNotFound ? -1 : replacementRange.location, replacementRange.length]])
    }

    override func doCommand(by sel: Selector) {
        emit(["ev": "doCommand", "sel": NSStringFromSelector(sel)])
    }

    func setMarkedText(_ s: Any, selectedRange: NSRange, replacementRange: NSRange) {
        let (str, segs) = describe(s)
        cut(replacementRange)
        selection = nil
        marked = (s as? NSAttributedString) ?? NSAttributedString(string: str)
        markedSel = selectedRange
        emit(["ev": "setMarkedText", "s": str, "segs": segs, "sel": [selectedRange.location, selectedRange.length],
              "rep": [replacementRange.location == NSNotFound ? -1 : replacementRange.location, replacementRange.length]])
    }

    func unmarkText() {
        text += marked.string
        marked = NSAttributedString()
        emit(["ev": "unmarkText"])
    }

    func selectedRange() -> NSRange {
        if marked.length == 0, let r = selection { return r }
        return NSRange(location: (text as NSString).length + markedSel.location, length: markedSel.length)
    }

    func markedRange() -> NSRange {
        marked.length == 0 ? NSRange(location: NSNotFound, length: 0) : NSRange(location: (text as NSString).length, length: marked.length)
    }

    func hasMarkedText() -> Bool { marked.length > 0 }

    func attributedSubstring(forProposedRange r: NSRange, actualRange: NSRangePointer?) -> NSAttributedString? {
        let all = (text + marked.string) as NSString
        guard r.location != NSNotFound, r.location + r.length <= all.length else { return nil }
        return NSAttributedString(string: all.substring(with: r))
    }

    func validAttributesForMarkedText() -> [NSAttributedString.Key] {
        [.underlineStyle, .underlineColor, .markedClauseSegment, .backgroundColor, .foregroundColor,
         NSAttributedString.Key("NSTextInputReplacementRangeAttributeName"), .glyphInfo, .font, .languageIdentifier]
    }

    func firstRect(forCharacterRange r: NSRange, actualRange: NSRangePointer?) -> NSRect {
        window!.convertToScreen(convert(NSRect(x: 20, y: 60, width: 10, height: 20), to: nil))
    }

    func characterIndex(for p: NSPoint) -> Int { 0 }

    override func draw(_ r: NSRect) {
        NSColor.textBackgroundColor.setFill()
        r.fill()
        let s = NSMutableAttributedString(string: text, attributes: [.font: NSFont.systemFont(ofSize: 20), .foregroundColor: NSColor.textColor])
        let m = NSMutableAttributedString(attributedString: marked)
        m.addAttributes([.font: NSFont.systemFont(ofSize: 20), .foregroundColor: NSColor.textColor], range: NSRange(location: 0, length: m.length))
        s.append(m)
        s.draw(at: NSPoint(x: 20, y: 60))
        if !banner.isEmpty {
            NSAttributedString(string: banner, attributes: [.font: NSFont.boldSystemFont(ofSize: 18), .foregroundColor: NSColor.systemRed])
                .draw(in: NSRect(x: 20, y: 100, width: bounds.width - 40, height: bounds.height - 105))
        }
    }
}

func tokens(_ s: String) -> [(String, Int, CGEventFlags)] {
    var out: [(String, Int, CGEventFlags)] = []
    for word in s.split(separator: " ") {
        if word.hasPrefix("{"), word.hasSuffix("}") {
            var parts = word.dropFirst().dropLast().split(separator: "+").map(String.init)
            let name = parts.removeLast()
            var f: CGEventFlags = []
            for p in parts {
                switch p {
                case "Shift": f.insert(.maskShift)
                case "Ctrl": f.insert(.maskControl)
                case "Opt": f.insert(.maskAlternate)
                case "Cmd": f.insert(.maskCommand)
                default: fatalError("modifier \(p)")
                }
            }
            if name == "Wait" { out.append((String(word), -1, f)); continue }
            if name.hasPrefix("Sel:") { out.append((String(word), -100 - Int(name.dropFirst(4))!, f)); continue }
            guard let c = KEY[name] else { fatalError("key \(name)") }
            out.append((String(word), c, f))
        } else {
            for ch in word { out.append((String(ch), KEY[String(ch)]!, [])) }
        }
    }
    return out
}

func select(_ n: Int) {
    let len = (view.text as NSString).length
    view.selection = NSRange(location: len - min(n, len), length: min(n, len))
    emit(["ev": "select", "range": [view.selection!.location, view.selection!.length]])
}

func imWindows() -> [[String: Any]] {
    let me = getpid()
    let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as! [[String: Any]]
    var out: [[String: Any]] = []
    for w in list {
        let layer = w[kCGWindowLayer as String] as? Int ?? 0
        let pid = w[kCGWindowOwnerPID as String] as? Int32 ?? 0
        let owner = w[kCGWindowOwnerName as String] as? String ?? ""
        if pid == me || layer == 0 { continue }
        if ["Window Server", "Dock", "Control Center", "コントロールセンター", "SystemUIServer", "Spotlight", "WindowManager"].contains(owner) { continue }
        let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
        out.append(["owner": owner, "layer": layer, "id": w[kCGWindowNumber as String] as? Int ?? 0,
                    "w": b["Width"] ?? 0, "h": b["Height"] ?? 0, "x": b["X"] ?? 0, "y": b["Y"] ?? 0])
    }
    return out
}

// Windows of this process other than the probe window: the candidate window is one of them
// (its content is drawn by another process, so only a screenshot shows it).
func dumpView(_ v: NSView, _ depth: Int, _ out: inout [String]) {
    var line = String(repeating: " ", count: depth) + "\(type(of: v)) \(Int(v.frame.width))x\(Int(v.frame.height))"
    if let t = v as? NSTextField { line += " text=\(t.stringValue)" }
    if let l = v.layer { line += " layer=\(type(of: l)) sub=\(l.sublayers?.count ?? 0)" }
    out.append(line)
    if depth < 12 { for s in v.subviews { dumpView(s, depth + 1, &out) } }
}

func otherWindows() -> [[String: Any]] {
    var res: [[String: Any]] = []
    for w in NSApp.windows where w !== win && w.isVisible {
        var views: [String] = []
        if let c = w.contentView { dumpView(c, 0, &views) }
        var d: [String: Any] = ["class": "\(type(of: w))", "num": w.windowNumber, "frame": "\(w.frame)", "views": views]
        if let dir = shotDir {
            let pr = Process()
            pr.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
            pr.arguments = ["-x", "-o", "-l", "\(w.windowNumber)", "\(dir)/win-\(i).png"]
            try? pr.run(); pr.waitUntilExit()
            d["shot"] = Int(pr.terminationStatus)
        }
        res.append(d)
    }
    return res
}

let args = CommandLine.arguments
let tableMode = args[1] == "table" || args[1] == "guide"
let inject = tableMode ? "app" : args[1]
let sourceID = tableMode ? "" : args[2]
let keys = tableMode ? [] : tokens(args[3])
let shotDir = tableMode ? nil : (args.count > 4 ? args[4] : nil)

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let win = NSWindow(contentRect: NSRect(x: 200, y: 400, width: 700, height: args[1] == "guide" ? 260 : 160), styleMask: [.titled], backing: .buffered, defer: false)
win.title = "mac-keyprobe"
let view = ProbeView(frame: win.contentView!.bounds)
win.contentView = view
win.makeKeyAndOrderFront(nil)
win.makeFirstResponder(view)
app.activate(ignoringOtherApps: true)

NotificationCenter.default.addObserver(forName: NSTextInputContext.keyboardSelectionDidChangeNotification, object: nil, queue: nil) { _ in
    emit(["ev": "source", "id": view.inputContext?.selectedKeyboardInputSource ?? ""])
}

func isFront() -> Bool { NSWorkspace.shared.frontmostApplication?.processIdentifier == getpid() }

func send(_ code: Int, _ flags: CGEventFlags) {
    let src = CGEventSource(stateID: .hidSystemState)
    for down in [true, false] {
        let ev = CGEvent(keyboardEventSource: src, virtualKey: CGKeyCode(code), keyDown: down)!
        var f = flags
        if ARROWS.contains(code) { f.insert(.maskNumericPad); f.insert(.maskSecondaryFn) }
        if FUNCS.contains(code) { f.insert(.maskSecondaryFn) }
        ev.flags = f
        if let m = MODKEYS[code] {
            ev.type = .flagsChanged
            ev.flags = down || code == 57 ? f.union(m) : f
        }
        if let t = ProcessInfo.processInfo.environment["PROBE_KBTYPE"], let n = Int64(t) {
            ev.setIntegerValueField(.keyboardEventKeyboardType, value: n)
        }
        switch inject {
        case "ns":
            if let n = NSEvent(cgEvent: ev) {
                if down { view.keyDown(with: n) } else { view.keyUp(with: n) }
            }
        case "app": if let n = NSEvent(cgEvent: ev) { injecting = true; NSApp.sendEvent(n); injecting = false }
        case "pid": ev.postToPid(getpid())
        case "hid":
            guard isFront() else { emit(["ev": "abort", "why": "not frontmost"]); exit(2) }
            ev.post(tap: .cghidEventTap)
        default: fatalError("inject")
        }
    }
}

var i = 0
func step() {
    if tableMode { if args[1] == "guide" { runGuide(args[2]) } else { runTable(args[2]) }; exit(0) }
    if i == keys.count {
        emit(["ev": "end", "text": view.text, "marked": view.marked.string])
        exit(0)
    }
    let (name, code, flags) = keys[i]
    emit(["ev": "press", "key": name, "front": isFront()])
    if code >= 0 { send(code, flags) } else if code <= -100 { select(-100 - code) }
    DispatchQueue.main.asyncAfter(deadline: .now() + (Double(ProcessInfo.processInfo.environment["PROBE_GAP"] ?? "") ?? 0.45)) {
        view.needsDisplay = true
        emit(["ev": "after", "key": name, "text": view.text, "marked": view.marked.string,
              "sel": [view.markedSel.location, view.markedSel.length], "windows": imWindows(), "own": otherWindows(),
              "source": view.inputContext?.selectedKeyboardInputSource ?? ""])
        i += 1
        step()
    }
}

DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
    emit(["ev": "start", "front": isFront(), "active": app.isActive, "key": win.isKeyWindow,
          "ax": AXIsProcessTrusted(), "post": CGPreflightPostEventAccess(), "screen": CGPreflightScreenCaptureAccess(),
          "sources": view.inputContext?.keyboardInputSources ?? [], "before": view.inputContext?.selectedKeyboardInputSource ?? ""])
    if !tableMode { view.inputContext?.selectedKeyboardInputSource = sourceID }
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { step() }
}
app.run()

// ---- table mode: many cases in one process --------------------------------------------------
// cases.json: [{"id": ..., "source": "<input-source-id>", "prep": "<keys>", "key": "<keys>"}, ...]
// Per case: discard any composition, empty the text, select the source, type prep, record the
// state (before), press key, record what the input method did (events) and the state (after),
// press Esc x3 and record the text that is left (kept = what was committed).

// Wait, and meanwhile hand the keyboard's events to the app (a bare RunLoop.run would leave them
// queued: real keys would never reach the window or the event monitor).
func pause(_ t: Double) {
    let end = Date().addingTimeInterval(t)
    while Date() < end {
        if let e = NSApp.nextEvent(matching: .any, until: end, inMode: .default, dequeue: true) { NSApp.sendEvent(e) }
    }
}

func press(_ s: String, letter: Double = 0.07, chord: Double = 0.3) {
    for (name, code, flags) in tokens(s) {
        if code >= 0 { send(code, flags) } else if code <= -100 { select(-100 - code) }
        pause(name.hasPrefix("{") ? chord : letter)
    }
}

func segs() -> [[Any]] {
    var out: [[Any]] = []
    let a = view.marked
    a.enumerateAttributes(in: NSRange(location: 0, length: a.length)) { attrs, r, _ in
        out.append([(a.string as NSString).substring(with: r), (attrs[.underlineStyle] as? NSNumber)?.intValue ?? 0])
    }
    return out
}

func snap() -> [String: Any] {
    ["text": view.text, "segs": segs(), "sel": [view.markedSel.location, view.markedSel.length],
     "source": (view.inputContext?.selectedKeyboardInputSource ?? "").split(separator: ".").last.map(String.init) ?? "",
     "panels": NSApp.windows.filter { $0 !== win && $0.isVisible }.map { "\(Int($0.frame.width))x\(Int($0.frame.height))" },
     "front": isFront(), "frontApp": NSWorkspace.shared.frontmostApplication?.localizedName ?? ""]
}

func compact(_ evs: [[String: Any]]) -> [String] {
    evs.compactMap { e -> String? in
        switch e["ev"] as? String ?? "" {
        case "setMarkedText": return "mark"
        case "insertText": return "ins:\(e["s"] ?? "")"
        case "doCommand": return "cmd:\(e["sel"] ?? "")"
        case "unmarkText": return "unmark"
        case "source": return "src:\((e["id"] as? String ?? "").split(separator: ".").last ?? "")"
        case "keyDown": return (e["handled"] as? Bool ?? false) ? nil : "unhandled"
        default: return nil
        }
    }
}

func reset(_ source: String) {
    if view.marked.length > 0 { view.inputContext?.discardMarkedText(); pause(0.15) }
    view.marked = NSAttributedString()
    view.markedSel = NSRange(location: 0, length: 0)
    view.text = ""
    if !isFront() { app.activate(ignoringOtherApps: true); win.makeKeyAndOrderFront(nil); pause(1.0) }
    if view.inputContext?.selectedKeyboardInputSource != source {
        view.inputContext?.selectedKeyboardInputSource = source
        pause(0.4)
    }
}

func runTable(_ path: String) {
    let cases = try! JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: path))) as! [[String: Any]]
    for c in cases {
        let source = c["source"] as! String
        recording = []
        reset(source)
        pause(0.15)
        press(c["prep"] as? String ?? "")
        pause(0.35)
        let before = snap()
        recording = []
        press(c["key"] as! String, letter: 0.45, chord: 0.45)
        let evs = recording!
        recording = []
        let after = snap()
        press("{Esc} {Esc} {Esc}", chord: 0.12)
        pause(0.2)
        recording = nil
        var r = c
        r["before"] = before
        r["after"] = after
        r["events"] = compact(evs)
        r["kept"] = view.text + view.marked.string
        emit(r)
    }
    recording = []
    reset(cases.first?["source"] as? String ?? "")
}

// ---- guide mode: a person presses the keys ------------------------------------------------
// steps.json: [{"id": ..., "source": ..., "prep": "<keys>", "say": "<what to press>"}, ...]
// Per step: set the state up (synthetic keys), show `say` in the window, and record everything
// until 0.3 s after the key is released (1 s after the last real key event otherwise) (8 s for the first step and 4 s afterwards with none). If the first step gets no real key, stop. Real events come from a local event
// monitor; it also sees the synthetic events given to NSApp.sendEvent, so those are skipped (injecting).


func runGuide(_ path: String) {
    let steps = try! JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: path))) as! [[String: Any]]
    NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .keyUp, .flagsChanged]) { e in
        if injecting { return e }
        realEvents.append(["t": Date().timeIntervalSince1970, "type": e.type == .keyDown ? "down" : e.type == .keyUp ? "up" : "flags",
                           "code": Int(e.keyCode), "mods": e.modifierFlags.rawValue & 0xFFFF_0000,
                           "chars": e.type == .flagsChanged ? "" : (e.charactersIgnoringModifiers ?? ""),
                           "repeat": e.type == .flagsChanged ? false : e.isARepeat])
        lastReal = Date()
        return e
    }
    for (n, c) in steps.enumerated() {
        recording = []
        reset(c["source"] as! String)
        pause(0.2)
        press(c["prep"] as? String ?? "")
        pause(0.4)
        let before = snap()
        view.banner = "[\(n + 1)/\(steps.count)] \(c["say"] as? String ?? "")"
        view.needsDisplay = true
        NSSound.beep()
        recording = []
        realEvents = []
        let start = Date()
        lastReal = .distantPast
        while true {
            pause(0.1)
            if realEvents.isEmpty && !(recording!.contains { ($0["ev"] as? String) == "source" }) {
                if Date().timeIntervalSince(start) > (n == 0 ? 8 : 4) { break }
                continue
            }
            let last = max(lastReal, start)
            // done 0.3 s after every key is up again (a hold ends with its up), or 1 s after the last event
            let released = (realEvents.last?["type"] as? String == "up") ||
                (realEvents.last?["type"] as? String == "flags" && (realEvents.last?["mods"] as? UInt ?? 1) & 0x00FF_0000 == 0)
            if Date().timeIntervalSince(last) > (released ? 0.3 : 1.0) { break }
        }
        let evs = recording!
        recording = []
        let after = snap()
        let real = realEvents
        view.banner = "（記録中。キーに触らないでください）"
        view.needsDisplay = true
        press("{Esc} {Esc} {Esc}", chord: 0.12)
        pause(0.2)
        recording = nil
        var r = c
        r["before"] = before
        r["after"] = after
        r["events"] = compact(evs)
        r["raw"] = evs
        r["real"] = real
        r["kept"] = view.text + view.marked.string
        emit(r)
        if n == 0 && real.isEmpty {
            view.banner = "キーが届きませんでした。中断します"
            view.needsDisplay = true
            pause(1.5)
            return
        }
    }
    view.banner = "終わりました"
    view.needsDisplay = true
    pause(1.0)
}
