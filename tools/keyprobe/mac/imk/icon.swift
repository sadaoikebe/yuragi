// icon <text> <out.tiff>: a 16pt menu-bar icon (1x and 2x) with one character.
import Cocoa
let text = CommandLine.arguments[1]
let out = CommandLine.arguments[2]
var reps: [NSBitmapImageRep] = []
for scale in [1, 2] {
    let px = 16 * scale
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8, samplesPerPixel: 4,
                               hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: 16, height: 16)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.boldSystemFont(ofSize: 13), .foregroundColor: NSColor.black]
    let s = NSAttributedString(string: text, attributes: attrs)
    let size = s.size()
    s.draw(at: NSPoint(x: (16 - size.width) / 2, y: (16 - size.height) / 2))
    NSGraphicsContext.restoreGraphicsState()
    reps.append(rep)
}
let data = NSBitmapImageRep.representationOfImageReps(in: reps, using: .tiff, properties: [:])!
try! data.write(to: URL(fileURLWithPath: out))
