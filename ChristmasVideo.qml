import QtQuick
import QtMultimedia

// Loaded only for the animated lobby. The poster remains underneath if Qt
// Multimedia or the platform decoder is unavailable.
VideoOutput {
  id: output
  objectName: "christmasVideoOutput"
  readonly property bool hasFrame: videoSink.videoSize.width > 0
  visible: hasFrame && player.error === MediaPlayer.NoError
  fillMode: VideoOutput.PreserveAspectCrop

  MediaPlayer {
    id: player
    source: "assets/christmas-compact.mp4"
    videoOutput: output
    loops: MediaPlayer.Infinite
    Component.onCompleted: play()
  }
}
