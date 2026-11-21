// Distaph.app — a native front door for the Distaph launcher.
//
// It does three small things and quits:
//   1. finds the Distaph install it belongs to (the folder it sits in),
//   2. finds your library — or asks you to choose or create one,
//   3. opens Terminal running the Distaph menu against that library.
//
// Hold Option while opening Distaph to choose a different library.
// The choice is saved to ~/.config/distaph/library, the same file the
// `distaph` command reads, so the app and the command line always agree.

import AppKit

enum Library {
    static let configName = "distaph.toml"
    static let pointer = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".config/distaph/library")
    static let defaultLocation = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Distaph")

    /// The library the command line would use: the saved choice, else ~/Distaph.
    static func current() -> URL {
        if let text = try? String(contentsOf: pointer, encoding: .utf8) {
            let path = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !path.isEmpty {
                return URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
            }
        }
        return defaultLocation
    }

    static func isLibrary(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: url.appendingPathComponent(configName).path)
    }

    static func remember(_ url: URL) throws {
        try FileManager.default.createDirectory(
            at: pointer.deletingLastPathComponent(), withIntermediateDirectories: true)
        try (url.path + "\n").write(to: pointer, atomically: true, encoding: .utf8)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var appRoot: URL!

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.activate(ignoringOtherApps: true)

        guard let root = findAppRoot() else {
            stop("Distaph can't find its files",
                 "Keep Distaph.app inside the Distaph folder (for example /Applications/Distaph), "
                 + "next to its bin and scripts folders.")
            return
        }
        appRoot = root

        let wantsToChoose = NSEvent.modifierFlags.contains(.option)
        let library = Library.current()
        if !wantsToChoose && Library.isLibrary(library) {
            open(library: library, initialize: false)
        } else {
            askForLibrary(current: Library.isLibrary(library) ? library : nil)
        }
    }

    /// The Distaph install: the folder containing this app, or /Applications/Distaph
    /// (so a copy run straight from Xcode's build folder still works).
    private func findAppRoot() -> URL? {
        let candidates = [
            Bundle.main.bundleURL.deletingLastPathComponent(),
            URL(fileURLWithPath: "/Applications/Distaph"),
        ]
        return candidates.first {
            FileManager.default.isExecutableFile(atPath: $0.appendingPathComponent("bin/distaph").path)
        }
    }

    // MARK: Choosing a library

    private func askForLibrary(current: URL?) {
        let alert = NSAlert()
        alert.messageText = current == nil ? "Choose your Distaph library" : "Use a different library?"
        alert.informativeText = current.map { "Distaph is using \($0.path)." }
            ?? "Your library is the folder where Distaph keeps your vault, transcripts and cuts. "
             + "Your footage stays on its own drive."
        alert.addButton(withTitle: "Choose Folder…")
        alert.addButton(withTitle: "Create New…")
        if let current { alert.addButton(withTitle: "Keep \(current.lastPathComponent)") }
        alert.addButton(withTitle: "Quit")

        switch alert.runModal() {
        case .alertFirstButtonReturn: chooseExisting()
        case .alertSecondButtonReturn: createNew()
        case .alertThirdButtonReturn where current != nil: open(library: current!, initialize: false)
        default: NSApp.terminate(nil)
        }
    }

    private func chooseExisting() {
        let panel = NSOpenPanel()
        panel.message = "Choose your Distaph library folder."
        panel.prompt = "Use This Folder"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser
        guard panel.runModal() == .OK, let url = panel.url else { return askForLibrary(current: nil) }

        if Library.isLibrary(url) {
            remember(url)
            open(library: url, initialize: false)
            return
        }
        let alert = NSAlert()
        alert.messageText = "“\(url.lastPathComponent)” isn't a Distaph library yet"
        alert.informativeText = "Distaph can set it up here: a settings file, an empty vault, "
            + "and a git repository. Nothing already in the folder is changed."
        alert.addButton(withTitle: "Set It Up")
        alert.addButton(withTitle: "Choose Another…")
        alert.addButton(withTitle: "Quit")
        switch alert.runModal() {
        case .alertFirstButtonReturn: open(library: url, initialize: true)
        case .alertSecondButtonReturn: chooseExisting()
        default: NSApp.terminate(nil)
        }
    }

    private func createNew() {
        let panel = NSSavePanel()
        panel.message = "Choose a name and place for your new library."
        panel.prompt = "Create Library"
        panel.nameFieldStringValue = "Distaph"
        panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser
        panel.canCreateDirectories = true
        guard panel.runModal() == .OK, let url = panel.url else { return askForLibrary(current: nil) }
        open(library: url, initialize: true)
    }

    private func remember(_ url: URL) {
        do { try Library.remember(url) } catch {
            stop("Distaph couldn't save your library choice", error.localizedDescription)
        }
    }

    // MARK: Opening Terminal

    /// Writes a one-shot .command script and opens it with your default handler
    /// for .command files (Terminal, unless you've changed it). No Apple Events
    /// permission needed. The script deletes itself when it runs.
    private func open(library: URL, initialize: Bool) {
        let distaph = appRoot.appendingPathComponent("bin/distaph").path
        var lines = [
            "#!/bin/zsh -il",
            "rm -f -- \"$0\"",
            "export DISTAPH_LIBRARY=\(q(library.path))",
            "clear",
            "if ! command -v uv >/dev/null; then",
            "  echo 'Distaph needs uv to run. Install it with:'",
            "  echo '  curl -LsSf https://astral.sh/uv/install.sh | sh'",
            "  echo 'then open Distaph again.'",
            "  exit 1",
            "fi",
        ]
        if initialize {
            lines += [
                "\(q(distaph)) init \(q(library.path)) || exit 1",
                "echo",
                "echo 'Opening your settings file — point it at your footage drive, save, then come back here.'",
                "open -t \(q(library.appendingPathComponent(Library.configName).path))",
                "echo",
                "read -k1 '?Press any key to open the Distaph menu…'",
            ]
        }
        lines.append("exec \(q(distaph))")

        let script = FileManager.default.temporaryDirectory
            .appendingPathComponent("distaph-\(UUID().uuidString).command")
        do {
            try (lines.joined(separator: "\n") + "\n").write(to: script, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: script.path)
        } catch {
            stop("Distaph couldn't start", error.localizedDescription)
            return
        }

        NSWorkspace.shared.open(script, configuration: NSWorkspace.OpenConfiguration()) { _, error in
            let message = error?.localizedDescription
            Task { @MainActor in
                if let message {
                    self.stop("Distaph couldn't open Terminal", message)
                } else {
                    NSApp.terminate(nil)
                }
            }
        }
    }

    /// Single-quote for zsh.
    private func q(_ s: String) -> String {
        "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    private func stop(_ title: String, _ detail: String) {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = title
        alert.informativeText = detail
        alert.addButton(withTitle: "Quit")
        alert.runModal()
        NSApp.terminate(nil)
    }
}

@main
enum DistaphApp {
    @MainActor
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.run()
    }
}
