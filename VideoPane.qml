import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "bridge"

Rectangle {
  id: root
  property string frameName: ""
  property var paletteTheme: null
  property var service: null
  property real streamVolume: service && service.media.volumes && service.media.volumes["$stream"] !== undefined ? service.media.volumes["$stream"] : 1
  readonly property bool hasFrame: surface.hasFrame
  readonly property int frameCount: surface.frameCount
  readonly property bool expandedVisible: expanded.visible
  function showExpanded() { expanded.show() }
  function hideExpanded() { expanded.close() }
  signal backRequested()
  color: "#111111"
  component Action: Button {
    id: button; implicitHeight: 34
    font.family: root.paletteTheme ? root.paletteTheme.fontFamily : "monospace"
    font.pixelSize: 11
    background: Rectangle { color: root.paletteTheme ? button.hovered ? root.paletteTheme.raised : root.paletteTheme.sunken : "#1b1619"; border.color: root.paletteTheme ? button.activeFocus ? root.paletteTheme.accent : root.paletteTheme.subtleBorder : "#3b3639" }
    contentItem: Text { text: button.text; textFormat: Text.PlainText; font: button.font; color: "#e8e8e8"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
  }
  component AudioControls: RowLayout {
    visible: !!root.service
    Label { text: "Stream audio"; color: "#e8e8e8"; font.pixelSize: 10 }
    Slider { Layout.fillWidth: true; from: 0; to: 2; stepSize: 0.05; value: root.streamVolume; onMoved: { root.streamVolume = value; volumeCommit.restart() } }
    Action { text: root.streamVolume === 0 ? "Unmute" : "Mute"; onClicked: { root.streamVolume = root.streamVolume === 0 ? 1 : 0; volumeCommit.restart() } }
  }
  Timer {
    id: volumeCommit; interval: 120
    onTriggered: {
      if (!root.service || !root.service.media.connected) return
      if (!root.service.request("screen-volume", { volume: root.streamVolume })) restart()
    }
  }
  ColumnLayout {
    anchors.fill: parent; spacing: 0
    RowLayout {
      Layout.fillWidth: true
      Action { text: "Back"; onClicked: root.backRequested() }
      Label { Layout.fillWidth: true; text: "LIVE SCREEN"; textFormat: Text.PlainText; color: "#e8e8e8" }
      Action { text: "Expand"; onClicked: root.showExpanded() }
    }
    VideoSurface { id: surface; Layout.fillWidth: true; Layout.fillHeight: true; frameName: expanded.visible ? "" : root.frameName }
    AudioControls { Layout.fillWidth: true }
    Label { Layout.fillWidth: true; visible: !surface.hasFrame && !expanded.visible; text: "Waiting for video…"; textFormat: Text.PlainText; color: "#e8e8e8"; padding: 12 }
  }
  Window {
    id: expanded; title: "SovChat screen share"; width: 960; height: 600; color: "#111111"
    ColumnLayout {
      anchors.fill: parent; spacing: 0
      RowLayout {
        Action { text: "Return to panel"; onClicked: root.hideExpanded() }
        Action { text: expanded.visibility === Window.FullScreen ? "Exit full screen" : "Full screen"; onClicked: expanded.visibility === Window.FullScreen ? expanded.showNormal() : expanded.showFullScreen() }
      }
      VideoSurface { Layout.fillWidth: true; Layout.fillHeight: true; frameName: expanded.visible ? root.frameName : "" }
      AudioControls { Layout.fillWidth: true }
    }
  }
  Component.onDestruction: expanded.close()
}
