// A logging-only input method (InputMethodKit) for the checks in docs/MACOS.md §9.
// It writes one JSON object per line to ~/Library/Logs/yuragi-probe/imk.jsonl.
//
// Files in ~/Library/Logs/yuragi-probe/ switch what it does (read when a client activates it):
//   (none)        log every event handle() gets and pass it on (return false)
//   mark          letters go to marked text, Return commits, Esc clears; logs what the client answers
//   eat-modes     Eisu / Kana are eaten (return true) instead of passed on
//   chars         also log the characters of each key (off by default: the log would hold what was typed)
//   request-tap   ask for the Input Monitoring permission, then try the event tap again
// The event tap logs only while a client has this input method active.
import Carbon
import Cocoa
import InputMethodKit

let logDir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/yuragi-probe")
let logURL = logDir.appendingPathComponent("imk.jsonl")
let logLock = NSLock()
var logHandle: FileHandle? = nil
var active = false
var tapPort: CFMachPort? = nil

func uptime() -> Double { ProcessInfo.processInfo.systemUptime }

func emit(_ d: [String: Any]) {
    var d = d
    d["now"] = (uptime() * 1e6).rounded() / 1e6
    guard let data = try? JSONSerialization.data(withJSONObject: d, options: [.sortedKeys]) else { return }
    logLock.lock()
    defer { logLock.unlock() }
    if logHandle == nil {
        try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: logURL.path) { FileManager.default.createFile(atPath: logURL.path, contents: nil) }
        logHandle = try? FileHandle(forWritingTo: logURL)
        logHandle?.seekToEndOfFile()
    }
    logHandle?.write(data)
    logHandle?.write("\n".data(using: .utf8)!)
}

func flag(_ name: String) -> Bool { FileManager.default.fileExists(atPath: logDir.appendingPathComponent(name).path) }

// ---- event tap (MACOS.md §9 #2) ----

func tapCallback(proxy: CGEventTapProxy, type: CGEventType, event: CGEvent, refcon: UnsafeMutableRawPointer?) -> Unmanaged<CGEvent>? {
    if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        emit(["ev": "tap-disabled", "type": Int(type.rawValue)])
        if let p = tapPort { CGEvent.tapEnable(tap: p, enable: true) }
    } else if active {
        emit(["ev": "tap", "type": Int(type.rawValue),
              "code": event.getIntegerValueField(.keyboardEventKeycode),
              "kbtype": event.getIntegerValueField(.keyboardEventKeyboardType),
              "repeat": event.getIntegerValueField(.keyboardEventAutorepeat),
              "flags": event.flags.rawValue,
              "srcpid": event.getIntegerValueField(.eventSourceUnixProcessID),
              "t": Double(event.timestamp) / 1e9])
    }
    return Unmanaged.passUnretained(event)
}

func tryTap(_ why: String) {
    if tapPort != nil { return }
    let mask: CGEventMask = (1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.keyUp.rawValue) | (1 << CGEventType.flagsChanged.rawValue)
    let pre = CGPreflightListenEventAccess()
    // creating the tap without the permission makes the OS ask for it; do that only for "request-tap"
    if !pre && why != "request" { emit(["ev": "tap-create", "why": why, "preflight": false, "created": false, "enabled": false]); return }
    tapPort = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap, options: .listenOnly,
                                eventsOfInterest: mask, callback: tapCallback, userInfo: nil)
    if let p = tapPort {
        CFRunLoopAddSource(CFRunLoopGetMain(), CFMachPortCreateRunLoopSource(nil, p, 0), .commonModes)
        CGEvent.tapEnable(tap: p, enable: true)
    }
    emit(["ev": "tap-create", "why": why, "preflight": pre, "created": tapPort != nil,
          "enabled": tapPort.map { CGEvent.tapIsEnabled(tap: $0) } ?? false])
}

// ---- the controller ----

func describe(_ e: NSEvent) -> [String: Any] {
    var d: [String: Any] = ["type": Int(e.type.rawValue), "code": Int(e.keyCode), "t": e.timestamp,
                            "mods": e.modifierFlags.rawValue]
    if e.type == .keyDown || e.type == .keyUp {
        d["repeat"] = e.isARepeat
        if flag("chars") {  // typed characters are logged only on request
            d["chars"] = e.characters ?? ""
            d["charsIM"] = e.charactersIgnoringModifiers ?? ""
        }
    }
    if let c = e.cgEvent {
        d["kbtype"] = c.getIntegerValueField(.keyboardEventKeyboardType)
        d["cg_t"] = Double(c.timestamp) / 1e9
    } else {
        d["cg"] = false
    }
    d["kbtype_sys"] = Int(LMGetKbdType())
    return d
}

@objc(ProbeController)
class ProbeController: IMKInputController {
    var buf = ""
    var lastCommit = ""

    override func recognizedEvents(_ sender: Any!) -> Int {
        let m: NSEvent.EventTypeMask = [.keyDown, .keyUp, .flagsChanged]
        return Int(m.rawValue)
    }

    override func activateServer(_ sender: Any!) {
        active = true
        let c = sender as? IMKTextInput
        emit(["ev": "activate", "app": c?.bundleIdentifier() ?? "", "mark": flag("mark"), "eatModes": flag("eat-modes")])
        if flag("request-tap") && tapPort == nil {
            let granted = CGRequestListenEventAccess()
            emit(["ev": "tap-request", "granted": granted])
            tryTap("request")
        }
        super.activateServer(sender)
    }

    override func deactivateServer(_ sender: Any!) {
        emit(["ev": "deactivate", "app": (sender as? IMKTextInput)?.bundleIdentifier() ?? ""])
        active = false
        super.deactivateServer(sender)
    }

    override func setValue(_ value: Any!, forTag tag: Int, client sender: Any!) {
        emit(["ev": "setValue", "value": "\(value ?? "nil")", "tag": tag])
        super.setValue(value, forTag: tag, client: sender)
    }

    override func commitComposition(_ sender: Any!) {
        emit(["ev": "commitComposition", "buf": buf])
        if !buf.isEmpty, let c = sender as? IMKTextInput {
            c.insertText(buf, replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
            buf = ""
        }
    }

    func clientState(_ c: IMKTextInput) -> [String: Any] {
        var d: [String: Any] = ["app": c.bundleIdentifier() ?? ""]
        let sel = c.selectedRange()
        d["sel"] = [sel.location == NSNotFound ? -1 : sel.location, sel.length]
        let mr = c.markedRange()
        d["marked"] = [mr.location == NSNotFound ? -1 : mr.location, mr.length]
        d["length"] = c.length()
        let start = mr.location != NSNotFound ? mr.location : sel.location
        if start != NSNotFound {
            let n = min(start, 20)
            // the text itself stays out of the log unless "chars" is set: only whether it came and whether it ends with what we committed
            let left = c.attributedSubstring(from: NSRange(location: start - n, length: n))?.string
            if flag("chars") { d["left"] = left ?? NSNull() }
            d["leftLen"] = left.map { ($0 as NSString).length } ?? -1
            d["leftEndsWithCommitted"] = !lastCommit.isEmpty && (left ?? "").hasSuffix(lastCommit)
        }
        var rect = NSRect.zero
        let attrs = c.attributes(forCharacterIndex: 0, lineHeightRectangle: &rect)
        d["rect"] = [rect.origin.x, rect.origin.y, rect.size.width, rect.size.height]
        d["attrKeys"] = (attrs ?? [:]).keys.map { "\($0)" }.sorted()
        d["validAttrs"] = (c.validAttributesForMarkedText() ?? []).map { "\($0)" }
        return d
    }

    func show(_ c: IMKTextInput) {
        let a = NSMutableAttributedString(string: buf)
        // two clauses when long enough: first thick (focused), rest thin
        let head = min(buf.count, 2)
        if head > 0 {
            a.addAttributes([.underlineStyle: NSUnderlineStyle.thick.rawValue, .markedClauseSegment: 0], range: NSRange(location: 0, length: head))
        }
        if buf.count > head {
            a.addAttributes([.underlineStyle: NSUnderlineStyle.single.rawValue, .markedClauseSegment: 1],
                            range: NSRange(location: head, length: (buf as NSString).length - head))
        }
        c.setMarkedText(a, selectionRange: NSRange(location: (buf as NSString).length, length: 0),
                        replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
    }

    override func handle(_ event: NSEvent!, client sender: Any!) -> Bool {
        guard let event = event else { return false }
        var d = describe(event)
        d["ev"] = "handle"
        let c = sender as? IMKTextInput
        var handled = false
        if event.type == .keyDown {
            let code = Int(event.keyCode)
            if (code == 102 || code == 104) && flag("eat-modes") {
                handled = true
            } else if flag("mark"), let c = c {
                let plain = event.modifierFlags.intersection([.command, .control, .option]).isEmpty
                if code == 36 && !buf.isEmpty {
                    lastCommit = buf
                    c.insertText(buf, replacementRange: NSRange(location: NSNotFound, length: NSNotFound))
                    buf = ""
                    handled = true
                } else if code == 53 && !buf.isEmpty {
                    buf = ""
                    show(c)
                    handled = true
                } else if plain, let s = event.characters, s.count == 1, let u = s.unicodeScalars.first, u.value > 0x20, u.value < 0x7f {
                    // show a kana so that the marked text is not plain ASCII
                    buf += String(UnicodeScalar(0x3042 + (u.value - 0x21) % 80)!)
                    show(c)
                    handled = true
                }
                if handled { d["client"] = clientState(c) }
            }
        }
        d["handled"] = handled
        emit(d)
        return handled
    }
}

emit(["ev": "start", "pid": Int(getpid()), "bundle": Bundle.main.bundleIdentifier ?? "", "path": Bundle.main.bundlePath,
      "kbtype_sys": Int(LMGetKbdType())])
let server = IMKServer(name: Bundle.main.infoDictionary?["InputMethodConnectionName"] as? String,
                       bundleIdentifier: Bundle.main.bundleIdentifier)
emit(["ev": "server", "ok": server != nil])
tryTap("start")
NSApplication.shared.run()
