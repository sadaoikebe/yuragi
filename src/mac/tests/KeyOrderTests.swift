// The order the engine gets key ups in (KeyOrder.swift). Built and run by src/mac/test.sh.
import Foundation

final class Field: KeyUpReceiver {
    var ups: [String] = []
    func keyUp(code: UInt16, vk: UInt32, t: UInt64) { ups.append("\(code)/\(vk)@\(t)") }
}

var failures = 0

func check<T: Equatable>(_ got: T, _ want: T, _ what: String, line: Int = #line) {
    if got == want { return }
    failures += 1
    print("FAIL line \(line): \(what): got \(got), want \(want)")
}

func deliver(_ ups: [KeyOrder.Up]) {
    for up in ups { up.receiver.keyUp(code: up.code, vk: up.vk, t: up.t) }
}

let A: UInt16 = 0, B: UInt16 = 11, X: UInt16 = 7
let vkA: UInt32 = 0x41, vkB: UInt32 = 0x42, vkX: UInt32 = 0x58

/// A down the tap saw, then handle() got and sent to the engine.
func press(_ order: inout KeyOrder, _ code: UInt16, vk: UInt32, t: UInt64, to field: Field) {
    deliver(order.seen(code, t: t, down: true)!)
    deliver(order.arrive(code, now: t + 10, tracking: true).ups)
    deliver(order.settle(code, vk: vk, sentTo: field))
}

func tests() {
    do {  // the down's real time; its up goes to the field it was sent to
        var order = KeyOrder()
        let field = Field()
        deliver(order.seen(A, t: 100, down: true)!)
        let arrived = order.arrive(A, now: 120, tracking: true)
        check(arrived.t, 100, "the time the tap saw")
        deliver(arrived.ups)
        deliver(order.settle(A, vk: vkA, sentTo: field))
        check(field.ups, [], "nothing before the up")
        deliver(order.seen(A, t: 180, down: false)!)
        check(field.ups, ["0/65@180"], "the up")
    }
    do {  // an up the tap saw before handle() got the down waits for it
        var order = KeyOrder()
        let field = Field()
        deliver(order.seen(A, t: 100, down: true)!)
        deliver(order.seen(A, t: 110, down: false)!)
        check(field.ups, [], "the down is still on its way")
        let arrived = order.arrive(A, now: 130, tracking: true)
        check(arrived.t, 100, "the time the tap saw")
        deliver(arrived.ups)
        check(field.ups, [], "not before the down is sent")
        deliver(order.settle(A, vk: vkA, sentTo: field))
        check(field.ups, ["0/65@110"], "after the down is sent")
    }
    do {  // down A, down B, up A: the up of A goes after the down of B
        var order = KeyOrder()
        let field = Field()
        deliver(order.seen(A, t: 100, down: true)!)
        deliver(order.seen(B, t: 110, down: true)!)
        deliver(order.seen(A, t: 120, down: false)!)
        deliver(order.arrive(A, now: 125, tracking: true).ups)
        deliver(order.settle(A, vk: vkA, sentTo: field))
        check(field.ups, [], "B is still on its way")
        let arrived = order.arrive(B, now: 135, tracking: true)
        check(arrived.t, 110, "the time of B")
        deliver(arrived.ups)
        check(field.ups, [], "not before B is sent")
        deliver(order.settle(B, vk: vkB, sentTo: field))
        check(field.ups, ["0/65@120"], "after B is sent")
        deliver(order.seen(B, t: 150, down: false)!)
        check(field.ups, ["0/65@120", "11/66@150"], "the up of B")
    }
    do {  // a down that was not sent to the engine has no up
        var order = KeyOrder()
        let field = Field()
        deliver(order.seen(A, t: 100, down: true)!)
        deliver(order.arrive(A, now: 110, tracking: true).ups)
        deliver(order.settle(A, vk: 0, sentTo: nil))
        deliver(order.seen(A, t: 150, down: false)!)
        check(field.ups, [], "no up")
    }
    do {  // a down that never comes to handle() is given up after transitMs; the ups behind it go then
        var order = KeyOrder()
        let field = Field()
        press(&order, X, vk: vkX, t: 100, to: field)
        deliver(order.seen(A, t: 200, down: true)!)
        deliver(order.seen(X, t: 210, down: false)!)
        check(field.ups, [], "behind a down on its way")
        var swept = order.sweep(now: 200 + KeyOrder.transitMs - 1)
        deliver(swept.ups)
        check(swept.more, true, "still on its way")
        check(field.ups, [], "not yet")
        swept = order.sweep(now: 200 + KeyOrder.transitMs)
        deliver(swept.ups)
        check(swept.more, false, "given up")
        check(field.ups, ["7/88@210"], "the up behind it")
        check(order.arrive(A, now: 500, tracking: false).t, nil, "a given-up down is no longer known")
    }
    do {  // downs before the one handle() got were not for this input method
        var order = KeyOrder()
        let field = Field()
        press(&order, X, vk: vkX, t: 100, to: field)
        deliver(order.seen(A, t: 200, down: true)!)
        deliver(order.seen(X, t: 205, down: false)!)
        deliver(order.seen(B, t: 210, down: true)!)
        let arrived = order.arrive(B, now: 220, tracking: true)
        check(arrived.t, 210, "the time of B")
        deliver(arrived.ups)
        check(field.ups, ["7/88@205"], "the up before B, once A is passed over")
    }
    do {  // a down handle() got before the tap did: the tap's copy is dropped, the next down is not
        var order = KeyOrder()
        let field = Field()
        check(order.arrive(A, now: 100, tracking: true).t, nil, "the tap has not seen it")
        deliver(order.settle(A, vk: vkA, sentTo: nil))
        check(order.seen(A, t: 95, down: true) == nil, true, "the tap's copy of that down")
        deliver(order.seen(A, t: 150, down: false)!)
        check(field.ups, [], "its up is not sent")
        check(order.seen(A, t: 400, down: true) != nil, true, "the next down")
        check(order.arrive(A, now: 410, tracking: true).t, 400, "is known")
    }
    do {  // an older record of an early down does not drop a later down
        var order = KeyOrder()
        _ = order.arrive(A, now: 100, tracking: true)
        check(order.seen(A, t: 300, down: true) != nil, true, "a down after that time")
    }
    do {  // while the tap sees nothing, an early down is not recorded
        var order = KeyOrder()
        _ = order.arrive(A, now: 100, tracking: false)
        check(order.seen(A, t: 95, down: true) != nil, true, "queued")
    }
    do {  // clear() forgets what is on its way
        var order = KeyOrder()
        deliver(order.seen(A, t: 100, down: true)!)
        order.clear()
        check(order.arrive(A, now: 110, tracking: false).t, nil, "forgotten")
    }
    do {  // a field that is gone gets nothing
        var order = KeyOrder()
        var field: Field? = Field()
        press(&order, A, vk: vkA, t: 100, to: field!)
        field = nil
        check(order.seen(A, t: 150, down: false)!.count, 0, "no up for a field that is gone")
    }
}

@main
enum KeyOrderTests {
    static func main() {
        tests()
        if failures > 0 { exit(1) }
        print("KeyOrder: ok")
    }
}
