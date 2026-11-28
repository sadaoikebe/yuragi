// The candidate window (DESIGN「候補窓の描画」, docs/MACOS.md §7.3): a panel under the text being
// converted that takes neither the focus nor the mouse. Colours and fonts are the system's, so
// light and dark, the accent colour and larger text follow the OS.
import Cocoa

struct CandidateList: Equatable {
    var items: [String] = []
    var notes: [String] = []  // beside each item; empty: none
    var selected = -1
    var page = 0  // from 0
    var hasNextPage = false
    /// Predictions offered without the focus: no numbers, no selected row, "Tab で選択" below.
    var suggesting = false
    /// One line of words for the user (DESIGN「小さな表示」): drawn like a prediction, with no footer.
    var notice = false

    var footer: String {
        if notice { return "" }
        if suggesting { return "Tab で選択" }
        if page > 0 || hasNextPage { return "\(page + 1)" + (hasNextPage ? " ▾" : "") }
        return ""
    }
}

final class CandidateView: NSView {
    var list = CandidateList() { didSet { needsDisplay = true } }

    private let inset: CGFloat = 5, padding: CGFloat = 10, row: CGFloat = 28
    private let numberColumn: CGFloat = 20, noteGap: CGFloat = 16, footerHeight: CGFloat = 22
    private let minWidth: CGFloat = 140, maxWidth: CGFloat = 520
    private var textFont: NSFont { .systemFont(ofSize: NSFont.systemFontSize + (list.notice ? 0 : 3)) }
    private var smallFont: NSFont { .systemFont(ofSize: NSFont.smallSystemFontSize) }

    override var isFlipped: Bool { true }

    private func width(_ text: String, _ font: NSFont) -> CGFloat {
        ceil((text as NSString).size(withAttributes: [.font: font]).width)
    }
    private var plain: Bool { list.suggesting || list.notice }
    private var textLeft: CGFloat { inset + padding + (plain ? 0 : numberColumn) }

    /// The size that shows every row, up to maxWidth (longer text is cut with an ellipsis).
    var fittingSize2: NSSize {
        let text = list.items.map { width($0, textFont) }.max() ?? 0
        let note = list.notes.map { width($0, smallFont) }.max() ?? 0
        let footer = list.footer.isEmpty ? 0 : width(list.footer, smallFont) + 2 * (inset + padding)
        let wanted = textLeft + text + (note > 0 ? noteGap + note : 0) + inset + padding
        return NSSize(width: min(maxWidth, max(minWidth, wanted, footer)),
                      height: 2 * inset + CGFloat(list.items.count) * row + (list.footer.isEmpty ? 0 : footerHeight))
    }

    override func draw(_ dirtyRect: NSRect) {
        let truncating = NSMutableParagraphStyle()
        truncating.lineBreakMode = .byTruncatingTail
        let right = NSMutableParagraphStyle()
        right.alignment = .right
        for (index, item) in list.items.enumerated() {
            let top = inset + CGFloat(index) * row
            let selected = index == list.selected && !plain
            if selected {
                NSColor.labelColor.withAlphaComponent(0.10).setFill()
                NSBezierPath(roundedRect: NSRect(x: inset, y: top, width: bounds.width - 2 * inset, height: row),
                             xRadius: 6, yRadius: 6).fill()
                NSColor.controlAccentColor.setFill()
                NSBezierPath(roundedRect: NSRect(x: inset, y: top + 6, width: 3, height: row - 12),
                             xRadius: 1.5, yRadius: 1.5).fill()
            }
            if !plain {
                ("\(index + 1)" as NSString).draw(
                    in: NSRect(x: inset + padding - 2, y: top + (row - smallFont.pointSize) / 2 - 2, width: numberColumn - 6, height: row),
                    withAttributes: [.font: smallFont, .foregroundColor: NSColor.secondaryLabelColor, .paragraphStyle: right])
            }
            let note = index < list.notes.count ? list.notes[index] : ""
            let noteWidth = note.isEmpty ? 0 : width(note, smallFont)
            let textRight = bounds.width - inset - padding - (noteWidth > 0 ? noteGap + noteWidth : 0)
            let lineHeight = ceil(textFont.ascender - textFont.descender)
            (item as NSString).draw(
                in: NSRect(x: textLeft, y: top + (row - lineHeight) / 2, width: max(0, textRight - textLeft), height: lineHeight),
                withAttributes: [.font: textFont, .foregroundColor: NSColor.labelColor, .paragraphStyle: truncating])
            if !note.isEmpty {
                (note as NSString).draw(
                    at: NSPoint(x: bounds.width - inset - padding - noteWidth, y: top + (row - smallFont.pointSize) / 2 - 2),
                    withAttributes: [.font: smallFont, .foregroundColor: NSColor.secondaryLabelColor])
            }
        }
        if !list.footer.isEmpty {
            let top = 2 * inset + CGFloat(list.items.count) * row
            NSColor.separatorColor.setFill()
            NSRect(x: inset + padding, y: top - inset / 2, width: bounds.width - 2 * (inset + padding), height: 1).fill()
            (list.footer as NSString).draw(
                in: NSRect(x: inset + padding, y: top + 2, width: bounds.width - 2 * (inset + padding), height: footerHeight),
                withAttributes: [.font: smallFont, .foregroundColor: NSColor.secondaryLabelColor, .paragraphStyle: right])
        }
    }
}

final class CandidateWindow {
    static let shared = CandidateWindow()
    private let panel: NSPanel
    private let view = CandidateView()
    private let gap: CGFloat = 4

    private init() {
        panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: true)
        panel.level = .popUpMenu
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.ignoresMouseEvents = true
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        let back = NSVisualEffectView()
        back.material = .popover
        back.state = .active
        back.wantsLayer = true
        back.layer?.cornerRadius = 8
        back.layer?.masksToBounds = true
        view.autoresizingMask = [.width, .height]
        back.addSubview(view)
        panel.contentView = back
    }

    /// Shows the list under the caret rectangle (screen coordinates), or above it when there is no room below.
    func show(_ list: CandidateList, at caret: NSRect) {
        noticeTimer?.cancel()
        noticeTimer = nil
        view.list = list
        let size = view.fittingSize2
        let screen = NSScreen.screens.first { $0.frame.contains(caret.origin) } ?? NSScreen.main
        let area = screen?.visibleFrame ?? NSRect(origin: .zero, size: size)
        var x = caret.minX
        var y = caret.minY - gap - size.height
        if y < area.minY { y = caret.maxY + gap }
        x = max(area.minX, min(x, area.maxX - size.width))
        panel.setFrame(NSRect(x: x, y: y, width: size.width, height: size.height), display: true)
        view.frame = NSRect(origin: .zero, size: size)
        panel.orderFrontRegardless()
    }

    func hide() {
        noticeTimer?.cancel()
        noticeTimer = nil
        panel.orderOut(nil)
    }

    private var noticeTimer: DispatchSourceTimer?

    /// DESIGN「小さな表示」: one line under the caret that goes by itself (NOTICE_SHOW_MS).
    func notice(_ text: String, at caret: NSRect) {
        show(CandidateList(items: [text], notice: true), at: caret)
        let source = DispatchSource.makeTimerSource(queue: .main)
        source.schedule(deadline: .now() + .milliseconds(4000))
        source.setEventHandler { [weak self] in self?.hide() }
        noticeTimer = source
        source.resume()
    }
}
