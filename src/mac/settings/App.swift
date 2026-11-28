// The settings window (MACOS.md §7.3): its own application inside the input program's bundle,
// opened from the input menu. The work is Python's (Service.swift); this lays it out.
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

@main
struct SettingsApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var model = Model()

    init() { signal(SIGPIPE, SIG_IGN) }  // the Python side may be gone when written to

    var body: some Scene {
        Window("ゆらぎ 設定", id: "main") {
            Root().environmentObject(model)
        }
        .defaultSize(width: 940, height: 620)
    }
}

enum Pane: String, CaseIterable, Identifiable {
    case general, words, learning, keys, status
    var id: Self { self }
    var title: String {
        switch self {
        case .general: return "一般"
        case .words: return "単語登録"
        case .learning: return "学習"
        case .keys: return "キー"
        case .status: return "状態"
        }
    }
    var symbol: String {
        switch self {
        case .general: return "gearshape"
        case .words: return "character.book.closed"
        case .learning: return "clock.arrow.circlepath"
        case .keys: return "keyboard"
        case .status: return "waveform.path.ecg"
        }
    }
}

struct Root: View {
    @EnvironmentObject private var model: Model
    /// `-pane words` on the command line opens on that pane (the input program's 単語登録を開く).
    @State private var pane: Pane? = Pane(rawValue: UserDefaults.standard.string(forKey: "pane") ?? "") ?? .general

    var body: some View {
        NavigationSplitView {
            List(Pane.allCases, selection: $pane) { item in
                Label(item.title, systemImage: item.symbol)
            }
            .navigationSplitViewColumnWidth(min: 150, ideal: 170, max: 220)
        } detail: {
            Group {
                if model.unavailable {
                    Unavailable()
                } else {
                    switch pane ?? .general {
                    case .general: GeneralPane()
                    case .words: WordsPane()
                    case .learning: LearningPane()
                    case .keys: KeyPane()
                    case .status: StatusPane()
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .navigationTitle((pane ?? .general).title)
            .safeAreaInset(edge: .bottom, spacing: 0) { NoticeBar() }
        }
        .frame(minWidth: 760, minHeight: 460)
        .task { await model.reload() }
        .task(id: pane) { model.notice = nil }  // a message belongs to the pane it came from
        // The engine writes these files too (learning): show them as they are now.
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            Task { await model.reload() }
        }
    }
}

struct NoticeBar: View {
    @EnvironmentObject private var model: Model

    var body: some View {
        if let notice = model.notice, !notice.message.isEmpty {
            HStack(spacing: 6) {
                Image(systemName: notice.ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                    .foregroundStyle(notice.ok ? Color.green : Color.red)
                Text(notice.message).textSelection(.enabled)
                Spacer()
            }
            .font(.callout)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.bar)
        }
    }
}

struct Unavailable: View {
    @EnvironmentObject private var model: Model

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(.secondary)
            Text("ゆらぎの設定を読み書きできません").font(.headline)
            Text("起動のしかたを書いたファイルを使えません。入れ直してください。\n\(Launch.config.path)")
                .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center).textSelection(.enabled)
            Button("もう一度試す") { Task { await model.reload() } }
        }
        .padding(30)
    }
}
