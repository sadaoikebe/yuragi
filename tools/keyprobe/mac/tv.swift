// The same synthetic keys as probe.swift, given to a real NSTextView (what ordinary Cocoa apps such as
// TextEdit use) instead of probe's minimal NSTextInputClient view. After each key, one JSON line with
// the text, the composition (clauses with their underline: 2 = focused), the selection and the source.
//
//   tv <input-source-id> "<keys>"        keys as in probe.swift; {Sel:n} selects the last n characters
//   PROBE_GAP=<seconds>                  wait after each key (default 0.45)
//   The app has a main menu: Edit (Undo, Cut, Copy, Paste, Select All, standard actions) and File › Save
//   (only records that it ran), so Command shortcuts behave as in an ordinary app. Each line has "menu":
//   the menu items that ran for that key, and "pb": the pasteboard text.
//   PROBE_SHOT=<dir>                     capture every other visible window to <dir>/tv-<key index>-<n>.png
import Carbon
import Cocoa

let KEY: [String: Int] = [
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12, "w": 13,
    "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25,
    "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "Return": 36,
    "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "Tab": 48, "Space": 49, "`": 50, "Delete": 51, "Esc": 53, "F6": 97, "F7": 98, "F8": 100, "F9": 101,
    "Eisu": 102, "Kana": 104, "F10": 109, "Home": 115, "PageUp": 116, "ForwardDelete": 117, "End": 119,
    "PageDown": 121, "Left": 123, "Right": 124, "Down": 125, "Up": 126,
]
let ARROWS: Set<Int> = [123, 124, 125, 126]
let FUNCS: Set<Int> = [97, 98, 100, 101, 109, 115, 116, 117, 119, 121]

func emit(_ d: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: d, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
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

let args = CommandLine.arguments
let sourceID = args[1], keys = tokens(args[2])
let gap = Double(ProcessInfo.processInfo.environment["PROBE_GAP"] ?? "") ?? 0.45

// Keep the user's clipboard: Command+C / X in the tests overwrite it.
let savedClipboard: [[NSPasteboard.PasteboardType: Data]] = (NSPasteboard.general.pasteboardItems ?? []).map { item in
    var d: [NSPasteboard.PasteboardType: Data] = [:]
    for t in item.types { if let v = item.data(forType: t) { d[t] = v } }
    return d
}
func restoreClipboard() {
    let pb = NSPasteboard.general
    pb.clearContents()
    pb.writeObjects(savedClipboard.map { d -> NSPasteboardItem in
        let it = NSPasteboardItem()
        for (t, v) in d { it.setData(v, forType: t) }
        return it
    })
}

// Characters of the real events for keys whose synthetic events carry legacy control codes instead
// (used with Command, where key bindings look the characters up).
let FUNCCHARS: [Int: Int] = [123: 0xF702, 124: 0xF703, 126: 0xF700, 125: 0xF701, 115: 0xF729, 119: 0xF72B,
                             116: 0xF72C, 121: 0xF72D, 117: 0xF728, 51: 0x7F]

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let win = NSWindow(contentRect: NSRect(x: 200, y: 400, width: 700, height: 160), styleMask: [.titled], backing: .buffered, defer: false)
win.title = "mac-keyprobe-textview"
let tv = NSTextView(frame: win.contentView!.bounds)
tv.isRichText = false
tv.font = NSFont.systemFont(ofSize: 20)
tv.allowsUndo = true
win.contentView = tv

var menuHits: [String] = []
class Recorder: NSObject {
    @objc func save(_ sender: Any?) { menuHits.append("save") }
}
let recorder = Recorder()
// Record which standard Edit item ran, without changing what it does.
class Watch: NSObject, NSMenuDelegate {}
func item(_ title: String, _ action: Selector, _ key: String, target: AnyObject? = nil) -> NSMenuItem {
    let it = NSMenuItem(title: title, action: action, keyEquivalent: key)
    it.target = target
    return it
}
let mainMenu = NSMenu()
let appItem = NSMenuItem(); mainMenu.addItem(appItem)
let appMenu = NSMenu(); appItem.submenu = appMenu
let fileItem = NSMenuItem(); mainMenu.addItem(fileItem)
let fileMenu = NSMenu(title: "File"); fileItem.submenu = fileMenu
fileMenu.addItem(item("Save", #selector(Recorder.save(_:)), "s", target: recorder))
let editItem = NSMenuItem(); mainMenu.addItem(editItem)
let editMenu = NSMenu(title: "Edit"); editItem.submenu = editMenu
editMenu.addItem(item("Undo", Selector(("undo:")), "z"))
editMenu.addItem(item("Cut", #selector(NSText.cut(_:)), "x"))
editMenu.addItem(item("Copy", #selector(NSText.copy(_:)), "c"))
editMenu.addItem(item("Paste", #selector(NSText.paste(_:)), "v"))
editMenu.addItem(item("Select All", #selector(NSText.selectAll(_:)), "a"))
app.mainMenu = mainMenu
NotificationCenter.default.addObserver(forName: NSMenu.didSendActionNotification, object: nil, queue: nil) { n in
    if let it = n.userInfo?["MenuItem"] as? NSMenuItem { menuHits.append(it.title) }
}
win.makeKeyAndOrderFront(nil)
win.makeFirstResponder(tv)
app.activate(ignoringOtherApps: true)

func send(_ code: Int, _ flags: CGEventFlags) {
    let src = CGEventSource(stateID: .hidSystemState)
    for down in [true, false] {
        let ev = CGEvent(keyboardEventSource: src, virtualKey: CGKeyCode(code), keyDown: down)!
        var f = flags
        if ARROWS.contains(code) { f.insert(.maskNumericPad); f.insert(.maskSecondaryFn) }
        if FUNCS.contains(code) { f.insert(.maskSecondaryFn) }
        ev.flags = f
        if flags.contains(.maskCommand), let u = FUNCCHARS[code], let base = NSEvent(cgEvent: ev) {
            let ch = String(UnicodeScalar(u)!)
            if let n = NSEvent.keyEvent(with: down ? .keyDown : .keyUp, location: .zero, modifierFlags: base.modifierFlags,
                                        timestamp: base.timestamp, windowNumber: win.windowNumber, context: nil,
                                        characters: ch, charactersIgnoringModifiers: ch, isARepeat: false, keyCode: UInt16(code)) {
                NSApp.sendEvent(n)
            }
            continue
        }
        if let n = NSEvent(cgEvent: ev) { NSApp.sendEvent(n) }
    }
}

func state() -> [String: Any] {
    let s = tv.string as NSString
    var segs: [[Any]] = []
    let mr = tv.markedRange()
    if tv.hasMarkedText(), mr.location != NSNotFound, let ts = tv.textStorage {
        ts.enumerateAttribute(.underlineStyle, in: mr) { v, r, _ in
            segs.append([s.substring(with: r), (v as? NSNumber)?.intValue ?? 0])
        }
    }
    let sel = tv.selectedRange()
    return ["text": tv.string, "segs": segs, "sel": [sel.location, sel.length],
            "source": (tv.inputContext?.selectedKeyboardInputSource ?? "").split(separator: ".").last.map(String.init) ?? "",
            "menu": menuHits, "pb": NSPasteboard.general.string(forType: .string) ?? "",
            "panels": NSApp.windows.filter { $0 !== win && $0.isVisible }.count,
            "front": NSWorkspace.shared.frontmostApplication?.processIdentifier == getpid()]
}

var i = 0
func step() {
    if i == keys.count {
        tv.inputContext?.discardMarkedText()
        restoreClipboard()
        exit(0)
    }
    let (name, code, flags) = keys[i]
    menuHits = []
    if code >= 0 { send(code, flags) }
    if code <= -100 {
        let n = -100 - code, len = (tv.string as NSString).length
        tv.setSelectedRange(NSRange(location: len - min(n, len), length: min(n, len)))
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + gap) {
        var d = state()
        d["key"] = name
        if let dir = ProcessInfo.processInfo.environment["PROBE_SHOT"] {
            for (n, w) in NSApp.windows.filter({ $0 !== win && $0.isVisible }).enumerated() {
                let pr = Process()
                pr.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
                pr.arguments = ["-x", "-o", "-l", "\(w.windowNumber)", "\(dir)/tv-\(i)-\(n).png"]
                try? pr.run(); pr.waitUntilExit()
            }
        }
        emit(d)
        i += 1
        step()
    }
}

DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
    tv.inputContext?.selectedKeyboardInputSource = sourceID
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { step() }
}
app.run()
