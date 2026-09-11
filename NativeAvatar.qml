import QtQuick
import QtQuick.Effects

Rectangle {
  id: root
  property string nickname: ""
  property string avatar: ""
  property color foreground: "#e8e8e8"
  readonly property bool imageReady: photo.status === Image.Ready
  color: "#393337"
  radius: width / 2
  implicitWidth: 32; implicitHeight: 32
  Text { anchors.centerIn: parent; text: root.nickname.slice(0, 1).toUpperCase(); color: root.foreground; font.family: "monospace"; font.bold: true }
  Image {
    id: photo
    anchors.fill: parent
    // The API projects only bounded raster data or a bundled avatar filename.
    source: /^avatar-([1-9]|1[0-5])\.png$/.test(root.avatar) ? Qt.resolvedUrl("assets/" + root.avatar)
      : root.avatar.length <= 350000 && /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(root.avatar) ? root.avatar : ""
    sourceSize.width: 64; sourceSize.height: 64
    fillMode: Image.PreserveAspectCrop
    visible: false
  }
  Rectangle { id: mask; anchors.fill: parent; radius: width / 2; color: "white"; layer.enabled: true; visible: false }
  MultiEffect { anchors.fill: parent; source: photo; visible: photo.status === Image.Ready; maskEnabled: true; maskSource: mask }
}
