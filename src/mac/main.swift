// The Yuragi input program (docs/MACOS.md §4.2). The OS starts it when its input source is selected.
import Cocoa
import InputMethodKit

signal(SIGPIPE, SIG_IGN)  // an engine that is gone must not end this process
Log.write("start pid \(getpid())")
let server = IMKServer(name: Bundle.main.infoDictionary?["InputMethodConnectionName"] as? String,
                       bundleIdentifier: Bundle.main.bundleIdentifier)
if server == nil { Log.write("IMKServer not created") }
Engine.shared.start()
Peers.shared.start()
KeyTap.shared.start(ask: false)
NSApplication.shared.run()
