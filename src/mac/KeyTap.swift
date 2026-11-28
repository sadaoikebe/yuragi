// The keys as the OS sees them (MACOS.md §6.1): InputMethodKit gives the downs late and no ups, so
// an event tap (it needs the "Input Monitoring" permission) supplies the real time of each down
// and the ups. It only listens; whether a key is eaten is still answered in handle().
// The order the engine gets them in is KeyOrder's; this file owns the tap and the timer.
import Cocoa

final class KeyTap {
    static let shared = KeyTap()

    private var port: CFMachPort?
    private var asked = false
    private var order = KeyOrder()
    private var sweep: DispatchSourceTimer?
    /// Keys are tracked only while an input field has this input method in its kana mode.
    var listening = false {
        didSet { if !listening { order.clear() } }
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
        guard let ups = order.seen(code, t: t, down: type == .keyDown) else { return }  // handle() has had this one
        if Log.debug { Log.write("tap \(type == .keyDown ? "down" : "up") \(code) t \(t)") }
        send(ups)
        if type == .keyDown { scheduleSweep() }
    }

    /// handle() has a key down (not a repeat). The ups that happened before it go to the engine
    /// first; the result is the time the key really went down, or nil when the tap has not seen it.
    func arrive(_ code: UInt16) -> UInt64? {
        let (t, ups) = order.arrive(code, now: nowMs(), tracking: running && listening)
        send(ups)
        return t
    }

    /// The down handle() just had went to the engine (receiver) or not (nil). Then the ups after it go.
    func settle(_ code: UInt16, vk: UInt32, sentTo receiver: KeyUpReceiver?) {
        send(order.settle(code, vk: vk, sentTo: receiver))
    }

    private func send(_ ups: [KeyOrder.Up]) {
        for up in ups { up.receiver.keyUp(code: up.code, vk: up.vk, t: up.t) }
    }

    private func scheduleSweep() {
        guard sweep == nil else { return }
        let source = DispatchSource.makeTimerSource(queue: .main)
        source.schedule(deadline: .now() + .milliseconds(Int(KeyOrder.transitMs)))
        source.setEventHandler { [weak self] in
            guard let self = self else { return }
            self.sweep = nil
            let (ups, more) = self.order.sweep(now: nowMs())
            self.send(ups)
            if more { self.scheduleSweep() }
        }
        sweep = source
        source.resume()
    }
}
