// The line for the settings window (DESIGN「通信」; yuragi/ime/broker_client.py): a Unix domain
// socket only this user can open. A connection talks to the watcher as an input field does
// (hello, retry, reload_keymap). Everything runs on the main thread.
import Foundation

final class Peers {
    static let shared = Peers()
    static let path = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/yuragi-ime/broker.sock").path

    private struct Peer {
        let fd: Int32
        let source: DispatchSourceRead
        var rest = Data()
    }
    private var listener: DispatchSourceRead?
    private var peers: [Int: Peer] = [:]

    func start() {
        guard listener == nil else { return }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(Self.path.utf8)
        let capacity = MemoryLayout.size(ofValue: address.sun_path)
        guard bytes.count < capacity else { Log.write("the socket path is too long"); return }
        withUnsafeMutableBytes(of: &address.sun_path) { $0.copyBytes(from: bytes) }
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return }
        unlink(Self.path)  // a socket left by a process that ended
        let old = umask(0o177)
        let bound = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
        }
        umask(old)
        guard bound == 0, listen(fd, 4) == 0 else {
            Log.write("no socket for the settings window (errno \(errno))")
            Darwin.close(fd)
            return
        }
        _ = fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK)
        let source = DispatchSource.makeReadSource(fileDescriptor: fd, queue: .main)
        source.setEventHandler { [weak self] in self?.accept(fd) }
        source.resume()
        listener = source
    }

    private func accept(_ listening: Int32) {
        let fd = Darwin.accept(listening, nil, nil)
        guard fd >= 0 else { return }
        _ = fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK)
        var on: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
        let id = Engine.shared.peerConnected()
        let source = DispatchSource.makeReadSource(fileDescriptor: fd, queue: .main)
        source.setEventHandler { [weak self] in self?.read(id) }
        source.setCancelHandler { Darwin.close(fd) }
        peers[id] = Peer(fd: fd, source: source)
        source.resume()
    }

    private func read(_ id: Int) {
        guard var peer = peers[id] else { return }
        var buffer = [UInt8](repeating: 0, count: 4096)
        let count = recv(peer.fd, &buffer, buffer.count, 0)
        if count < 0 && errno == EAGAIN { return }
        guard count > 0, peer.rest.count < 1 << 16 else { close(id); return }
        peer.rest.append(contentsOf: buffer[0..<count])
        var lines: [String] = []
        while let end = peer.rest.firstIndex(of: 0x0A) {
            lines.append(String(decoding: peer.rest[peer.rest.startIndex..<end], as: UTF8.self))
            peer.rest.removeSubrange(peer.rest.startIndex...end)
        }
        peers[id] = peer
        for line in lines { Engine.shared.peerLine(id, line) }
    }

    func write(_ id: Int, _ line: String) {
        guard let peer = peers[id] else { return }
        var data = Data(line.utf8)
        data.append(0x0A)
        let sent = data.withUnsafeBytes { Darwin.send(peer.fd, $0.baseAddress, $0.count, 0) }
        if sent != data.count { DispatchQueue.main.async { self.close(id) } }  // it reads nothing, or is gone
    }

    private func close(_ id: Int) {
        guard let peer = peers.removeValue(forKey: id) else { return }
        peer.source.cancel()
        Engine.shared.peerClosed(id)
    }
}
