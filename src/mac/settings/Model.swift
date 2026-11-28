// What the settings window shows, as the Python side gives it (yuragi/ime/admin_service.py).
import SwiftUI

struct Outcome: Decodable {
    var ok: Bool
    var message: String
}

struct Word: Decodable, Identifiable, Hashable {
    var reading: String
    var surface: String
    var pos: String
    var cost: Int
    var id: String { reading + "\t" + surface }
}

struct Learned: Decodable, Identifiable, Hashable {
    var reading: String
    var surface: String
    var when: String
    var word: Bool
    var id: String { reading + "\t" + surface }
}

struct Setting: Decodable, Identifiable {
    var name: String
    var label: String
    var help: String
    var value: String
    var choices: [String]
    var id: String { name }
}

struct Everything: Decodable {
    var words: [Word]
    var learned: [Learned]
    var counts: String
    var settings: [Setting]
    var pos: [String]
    var default_cost: Int
}

struct Status: Decodable {
    var engine: String
    var rows: [[String]]
}

struct KeyRow: Decodable, Identifiable {
    var key: String
    var cells: [String]
    var id: String { key }
}

struct KeyTable: Decodable {
    var presets: [String]
    var selected: Int
    var custom: Bool
    var name: String
    var notes: [String]
    var phases: [String]
    var rows: [KeyRow]
    var dirty: Bool
}

struct PhaseChoice: Decodable, Identifiable {
    var id: String
    var label: String
    var allowed: Bool
    var picked: String
    var now: String
    var choices: [String]
}

struct KeyDetail: Decodable {
    var key: String
    var phases: [PhaseChoice]
}

struct Pressed: Decodable {
    var ok: Bool
    var message: String
    var key: String?
}

@MainActor
final class Model: ObservableObject {
    @Published var words: [Word] = []
    @Published var learned: [Learned] = []
    @Published var counts = ""
    @Published var settings: [Setting] = []
    @Published var pos: [String] = []
    @Published var defaultCost = 0
    @Published var status: Status?
    @Published var keys: KeyTable?
    @Published var detail: KeyDetail?
    /// The last action's result, shown at the bottom of the window.
    @Published var notice: Outcome?
    /// The Python side could not be reached.
    @Published var unavailable = false

    private let service = Service()

    private func get<T: Decodable>(_ op: String, _ args: [String: Any] = [:]) async -> T? {
        let data = await service.call(op, args)
        unavailable = data == nil
        guard let data else { return nil }
        if let value = try? JSONDecoder().decode(T.self, from: data) { return value }
        // A request that failed answers with why.
        if let outcome = try? JSONDecoder().decode(Outcome.self, from: data) { notice = outcome }
        return nil
    }

    func reload() async {
        guard let all: Everything = await get("state") else { return }
        words = all.words
        learned = all.learned
        counts = all.counts
        settings = all.settings
        pos = all.pos
        defaultCost = all.default_cost
    }

    func loadStatus() async {
        if let now: Status = await get("status") { status = now }
    }

    /// A change: its result goes to the bottom of the window (unless `quiet`), and the lists are read again.
    @discardableResult
    func act(_ op: String, _ args: [String: Any] = [:], quiet: Bool = false) async -> Outcome {
        let outcome: Outcome = await get(op, args) ?? Outcome(ok: false, message: "ゆらぎの設定を読み書きできません")
        if !quiet || !outcome.ok { notice = outcome }
        await reload()
        return outcome
    }

    // -- keys ------------------------------------------------------------------------------

    func loadKeys(selected key: String?) async {
        if let table: KeyTable = await get("keys") { keys = table }
        if let key, keys?.rows.contains(where: { $0.key == key }) == true {
            detail = await get("key_detail", ["key": key])
        } else {
            detail = nil
        }
    }

    func keyAct(_ op: String, _ args: [String: Any] = [:], selected key: String?) async {
        let outcome: Outcome = await get(op, args) ?? Outcome(ok: false, message: "ゆらぎの設定を読み書きできません")
        notice = outcome
        await loadKeys(selected: key)
    }

    func press(_ vk: UInt32, _ mods: [String]) async -> Pressed {
        await get("key_press", ["vk": Int(vk), "mods": mods])
            ?? Pressed(ok: false, message: "ゆらぎの設定を読み書きできません", key: nil)
    }
}
