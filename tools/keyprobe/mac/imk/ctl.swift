// ctl list | register <app path> | enable <id> | disable <id> | select <id> | current
// Input sources of the probe (and the current one), through Text Input Sources.
import Carbon
import Foundation

func prop<T>(_ s: TISInputSource, _ k: CFString) -> T? {
    guard let p = TISGetInputSourceProperty(s, k) else { return nil }
    return Unmanaged<AnyObject>.fromOpaque(p).takeUnretainedValue() as? T
}
func all() -> [TISInputSource] { (TISCreateInputSourceList(nil, true).takeRetainedValue() as? [TISInputSource]) ?? [] }
func find(_ id: String) -> TISInputSource? { all().first { (prop($0, kTISPropertyInputSourceID) as String?) == id } }
func line(_ s: TISInputSource) -> String {
    let id: String = prop(s, kTISPropertyInputSourceID) ?? "?"
    let en: Bool = prop(s, kTISPropertyInputSourceIsEnabled) ?? false
    let sel: Bool = prop(s, kTISPropertyInputSourceIsSelected) ?? false
    let cap: Bool = prop(s, kTISPropertyInputSourceIsSelectCapable) ?? false
    let type: String = prop(s, kTISPropertyInputSourceType) ?? "?"
    return "\(id) type=\(type) enabled=\(en) selectable=\(cap) selected=\(sel)"
}

let a = CommandLine.arguments
switch a.count > 1 ? a[1] : "" {
case "list":
    for s in all() where ((prop(s, kTISPropertyInputSourceID) as String?) ?? "").contains("YuragiProbe") { print(line(s)) }
case "register":
    print("register status=\(TISRegisterInputSource(URL(fileURLWithPath: a[2]) as CFURL))")
case "enable":
    if let s = find(a[2]) { print("enable status=\(TISEnableInputSource(s))") } else { print("not found") }
    RunLoop.current.run(until: Date().addingTimeInterval(1))
    if let s = find(a[2]) { print(line(s)) }
case "disable":
    if let s = find(a[2]) { print("disable status=\(TISDisableInputSource(s))") } else { print("not found") }
case "select":
    if let s = find(a[2]) { print("select status=\(TISSelectInputSource(s))") } else { print("not found") }
case "current":
    print(line(TISCopyCurrentKeyboardInputSource().takeRetainedValue()))
default:
    print("usage: ctl list | register <app> | enable <id> | disable <id> | select <id> | current")
}
