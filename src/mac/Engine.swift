// The conversion engine as a child process (DESIGN「ブローカーとエンジン」): one JSON object per line
// on its stdin and stdout. Everything here but the reader runs on the main thread.
import Foundation

protocol EngineSession: AnyObject {
    func reply(_ m: YRMessage)
    func lmDone()
    /// The engine is gone: what is on screen stays (DESIGN「見えている文字の確定」).
    func engineLost()
}

final class Engine {
    static let shared = Engine()
    enum State { case stopped, starting, ready }

    private(set) var state = State.stopped
    private(set) var table: YRKeyTable?
    private var process: Process?
    private var input: Int32 = -1
    private let arrived = NSCondition()
    private var lines: [String?] = []  // nil: the engine closed its stdout
    private var sessions: [Int: () -> EngineSession?] = [:]
    private var lastSid = 0
    private var lastSeq = 0

    /// versions/<tag>/engine.json beside the shared files (MACOS.md §4.6; the form is src/broker/support.h).
    private var configURL: URL {
        let tag = Bundle.main.object(forInfoDictionaryKey: "YuragiTag") as? String ?? "dev"
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/yuragi-ime/versions/\(tag)/engine.json")
    }

    func start() {
        guard state == .stopped else { return }
        guard let data = try? Data(contentsOf: configURL),
              let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let python = config["python"] as? String, let app = config["app"] as? String,
              let args = config["args"] as? [String] else {
            Log.write("engine.json unreadable: \(configURL.path)")
            return
        }
        let child = Process()
        child.executableURL = URL(fileURLWithPath: python)
        child.arguments = args
        child.currentDirectoryURL = URL(fileURLWithPath: app)
        var env = ProcessInfo.processInfo.environment
        env.removeValue(forKey: "PYTHONPATH")
        env.removeValue(forKey: "PYTHONHOME")
        for (key, value) in ["PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1", "HF_HUB_OFFLINE": "1"] {
            env[key] = value
        }
        child.environment = env
        let toEngine = Pipe(), fromEngine = Pipe()
        child.standardInput = toEngine
        child.standardOutput = fromEngine
        let log = Log.dir.appendingPathComponent("engine.log")
        try? FileManager.default.createDirectory(at: Log.dir, withIntermediateDirectories: true)
        _ = try? FileManager.default.replaceItemAt(Log.dir.appendingPathComponent("engine.prev.log"), withItemAt: log)
        FileManager.default.createFile(atPath: log.path, contents: nil)
        child.standardError = (try? FileHandle(forWritingTo: log)) ?? FileHandle.nullDevice
        do { try child.run() } catch {
            Log.write("engine not started: \(error.localizedDescription)")
            return
        }
        process = child
        input = dup(toEngine.fileHandleForWriting.fileDescriptor)
        try? toEngine.fileHandleForWriting.close()
        // A full pipe (an engine that reads nothing) must not stop the application's key.
        _ = fcntl(input, F_SETFL, fcntl(input, F_GETFL) | O_NONBLOCK)
        state = .starting
        Log.write("engine started pid \(child.processIdentifier)")
        let output = fromEngine.fileHandleForReading
        Thread.detachNewThread { [self] in read(output) }
    }

    private func read(_ output: FileHandle) {
        var rest = Data()
        while true {
            let chunk = output.availableData
            var got: [String?] = []
            if chunk.isEmpty {
                got.append(nil)
            } else {
                rest.append(chunk)
                while let end = rest.firstIndex(of: 0x0A) {
                    got.append(String(decoding: rest[rest.startIndex..<end], as: UTF8.self))
                    rest.removeSubrange(rest.startIndex...end)
                }
            }
            if !got.isEmpty {
                arrived.lock()
                lines.append(contentsOf: got)
                arrived.broadcast()
                arrived.unlock()
                DispatchQueue.main.async { self.drain() }
            }
            if chunk.isEmpty { return }
        }
    }

    /// A session for one input field. `open` goes out now, or when the engine becomes ready.
    func open(_ session: EngineSession) -> Int {
        lastSid += 1
        let sid = lastSid
        sessions[sid] = { [weak session] in session }
        if state == .ready { _ = send(["op": "open", "sid": sid]) }
        return sid
    }

    func close(_ sid: Int) {
        guard sessions.removeValue(forKey: sid) != nil else { return }
        if state == .ready { _ = send(["op": "close", "sid": sid]) }
    }

    func nextSeq() -> Int {
        lastSeq += 1
        return lastSeq
    }

    /// false: the line did not go out (no engine, or its pipe is full or broken).
    func send(_ message: [String: Any]) -> Bool {
        guard state != .stopped, var data = try? JSONSerialization.data(withJSONObject: message) else { return false }
        data.append(0x0A)
        let written = data.withUnsafeBytes { Darwin.write(input, $0.baseAddress, $0.count) }
        if written == data.count { return true }
        Log.write("engine write failed (\(written) of \(data.count), errno \(errno))")
        if written > 0 { lost() }  // half a line went out: the stream cannot be used again
        return false
    }

    /// Handles the lines that arrived, in order.
    func drain() {
        while true {
            arrived.lock()
            let batch = lines
            lines.removeAll()
            arrived.unlock()
            if batch.isEmpty { return }
            for line in batch {
                guard let line = line else { lost(); continue }
                guard let m = YRMessage.parse(line) else { continue }
                if m.ready {
                    table = m.keymap ?? table
                    state = .ready
                    Log.write("engine ready, key table \(table?.rev ?? "none")")
                    for sid in sessions.keys.sorted() { _ = send(["op": "open", "sid": sid]) }
                } else if m.event == "keymap" {
                    table = m.keymap ?? table
                } else if m.event == "lm_done" {
                    if m.hasSid { sessions[Int(m.sid)]?()?.lmDone() }
                } else if m.event == "warning" {
                    Log.write("engine warning")
                } else if m.hasSeq, m.hasSid {
                    sessions[Int(m.sid)]?()?.reply(m)
                }
            }
        }
    }

    /// Waits on the main thread until done() or the deadline, handling replies as they arrive.
    func wait(until deadline: Date, done: () -> Bool) -> Bool {
        while true {
            drain()
            if done() { return true }
            arrived.lock()
            let more = !lines.isEmpty || arrived.wait(until: deadline)
            arrived.unlock()
            if !more { return done() }
        }
    }

    private func lost() {
        guard state != .stopped else { return }
        state = .stopped
        Darwin.close(input)
        input = -1
        process = nil
        Log.write("engine lost")
        for session in sessions.values { session()?.engineLost() }
    }
}
