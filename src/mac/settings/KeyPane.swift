// The key editor: the table of keys by phase, the selected key's commands, and picking a key by pressing it.
// Nothing is written until 保存.
import SwiftUI

struct KeyPane: View {
    @EnvironmentObject private var model: Model
    @State private var selection: KeyRow.ID?
    @State private var pressing = false
    @State private var renaming = false
    @State private var showingNotes = false

    var body: some View {
        VStack(spacing: 0) {
            if let keys = model.keys {
                header(keys)
                Divider()
                ScrollViewReader { scroll in
                    table(keys)
                        .task(id: selection) {
                            if let selection { scroll.scrollTo(selection) }
                            await model.loadKeys(selected: selection)
                        }
                }
                Divider()
                if let detail = model.detail, detail.key == selection {
                    KeyDetailView(detail: detail)
                    Divider()
                }
                footer(keys)
            } else {
                ProgressView()
            }
        }
        .task { if model.keys == nil { await model.loadKeys(selected: nil) } }
        .sheet(isPresented: $pressing) {
            KeyPress { key in
                Task {
                    await model.loadKeys(selected: key)
                    selection = key
                }
            }
        }
        .sheet(isPresented: $renaming) {
            RenameKeys(name: model.keys?.name ?? "") { name in
                Task { await model.keyAct("key_rename", ["name": name], selected: selection) }
            }
        }
        .sheet(isPresented: $showingNotes) { KeyNotes(notes: model.keys?.notes ?? []) }
    }

    private func header(_ keys: KeyTable) -> some View {
        HStack(spacing: 12) {
            Picker("キー設定", selection: Binding(
                get: { keys.selected },
                set: { index in Task { await model.keyAct("key_preset", ["index": index], selected: selection) } }
            )) {
                ForEach(Array(keys.presets.enumerated()), id: \.offset) { index, label in Text(label).tag(index) }
            }
            .fixedSize()
            if keys.custom { Button("名前を変更…") { renaming = true } }
            Spacer()
            if !keys.notes.isEmpty { Button("読み込みの記録（\(keys.notes.count)）") { showingNotes = true } }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private func table(_ keys: KeyTable) -> some View {
        Table(keys.rows, selection: $selection) {
            TableColumn("キー") { Text($0.key).fontWeight(.medium) }.width(min: 80, ideal: 120)
            TableColumn(title(keys, 0)) { cell($0, 0) }.width(min: 60, ideal: 96)
            TableColumn(title(keys, 1)) { cell($0, 1) }.width(min: 60, ideal: 96)
            TableColumn(title(keys, 2)) { cell($0, 2) }.width(min: 60, ideal: 96)
            TableColumn(title(keys, 3)) { cell($0, 3) }.width(min: 60, ideal: 96)
            TableColumn(title(keys, 4)) { cell($0, 4) }.width(min: 60, ideal: 96)
            TableColumn(title(keys, 5)) { cell($0, 5) }.width(min: 60, ideal: 96)
            TableColumn(title(keys, 6)) { cell($0, 6) }.width(min: 60, ideal: 96)
            TableColumn(title(keys, 7)) { cell($0, 7) }.width(min: 60, ideal: 96)
        }
    }

    private func title(_ keys: KeyTable, _ index: Int) -> String {
        index < keys.phases.count ? keys.phases[index] : ""
    }

    @ViewBuilder
    private func cell(_ row: KeyRow, _ index: Int) -> some View {
        let text = index < row.cells.count ? row.cells[index] : ""
        if text == "–" {
            Text(text).foregroundStyle(.tertiary)
        } else {
            Text(text).foregroundStyle(text.hasSuffix("）") ? .secondary : .primary).lineLimit(1).help(text)
        }
    }

    private func footer(_ keys: KeyTable) -> some View {
        HStack(spacing: 12) {
            Button("キーを押して選ぶ…") { pressing = true }
                .help("押したキーの行を選びます。表に無いキーは行を足します。")
            Spacer()
            if keys.dirty { Text("保存していない変更があります").font(.callout).foregroundStyle(.secondary) }
            Button("元に戻す") { Task { await model.keyAct("key_revert", selected: selection) } }.disabled(!keys.dirty)
            Button("保存") { Task { await model.keyAct("key_save", selected: selection) } }
                .keyboardShortcut("s")
                .buttonStyle(.borderedProminent)
                .disabled(!keys.dirty)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }
}

/// What the selected key does in each phase.
struct KeyDetailView: View {
    @EnvironmentObject private var model: Model
    let detail: KeyDetail

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(detail.key).font(.headline)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 12, alignment: .leading), count: 4),
                      alignment: .leading, spacing: 8) {
                ForEach(detail.phases) { phase in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(phase.label).font(.caption).foregroundStyle(.secondary)
                        if phase.allowed {
                            Picker(phase.label, selection: Binding(
                                get: { phase.picked },
                                set: { choice in
                                    Task {
                                        await model.keyAct("key_assign", ["key": detail.key, "phase": phase.id, "choice": choice],
                                                           selected: detail.key)
                                    }
                                }
                            )) {
                                ForEach(Array(phase.choices.enumerated()), id: \.element) { index, choice in
                                    // "As the preset", when picked, says what that is here.
                                    Text(index == 0 && phase.picked == choice && phase.now != "–"
                                         ? "\(choice)（\(phase.now)）" : choice).tag(choice)
                                    if index == 1 { Divider() }
                                }
                            }
                            .labelsHidden()
                        } else {
                            Text("割り当てられません").foregroundStyle(.tertiary).frame(height: 22)
                        }
                    }
                }
            }
        }
        .padding(12)
    }
}

/// Waits for a key: its row is selected, or added when the table has none.
struct KeyPress: View {
    @EnvironmentObject private var model: Model
    @Environment(\.dismiss) private var dismiss
    let picked: (String) -> Void
    @State private var monitor: Any?
    @State private var message = ""

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "keyboard").font(.system(size: 40)).foregroundStyle(.secondary)
            Text("キーを押してください").font(.headline)
            Text("Shift・Control・Option と組み合わせられます。")
                .font(.callout).foregroundStyle(.secondary)
            Text(message).font(.callout).foregroundStyle(.red).frame(minHeight: 18)
            Button("キャンセル") { dismiss() }
        }
        .padding(24)
        .frame(width: 340)
        .onAppear {
            monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
                if event.modifierFlags.contains(.command) { return event }  // Command+Q and the like
                guard let vk = Keys.vk[event.keyCode] else {
                    message = "このキーは割り当てに使えません"
                    return nil
                }
                let mods = Keys.mods(event.modifierFlags)
                Task {
                    let pressed = await model.press(vk, mods)
                    if pressed.ok, let key = pressed.key {
                        picked(key)
                        dismiss()
                    } else {
                        message = pressed.message
                    }
                }
                return nil
            }
        }
        .onDisappear {
            if let monitor { NSEvent.removeMonitor(monitor) }
            monitor = nil
        }
    }
}

struct RenameKeys: View {
    @Environment(\.dismiss) private var dismiss
    @State var name: String
    let done: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("キー設定の名前を変更").font(.headline)
            TextField("表示名", text: $name, prompt: Text("ユーザー定義"))
            HStack {
                Spacer()
                Button("キャンセル", role: .cancel) { dismiss() }.keyboardShortcut(.cancelAction)
                Button("変更") { done(name); dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 340)
    }
}

struct KeyNotes: View {
    @Environment(\.dismiss) private var dismiss
    let notes: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("キー設定の読み込みの記録").font(.headline)
            ScrollView {
                Text(notes.joined(separator: "\n")).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 180)
            HStack {
                Spacer()
                Button("閉じる") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 480)
    }
}
