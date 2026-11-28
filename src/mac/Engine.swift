// The conversion engine as a child process, and its watcher (DESIGN「ブローカーとエンジン」「見張り」):
// one JSON object per line on the engine's stdin and stdout. The decisions are broker_core's
// (YRWatcher); this file owns the process, the pipes and the timer. Everything here but the
// readers runs on the main thread.
import Cocoa

protocol EngineSession: AnyObject {
    /// A reply, or `lm_done`, `reset` and `state` events (DESIGN「通信」).
    func receive(_ m: YRMessage)
}

final class Engine: NSObject, YRWatcherPlatform {
    static let shared = Engine()

    private enum Item {
        case line(String)
        case fatal(String)  // a "fatal ..." line of the engine's stderr
        case exit(Int32)
    }

    private(set) var table: YRKeyTable?
    private lazy var watcher = YRWatcher(platform: self)
    private var started = false
    private var process: Process?
    private var dataDir: URL?
    private var input: Int32 = -1
    private let arrived = NSCondition()
    private var items: [Item] = []
    private var sessions: [Int: () -> EngineSession?] = [:]
    private var outbox: [(Int, String)] = []  // lines for sessions, delivered outside the watcher's calls
    private var delivering = false
    private var timer: DispatchSourceTimer?
    private var lastSid = 0
    private var lastSeq = 0

    var state: YRState { watcher.state }

    func start() {
        guard !started else { return }
        started = true
        call { watcher.start() }
    }

    /// DESIGN「メニュー」「もう一度試す」.
    func retry() { call { watcher.retry() } }

    /// A session for one input field.
    func open(_ session: EngineSession) -> Int {
        lastSid += 1
        let sid = lastSid
        sessions[sid] = { [weak session] in session }
        call { watcher.sessionOpened(UInt64(sid)) }
        return sid
    }

    func close(_ sid: Int) {
        guard sessions.removeValue(forKey: sid) != nil else { return }
        call { watcher.sessionClosed(UInt64(sid)) }
    }

    // The settings window's connections (Peers.swift) share the sessions' numbers.
    func peerConnected() -> Int {
        lastSid += 1
        watcher.peerConnected(UInt64(lastSid))
        return lastSid
    }

    func peerLine(_ id: Int, _ line: String) { call { watcher.session(UInt64(id), line: line) } }

    func peerClosed(_ id: Int) { call { watcher.sessionClosed(UInt64(id)) } }

    /// DESIGN「メニュー」「設定を開く」.

    func nextSeq() -> Int {
        lastSeq += 1
        return lastSeq
    }

    /// A request with a `seq`: the session gets one line with that seq, from the engine or the watcher.
    func send(_ sid: Int, _ message: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: message) else { return }
        call { watcher.session(UInt64(sid), line: String(decoding: data, as: UTF8.self)) }
    }

    /// Waits on the main thread until done() or the deadline, handling replies as they arrive.
    func wait(until deadline: Date, done: () -> Bool) -> Bool {
        while true {
            drain()
            if done() { return true }
            arrived.lock()
            let more = !items.isEmpty || arrived.wait(until: deadline)
            arrived.unlock()
            if !more { return done() }
        }
    }

    /// DESIGN「状態」, as the user is told.
    var problem: String? {
        if !KeyTap.shared.running { return "「入力監視」の許可が要ります。メニューバーの「ゆ」から設定を開けます" }
        if state == .down { return "日本語変換が止まっています。メニューバーの「ゆ」から「もう一度試す」を選んでください" }
        return nil
    }

    // -- the watcher's calls ---------------------------------------------------------------

    /// Every call into the watcher: then its lines go to the sessions and its timer is set again.
    private func call(_ body: () -> Void) {
        body()
        guard !delivering else { return }  // the outer call delivers what this one added
        delivering = true
        while !outbox.isEmpty {
            let (sid, line) = outbox.removeFirst()
            guard let session = sessions[sid] else { Peers.shared.write(sid, line); continue }
            guard let m = YRMessage.parse(line) else { continue }
            if let keymap = m.keymap { table = keymap }
            session()?.receive(m)
        }
        delivering = false
        schedule()
    }

    private func schedule() {
        timer?.cancel()
        timer = nil
        let at = watcher.nextDeadline
        guard at != Int64.max else { return }
        let source = DispatchSource.makeTimerSource(queue: .main)
        source.schedule(deadline: .now() + .milliseconds(Int(max(0, at - Int64(nowMs()))) + 1))
        source.setEventHandler { [weak self] in self?.call { self?.watcher.timer() } }
        timer = source
        source.resume()
    }

    /// Handles what arrived from the engine, in order.
    private func drain() {
        while true {
            arrived.lock()
            let batch = items
            items.removeAll()
            arrived.unlock()
            if batch.isEmpty { return }
            for item in batch {
                switch item {
                case .line(let line): call { watcher.engineLine(line) }
                case .fatal(let line): watcher.engineStderrLine(line)
                case .exit(let code):
                    Darwin.close(input)
                    input = -1
                    process = nil
                    call { watcher.engineExit(code) }
                }
            }
        }
    }

    private func post(_ new: [Item]) {
        arrived.lock()
        items.append(contentsOf: new)
        arrived.broadcast()
        arrived.unlock()
        DispatchQueue.main.async { self.drain() }
    }

    // -- YRWatcherPlatform -----------------------------------------------------------------

    func startEngine() -> String? {
        guard let (child, args) = Launch.python("args") else { return "engine.json unreadable: \(Launch.config.path)" }
        // The user's data (yuragi.ime.config.DEFAULT_RUNTIME_DIR, or the engine's --data-dir).
        let at = args.firstIndex(of: "--data-dir").map { $0 + 1 }
        dataDir = at.flatMap { $0 < args.count ? URL(fileURLWithPath: args[$0]) : nil }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".yuragi-ime")
        let toEngine = Pipe(), fromEngine = Pipe(), errors = Pipe()
        child.standardInput = toEngine
        child.standardOutput = fromEngine
        child.standardError = errors
        let log = Log.dir.appendingPathComponent("engine.log")
        try? FileManager.default.createDirectory(at: Log.dir, withIntermediateDirectories: true)
        _ = try? FileManager.default.replaceItemAt(Log.dir.appendingPathComponent("engine.prev.log"), withItemAt: log)
        FileManager.default.createFile(atPath: log.path, contents: nil)
        let ended = DispatchSemaphore(value: 0)
        child.terminationHandler = { _ in ended.signal() }
        do { try child.run() } catch { return error.localizedDescription }
        process = child
        input = dup(toEngine.fileHandleForWriting.fileDescriptor)
        try? toEngine.fileHandleForWriting.close()
        try? fromEngine.fileHandleForWriting.close()
        try? errors.fileHandleForWriting.close()
        // A full pipe (an engine that reads nothing) must not stop the application's key.
        _ = fcntl(input, F_SETFL, fcntl(input, F_GETFL) | O_NONBLOCK)
        Log.write("engine started pid \(child.processIdentifier)")
        let errorsRead = DispatchSemaphore(value: 0)
        let errorLog = try? FileHandle(forWritingTo: log)
        Thread.detachNewThread { [self] in
            Self.lines(of: errors.fileHandleForReading, raw: { try? errorLog?.write(contentsOf: $0) }) { line in
                if line.hasPrefix("fatal ") { post([.fatal(line)]) }
            }
            errorsRead.signal()
        }
        Thread.detachNewThread { [self] in
            Self.lines(of: fromEngine.fileHandleForReading, raw: { _ in }) { post([.line($0)]) }
            // Its stdout is closed: the exit is told once the process and its stderr have ended too.
            if ended.wait(timeout: .now() + 2) == .timedOut {
                kill(child.processIdentifier, SIGKILL)
                ended.wait()
            }
            _ = errorsRead.wait(timeout: .now() + 1)
            let signalled = child.terminationReason == .uncaughtSignal
            post([.exit(signalled ? -child.terminationStatus : child.terminationStatus)])
        }
        return nil
    }

    /// Until the end of the stream or an error. read(2), not FileHandle's reading: that one raises
    /// an exception Swift cannot catch when the read fails.
    private static func lines(of handle: FileHandle, raw: (Data) -> Void, each: (String) -> Void) {
        var rest = Data()
        var buffer = [UInt8](repeating: 0, count: 1 << 16)
        while true {
            let count = Darwin.read(handle.fileDescriptor, &buffer, buffer.count)
            if count < 0 && errno == EINTR { continue }
            if count <= 0 { return }
            let chunk = Data(buffer[0..<count])
            raw(chunk)
            rest.append(chunk)
            while let end = rest.firstIndex(of: 0x0A) {
                each(String(decoding: rest[rest.startIndex..<end], as: UTF8.self))
                rest.removeSubrange(rest.startIndex...end)
            }
        }
    }

    func writeEngine(_ line: String) {
        guard input >= 0 else { return }
        var data = Data(line.utf8)
        data.append(0x0A)
        let written = data.withUnsafeBytes { Darwin.write(input, $0.baseAddress, $0.count) }
        if written == data.count { return }
        // Nothing went out: the watcher ends an engine that does not answer (ENGINE_HANG_MS).
        Log.write("engine write failed (\(written) of \(data.count), errno \(errno))")
        if written > 0 { killEngine() }  // half a line went out: the stream cannot be used again
    }

    func killEngine() {
        if let process = process, process.isRunning { kill(process.processIdentifier, SIGKILL) }
    }

    func writeSession(_ sid: UInt64, line: String) { outbox.append((Int(sid), line)) }

    /// DESIGN「通知」: logs/notices.log is where the settings window reads the last stop from.
    func engineStopped(_ reason: String) {
        Log.write("conversion stopped: \(reason)")
        guard let logs = dataDir?.appendingPathComponent("logs") else { return }
        let stamp = ISO8601DateFormatter.string(from: Date(), timeZone: .current,
                                                formatOptions: [.withFullDate, .withTime, .withColonSeparatorInTime])
        try? FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        let file = logs.appendingPathComponent("notices.log")
        if !FileManager.default.fileExists(atPath: file.path) { FileManager.default.createFile(atPath: file.path, contents: nil) }
        guard let handle = try? FileHandle(forWritingTo: file) else { return }
        // The throwing calls: the older ones raise an exception Swift cannot catch (a full disk).
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: Data("{\"time\":\"\(stamp)\",\"stopped\":\"\(reason)\"}\n".utf8))
        try? handle.close()
    }

    /// The settings window: its own process. A second one hands over to the first (admin_ui).
    /// The settings window is its own application inside this bundle (settings/): opening it again
    /// brings the one that is running to the front. `pane` is where a new one opens (settings/App.swift).
    func openSettings(pane: String? = nil) {
        let app = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/Yuragi Settings.app")
        let how = NSWorkspace.OpenConfiguration()
        how.activates = true
        if let pane { how.arguments = ["-pane", pane] }
        NSWorkspace.shared.openApplication(at: app, configuration: how) { _, error in
            if let error { Log.write("settings window not opened: \(error.localizedDescription)") }
        }
    }

    func openAdmin() { openSettings() }

    func log(_ line: String) { Log.write(line) }
}
