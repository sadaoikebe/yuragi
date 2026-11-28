// The keys as the OS sees them (MACOS.md §6.1): InputMethodKit gives the downs late and no ups, so
// an event tap (it needs the "Input Monitoring" permission) supplies the real time of each down
// and the ups. It only listens; whether a key is eaten is still answered in handle().
//
// The tap sees a down before handle() gets it, and may see its up, and other keys' ups, before that
// too. The engine must get them in the order they happened, so an up waits here until every down
// before it has reached handle() (or has been given up: a key that never comes to this input method).
import Cocoa

protocol KeyUpReceiver: AnyObject {
    func keyUp(code: UInt16, vk: UInt32, t: UInt64)
}

final class KeyTap {
    static let shared = KeyTap()
    /// A down the tap saw is given up when handle() has not got it after this long (ms).
    static let transitMs: UInt64 = 250

    private struct Entry {
        let code: UInt16
        let t: UInt64
        let down: Bool
        var settled = false  // a down: handle() has got it (or it was given up)
    }
    private struct Held {
        weak var receiver: KeyUpReceiver?
        let vk: UInt32
    }

    private var port: CFMachPort?
    private var asked = false
    private var queue: [Entry] = []
    private var held: [UInt16: Held] = [:]  // downs sent to the engine, until their up
    private var early: [UInt16: UInt64] = [:]  // downs handle() got before the tap did: when
    private var sweep: DispatchSourceTimer?
    /// Keys are tracked only while an input field has this input method in its kana mode.
    var listening = false {
        didSet { if !listening { queue.removeAll(); early.removeAll() } }
    }

    var running: Bool { port != nil }

    /// Starts the tap if the permission is there. ask: request the permission once (the OS shows
    /// its dialog, and starts this process again when the user allows it).
    func start(ask: Bool) {
        if port != nil { return }
        if !CGPreflightListenEventAccess() {
            if !ask || asked { return }
            asked = true
            // The request alone does not always bring the OS's dialog; creating the tap does.
            Log.write("asking for Input Monitoring: \(CGRequestListenEventAccess())")
        }
        let mask: CGEventMask = (1 << CGEventType.keyDown.rawValue) | (1 << CGEventType.keyUp.rawValue)
        port = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap, options: .listenOnly,
                                 eventsOfInterest: mask, callback: { _, type, event, _ in
            KeyTap.shared.seen(type, event)
            return Unmanaged.passUnretained(event)
        }, userInfo: nil)
        guard let port = port, CGPreflightListenEventAccess() else {
            // Without the permission the tap gets nothing: the OS starts this process again once it is given.
            Log.write("event tap not usable yet")
            self.port = nil
            return
        }
        CFRunLoopAddSource(CFRunLoopGetMain(), CFMachPortCreateRunLoopSource(nil, port, 0), .commonModes)
        CGEvent.tapEnable(tap: port, enable: true)
        Log.write("event tap on")
    }

    private func seen(_ type: CGEventType, _ event: CGEvent) {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let port = port { CGEvent.tapEnable(tap: port, enable: true) }
            return
        }
        guard listening, type == .keyDown || type == .keyUp,
              event.getIntegerValueField(.keyboardEventAutorepeat) == 0 else { return }
        let code = UInt16(truncatingIfNeeded: event.getIntegerValueField(.keyboardEventKeycode))
        let t = event.timestamp / 1_000_000
        if type == .keyDown, let at = early[code] {
            early[code] = nil
            if at >= t && at - t < KeyTap.transitMs { return }  // handle() has had this one
        }
        queue.append(Entry(code: code, t: t, down: type == .keyDown))
        if Log.debug { Log.write("tap \(type == .keyDown ? "down" : "up") \(code) t \(t)") }
        flush()
        if type == .keyDown { scheduleSweep() }
    }

    /// handle() has a key down (not a repeat). The ups that happened before it go to the engine
    /// first; the result is the time the key really went down, or nil when the tap has not seen it.
    func arrive(_ code: UInt16) -> UInt64? {
        guard let index = queue.firstIndex(where: { $0.down && !$0.settled && $0.code == code }) else {
            if running && listening { early[code] = nowMs() }
            return nil
        }
        // Downs before it that handle() never got were not for this input method.
        for i in 0..<index where queue[i].down { queue[i].settled = true }
        queue[index].settled = true
        let t = queue[index].t
        let after = Array(queue[(index + 1)...])
        queue.removeSubrange((index + 1)...)
        flush()
        queue.append(contentsOf: after)
        return t
    }

    /// The down handle() just had went to the engine (receiver) or not (nil). Then the ups after it go.
    func settle(_ code: UInt16, vk: UInt32, sentTo receiver: KeyUpReceiver?) {
        if let receiver = receiver { held[code] = Held(receiver: receiver, vk: vk) }
        flush()
    }

    /// Sends what is at the head of the queue, up to the first down still on its way to handle().
    private func flush() {
        while let first = queue.first, !first.down || first.settled {
            queue.removeFirst()
            if !first.down, let key = held.removeValue(forKey: first.code) {
                key.receiver?.keyUp(code: first.code, vk: key.vk, t: first.t)
            }
        }
    }

    private func scheduleSweep() {
        guard sweep == nil else { return }
        let source = DispatchSource.makeTimerSource(queue: .main)
        source.schedule(deadline: .now() + .milliseconds(Int(KeyTap.transitMs)))
        source.setEventHandler { [weak self] in
            guard let self = self else { return }
            self.sweep = nil
            let now = nowMs()
            for i in self.queue.indices where self.queue[i].down && now >= self.queue[i].t + KeyTap.transitMs {
                self.queue[i].settled = true
            }
            self.flush()
            if self.queue.contains(where: { $0.down && !$0.settled }) { self.scheduleSweep() }
        }
        sweep = source
        source.resume()
    }
}
