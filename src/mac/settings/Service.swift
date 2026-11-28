// The settings window's work is done in Python (yuragi/ime/admin_service.py), started from engine.json
// like the engine: one request line, one reply line, in order.
import Foundation

final class Service: @unchecked Sendable {  // its state is touched on `queue` only
    private let queue = DispatchQueue(label: "yuragi.settings.service")
    private var child: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var buffer = Data()

    /// The reply to one request, or nil when the Python side cannot be started or went away.
    /// The next call starts it again.
    func call(_ op: String, _ args: [String: Any] = [:]) async -> Data? {
        await withCheckedContinuation { done in
            queue.async { done.resume(returning: self.exchange(op, args)) }
        }
    }

    private func exchange(_ op: String, _ args: [String: Any]) -> Data? {
        var message = args
        message["op"] = op
        guard start(), var line = try? JSONSerialization.data(withJSONObject: message) else { return nil }
        line.append(10)
        do { try input?.write(contentsOf: line) } catch { return stop() }
        return read() ?? stop()
    }

    private func start() -> Bool {
        if let child, child.isRunning { return true }
        guard let (process, _) = Launch.python("admin_args") else { return false }
        let to = Pipe(), from = Pipe()
        process.standardInput = to
        process.standardOutput = from
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return false }
        child = process
        input = to.fileHandleForWriting
        output = from.fileHandleForReading
        buffer = Data()
        return true
    }

    private func stop() -> Data? {
        child?.terminate()
        child = nil
        return nil
    }

    private func read() -> Data? {
        guard let fd = output?.fileDescriptor else { return nil }
        var chunk = [UInt8](repeating: 0, count: 65536)
        while true {
            if let end = buffer.firstIndex(of: 10) {
                let line = buffer.subdata(in: buffer.startIndex..<end)
                buffer.removeSubrange(buffer.startIndex...end)
                return line
            }
            let n = Foundation.read(fd, &chunk, chunk.count)
            if n < 0 && errno == EINTR { continue }
            if n <= 0 { return nil }
            buffer.append(contentsOf: chunk[0..<n])
        }
    }
}
