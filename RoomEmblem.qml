import QtQuick

Rectangle {
  id: root
  required property var theme
  property string name: ""
  property string image: ""
  color: theme.raised; radius: theme.px(1)
  implicitWidth: theme.px(26); implicitHeight: implicitWidth
  Text {
    anchors.fill: parent; visible: photo.status !== Image.Ready
    text: (root.name || "?").slice(0, 2).toUpperCase(); textFormat: Text.PlainText
    color: root.theme.foreground; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(10)
    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
  }
  Image {
    id: photo; anchors.fill: parent; fillMode: Image.PreserveAspectFit
    sourceSize.width: 80; sourceSize.height: 80
    source: /^avatar-([1-9]|1[0-5])\.png$/.test(root.image) ? Qt.resolvedUrl("assets/" + root.image)
      : root.image.length <= 900000 && /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(root.image) ? root.image : ""
  }
}
