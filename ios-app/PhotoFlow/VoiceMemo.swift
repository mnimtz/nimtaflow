import SwiftUI
import AVFoundation

/// Records / plays / uploads a voice memo for a photo (iOS parity with the web).
@MainActor
final class VoiceMemoController: ObservableObject {
    @Published var recording = false
    @Published var busy = false
    private var recorder: AVAudioRecorder?
    private var player: AVAudioPlayer?
    private var fileURL: URL { FileManager.default.temporaryDirectory.appendingPathComponent("pf_voice_memo.m4a") }

    func startRecording() async -> Bool {
        let granted = await AVAudioApplication.requestRecordPermission()
        guard granted else { return false }
        do {
            let s = AVAudioSession.sharedInstance()
            try s.setCategory(.playAndRecord, mode: .default)
            try s.setActive(true)
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 44_100,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue,
            ]
            recorder = try AVAudioRecorder(url: fileURL, settings: settings)
            recorder?.record()
            recording = true
            return true
        } catch { return false }
    }

    func stopRecording() -> Data? {
        recorder?.stop(); recording = false
        try? AVAudioSession.sharedInstance().setActive(false)
        return try? Data(contentsOf: fileURL)
    }

    func play(_ data: Data) {
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            player = try AVAudioPlayer(data: data)
            player?.play()
        } catch {}
    }
}

struct VoiceMemoSection: View {
    let photoId: Int
    @State var hasNote: Bool
    @EnvironmentObject var api: APIClient
    @StateObject private var ctl = VoiceMemoController()
    @State private var errMsg: String?

    var body: some View {
        Section("🎤 Sprach-Memo") {
            if hasNote {
                Button {
                    Task {
                        if let d = try? await api.voiceNoteData(photoId) { ctl.play(d) }
                    }
                } label: { Label("Abspielen", systemImage: "play.circle") }
            }
            if ctl.recording {
                Button(role: .destructive) {
                    Task {
                        ctl.busy = true; defer { ctl.busy = false }
                        if let data = ctl.stopRecording() {
                            do { try await api.uploadVoiceNote(photoId, data: data); hasNote = true; errMsg = nil }
                            catch { errMsg = "Upload fehlgeschlagen." }
                        }
                    }
                } label: { Label("Aufnahme stoppen & speichern", systemImage: "stop.circle.fill") }
            } else {
                Button {
                    Task {
                        let ok = await ctl.startRecording()
                        if !ok { errMsg = "Kein Mikrofon-Zugriff." }
                    }
                } label: { Label(hasNote ? "Neu aufnehmen" : "Aufnehmen", systemImage: "mic.circle") }
                    .disabled(ctl.busy)
            }
            if hasNote && !ctl.recording {
                Button(role: .destructive) {
                    Task { try? await api.deleteVoiceNote(photoId); hasNote = false }
                } label: { Label("Löschen", systemImage: "trash") }
            }
            if let errMsg { Text(errMsg).font(.caption).foregroundStyle(.red) }
        }
    }
}
