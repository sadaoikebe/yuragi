// The panes for settings, registered words, learning and status.
import SwiftUI

struct GeneralPane: View {
    @EnvironmentObject private var model: Model

    var body: some View {
        Form {
            ForEach(model.settings) { setting in
                Picker(selection: Binding(
                    get: { setting.value },
                    set: { value in Task { await model.act("set_setting", ["name": setting.name, "value": value]) } }
                )) {
                    ForEach(setting.choices, id: \.self) { Text($0) }
                } label: {
                    Text(setting.label)
                    Text(setting.help)
                }
            }
        }
        .formStyle(.grouped)
    }
}

struct WordsPane: View {
    @EnvironmentObject private var model: Model
    @State private var selection: Word.ID?
    @State private var adding = false
    @State private var removing: Word?

    private var selected: Word? { model.words.first { $0.id == selection } }

    var body: some View {
        VStack(spacing: 0) {
            Table(model.words, selection: $selection) {
                TableColumn("読み", value: \.reading)
                TableColumn("単語", value: \.surface)
                TableColumn("品詞", value: \.pos).width(min: 70, ideal: 100)
                TableColumn("コスト") { Text(String($0.cost)).monospacedDigit() }.width(min: 50, ideal: 70)
            }
            .overlay {
                if model.words.isEmpty {
                    Text("登録した単語はありません。＋ で登録します。").foregroundStyle(.secondary)
                }
            }
            Divider()
            HStack(spacing: 12) {
                Button { adding = true } label: { Image(systemName: "plus") }.help("単語を登録")
                Button { removing = selected } label: { Image(systemName: "minus") }
                    .disabled(selected == nil).help("選んだ単語を削除")
                Spacer()
                Text("\(model.words.count) 件").foregroundStyle(.secondary)
            }
            .buttonStyle(.borderless)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .sheet(isPresented: $adding) { AddWord() }
        .confirmationDialog("\(removing?.reading ?? "") → \(removing?.surface ?? "") を削除しますか？",
                            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } })) {
            Button("削除", role: .destructive) {
                if let word = removing {
                    Task { await model.act("remove_word", ["reading": word.reading, "surface": word.surface]) }
                }
            }
        }
    }
}

struct AddWord: View {
    @EnvironmentObject private var model: Model
    @Environment(\.dismiss) private var dismiss
    @State private var reading = ""
    @State private var surface = ""
    @State private var pos = "名詞"
    @State private var cost = ""
    @State private var error = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("単語を登録").font(.headline)
            Form {
                TextField("読み", text: $reading)
                TextField("単語", text: $surface)
                Picker("品詞", selection: $pos) {
                    ForEach(model.pos, id: \.self) { Text($0) }
                }
                TextField("コスト", text: $cost, prompt: Text(String(model.defaultCost)))
            }
            Text("コストは小さいほど上位に出ます。").font(.callout).foregroundStyle(.secondary)
            if !error.isEmpty { Text(error).font(.callout).foregroundStyle(.red) }
            HStack {
                Spacer()
                Button("キャンセル", role: .cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Button("登録") {
                    Task {
                        let outcome = await model.act("add_word", ["reading": reading, "surface": surface,
                                                                   "pos": pos, "cost": cost])
                        if outcome.ok { dismiss() } else { error = outcome.message; model.notice = nil }
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(reading.isEmpty || surface.isEmpty)
            }
        }
        .padding(20)
        .frame(width: 380)
    }
}

struct LearningPane: View {
    @EnvironmentObject private var model: Model
    @State private var selection: Learned.ID?
    @State private var query = ""
    @State private var forgetting: Learned?

    private var shown: [Learned] {
        let text = query.trimmingCharacters(in: .whitespaces)
        return text.isEmpty ? model.learned : model.learned.filter { $0.reading.contains(text) || $0.surface.contains(text) }
    }
    private var selected: Learned? { model.learned.first { $0.id == selection } }

    var body: some View {
        VStack(spacing: 0) {
            Table(shown, selection: $selection) {
                TableColumn("読み", value: \.reading)
                TableColumn("変換", value: \.surface)
                TableColumn("最後の確定") { Text($0.when).monospacedDigit() }.width(min: 110, ideal: 130)
                TableColumn("単語として覚えた") { row in
                    if row.word { Image(systemName: "checkmark") }
                }.width(min: 60, ideal: 110)
            }
            .overlay {
                if shown.isEmpty {
                    Text(model.learned.isEmpty ? "学習した変換はまだありません。" : "見つかりません。").foregroundStyle(.secondary)
                }
            }
            Divider()
            HStack(spacing: 12) {
                Button("忘れる") { forgetting = selected }.disabled(selected == nil)
                Menu("単語登録") {
                    ForEach(model.pos, id: \.self) { pos in
                        Button(pos) {
                            if let pair = selected {
                                Task { await model.act("promote", ["reading": pair.reading, "surface": pair.surface, "pos": pos]) }
                            }
                        }
                    }
                }
                .fixedSize()
                .disabled(selected == nil)
                .help("選んだ変換を、品詞を選んで単語登録します。学習履歴を消しても残ります。")
                Spacer()
                Text(model.counts).font(.callout).foregroundStyle(.secondary).lineLimit(1)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .searchable(text: $query, prompt: "読みか変換で検索")
        .confirmationDialog("\(forgetting?.reading ?? "") → \(forgetting?.surface ?? "") の学習を忘れますか？",
                            isPresented: Binding(get: { forgetting != nil }, set: { if !$0 { forgetting = nil } })) {
            Button("忘れる", role: .destructive) {
                if let pair = forgetting {
                    Task { await model.act("forget", ["reading": pair.reading, "surface": pair.surface]) }
                }
            }
        }
    }
}

struct StatusPane: View {
    @EnvironmentObject private var model: Model

    private var light: Color {
        switch model.status?.engine {
        case "ready": return .green
        case "starting": return .orange
        case "down": return .red
        default: return .gray
        }
    }

    var body: some View {
        Form {
            Section {
                ForEach(Array((model.status?.rows ?? []).enumerated()), id: \.offset) { index, row in
                    LabeledContent(row.first ?? "") {
                        HStack(spacing: 6) {
                            if index == 0 { Circle().fill(light).frame(width: 9, height: 9) }
                            Text(row.last ?? "").textSelection(.enabled).multilineTextAlignment(.trailing)
                        }
                    }
                }
            }
            Section {
                HStack {
                    Button("変換エンジンを再起動") { Task { await model.act("restart"); await model.loadStatus() } }
                    Button("記録のフォルダを開く") {
                        NSWorkspace.shared.open(FileManager.default.homeDirectoryForCurrentUser
                            .appendingPathComponent("Library/Logs/yuragi-ime"))
                    }
                    Spacer()
                }
            }
        }
        .formStyle(.grouped)
        .task {
            // Shown while it changes: a restart takes a moment.
            while !Task.isCancelled {
                await model.loadStatus()
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
    }
}
