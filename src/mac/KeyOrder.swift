// The order of the keys the event tap saw (KeyTap.swift), apart from the OS: which ups may go to
// the engine now, and the real time of a down that handle() has got.
//
// The tap sees a down before handle() gets it, and may see its up, and other keys' ups, before that
// too. The engine must get them in the order they happened, so an up waits here until every down
// before it has reached handle() (or has been given up: a key that never comes to this input method).

protocol KeyUpReceiver: AnyObject {
    func keyUp(code: UInt16, vk: UInt32, t: UInt64)
}

struct KeyOrder {
    /// A down the tap saw is given up when handle() has not got it after this long (ms).
    static let transitMs: UInt64 = 250

    /// An up to send to the engine now.
    struct Up {
        let receiver: KeyUpReceiver
        let code: UInt16
        let vk: UInt32
        let t: UInt64
    }

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

    private var queue: [Entry] = []
    private var held: [UInt16: Held] = [:]  // downs sent to the engine, until their up
    private var early: [UInt16: UInt64] = [:]  // downs handle() got before the tap did: when

    /// No input field has this input method in its kana mode: what is on its way is forgotten.
    mutating func clear() {
        queue.removeAll()
        early.removeAll()
    }

    /// The tap saw a key (not a repeat) at t. nil: a down handle() has had already; else the ups to send.
    mutating func seen(_ code: UInt16, t: UInt64, down: Bool) -> [Up]? {
        if down, let at = early[code] {
            early[code] = nil
            if at >= t && at - t < KeyOrder.transitMs { return nil }
        }
        queue.append(Entry(code: code, t: t, down: down))
        return flush()
    }

    /// handle() has a key down (not a repeat). The ups that happened before it go to the engine
    /// first; t is the time the key really went down, or nil when the tap has not seen it.
    /// tracking: the tap is seeing keys, so it will see this one later.
    mutating func arrive(_ code: UInt16, now: UInt64, tracking: Bool) -> (t: UInt64?, ups: [Up]) {
        guard let index = queue.firstIndex(where: { $0.down && !$0.settled && $0.code == code }) else {
            if tracking { early[code] = now }
            return (nil, [])
        }
        // Downs before it that handle() never got were not for this input method.
        for i in 0..<index where queue[i].down { queue[i].settled = true }
        queue[index].settled = true
        let t = queue[index].t
        // What the tap saw after this down waits for settle().
        let after = Array(queue[(index + 1)...])
        queue.removeSubrange((index + 1)...)
        let ups = flush()
        queue.append(contentsOf: after)
        return (t, ups)
    }

    /// The down handle() just had went to the engine (receiver) or not (nil). Then the ups after it go.
    mutating func settle(_ code: UInt16, vk: UInt32, sentTo receiver: KeyUpReceiver?) -> [Up] {
        if let receiver = receiver { held[code] = Held(receiver: receiver, vk: vk) }
        return flush()
    }

    /// Gives up the downs handle() has not got in transitMs. more: some are still on their way.
    mutating func sweep(now: UInt64) -> (ups: [Up], more: Bool) {
        for i in queue.indices where queue[i].down && now >= queue[i].t + KeyOrder.transitMs {
            queue[i].settled = true
        }
        let ups = flush()
        return (ups, queue.contains { $0.down && !$0.settled })
    }

    /// Takes what is at the head of the queue, up to the first down still on its way to handle().
    private mutating func flush() -> [Up] {
        var ups: [Up] = []
        while let first = queue.first, !first.down || first.settled {
            queue.removeFirst()
            if !first.down, let key = held.removeValue(forKey: first.code), let receiver = key.receiver {
                ups.append(Up(receiver: receiver, code: first.code, vk: key.vk, t: first.t))
            }
        }
        return ups
    }
}
