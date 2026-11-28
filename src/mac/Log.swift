// ~/Library/Logs/yuragi-ime/input.log: what the input program did, never what was typed.
// Key codes go in only while the file "debug" is in that folder.
import Foundation

enum Log {
    static let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/yuragi-ime")
    private static let lock = NSLock()
    private static var handle: FileHandle?
    private static let stamp: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        return f
    }()

    static var debug: Bool { FileManager.default.fileExists(atPath: dir.appendingPathComponent("debug").path) }

    static func write(_ message: String) {
        lock.lock()
        defer { lock.unlock() }
        if handle == nil {
            let url = dir.appendingPathComponent("input.log")
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            if !FileManager.default.fileExists(atPath: url.path) { FileManager.default.createFile(atPath: url.path, contents: nil) }
            handle = try? FileHandle(forWritingTo: url)
            _ = try? handle?.seekToEnd()
        }
        try? handle?.write(contentsOf: Data("\(stamp.string(from: Date())) input: \(message)\n".utf8))
    }
}

/// Milliseconds on the clock of NSEvent.timestamp: the `t` of every request.
func nowMs() -> UInt64 { UInt64(ProcessInfo.processInfo.systemUptime * 1000) }
