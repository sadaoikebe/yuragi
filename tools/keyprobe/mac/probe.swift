// Prototype: a window whose view implements NSTextInputClient and logs everything the
// input method does (one JSON object per line on stdout), driven by synthetic key events.
//
//   probe <inject> <input-source-id> "<keys>" [shot-dir]
//
// inject   app  NSApp.sendEvent, in-process, no permission (the one to use)
//          ns   the view's keyDown directly; mode keys (Eisu/Kana, Ctrl+Shift+J) do not work
//          pid  CGEvent.postToPid(self); dropped without the Accessibility permission
//          hid  CGEvent.post to the system; needs Accessibility, sent only while frontmost (untested)
// keys     "kyouhaamedesu {Space} {Shift+Left}": {Name} / {Ctrl+Shift+Name} is one chord, other words
//          are typed letter by letter, {Wait} presses nothing. Modifiers: Shift Ctrl Opt Cmd. Names: KEY.
// shot-dir when given, each candidate window is captured to <shot-dir>/win-<key index>.png
//          (screencapture; needs the Screen Recording permission)
import Carbon
import Cocoa

func emit(_ d: [String: Any]) {
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
]
let ARROWS: Set<Int> = [123, 124, 125, 126]
let FUNCS: Set<Int> = [96, 97, 98, 99, 100, 101, 103, 109, 111, 115, 116, 117, 118, 119, 120, 121, 122]

class ProbeView: NSView, NSTextInputClient {
    var text = ""
    var marked = NSAttributedString()
    var markedSel = NSRange(location: 0, length: 0)

    override var acceptsFirstResponder: Bool { true }

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

    func insertText(_ s: Any, replacementRange: NSRange) {
        let (str, _) = describe(s)
        text += str
        marked = NSAttributedString()
        emit(["ev": "insertText", "s": str, "rep": [replacementRange.location == NSNotFound ? -1 : replacementRange.location, replacementRange.length]])
    }

    override func doCommand(by sel: Selector) {
        emit(["ev": "doCommand", "sel": NSStringFromSelector(sel)])
    }

    func setMarkedText(_ s: Any, selectedRange: NSRange, replacementRange: NSRange) {
        let (str, segs) = describe(s)
        marked = (s as? NSAttributedString) ?? NSAttributedString(string: str)
        markedSel = selectedRange
        emit(["ev": "setMarkedText", "s": str, "segs": segs, "sel": [selectedRange.location, selectedRange.length]])
    }

    func unmarkText() {
        text += marked.string
        marked = NSAttributedString()
        emit(["ev": "unmarkText"])
    }

    func selectedRange() -> NSRange {
        NSRange(location: (text as NSString).length + markedSel.location, length: markedSel.length)
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
            guard let c = KEY[name] else { fatalError("key \(name)") }
            out.append((String(word), c, f))
        } else {
            for ch in word { out.append((String(ch), KEY[String(ch)]!, [])) }
        }
    }
    return out
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
let inject = args[1], sourceID = args[2], keys = tokens(args[3])
let shotDir = args.count > 4 ? args[4] : nil

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let win = NSWindow(contentRect: NSRect(x: 200, y: 400, width: 700, height: 160), styleMask: [.titled], backing: .buffered, defer: false)
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
        switch inject {
        case "ns":
            if let n = NSEvent(cgEvent: ev) {
                if down { view.keyDown(with: n) } else { view.keyUp(with: n) }
            }
        case "app": if let n = NSEvent(cgEvent: ev) { NSApp.sendEvent(n) }
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
    if i == keys.count {
        emit(["ev": "end", "text": view.text, "marked": view.marked.string])
        exit(0)
    }
    let (name, code, flags) = keys[i]
    emit(["ev": "press", "key": name, "front": isFront()])
    if code >= 0 { send(code, flags) }
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
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
    view.inputContext?.selectedKeyboardInputSource = sourceID
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { step() }
}
app.run()
