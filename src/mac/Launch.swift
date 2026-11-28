// How this version starts its Python programs: versions/<tag>/engine.json beside the shared files
// (MACOS.md §4.6; the form is src/broker/support.h). Used by the input program and the settings window.
import Foundation

enum Launch {
    static var config: URL {
        let tag = Bundle.main.object(forInfoDictionaryKey: "YuragiTag") as? String ?? "dev"
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/yuragi-ime/versions/\(tag)/engine.json")
    }

    /// A Python process of this version, not started: the engine (`args`) or the settings window's
    /// work (`admin_args`). Also the arguments it is given.
    static func python(_ key: String) -> (Process, [String])? {
        guard let data = try? Data(contentsOf: config),
              let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let python = config["python"] as? String, let app = config["app"] as? String,
              let args = config[key] as? [String] else { return nil }
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
        return (child, args)
    }
}
