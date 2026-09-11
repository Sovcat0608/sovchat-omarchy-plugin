import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Palette.js" as Palette

Rectangle {
  id: root
  required property var paletteTheme
  property var service: null
  property string section: "palette"
  readonly property var theme: paletteTheme
  signal backRequested()
  signal themeSelected(string value)
  color: theme.background
  component Copy: Label {
    Layout.fillWidth: true; textFormat: Text.PlainText; wrapMode: Text.Wrap
    color: theme.foreground; font.family: theme.fontFamily; font.pixelSize: theme.px(12)
  }
  component Rule: Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.subtleBorder }
  component Heading: RowLayout {
    property string title: ""
    property string glyph: ""
    Layout.fillWidth: true; Layout.topMargin: theme.px(20); Layout.bottomMargin: theme.px(12); spacing: theme.px(14)
    NativeGlyph { width: theme.px(22); height: width; kind: parent.glyph; color: theme.secondary }
    Copy { text: parent.title; font.bold: true }
  }
  ColumnLayout {
    anchors.fill: parent; spacing: 0
    RowLayout {
      Layout.fillWidth: true; Layout.leftMargin: theme.px(12); Layout.rightMargin: theme.px(12); Layout.topMargin: theme.px(8); Layout.bottomMargin: theme.px(8)
      Copy { text: "SETTINGS"; color: theme.accent; font.pixelSize: theme.px(11); font.letterSpacing: 3 }
      Button {
        implicitWidth: theme.px(36); implicitHeight: theme.px(36); Accessible.name: "Back to lobby"
        background: Rectangle { color: theme.sunken; border.color: parent.activeFocus ? theme.accent : theme.subtleBorder }
        contentItem: Item { NativeGlyph { anchors.centerIn: parent; width: theme.px(20); height: width; kind: "close"; color: theme.foreground } }
        onClicked: root.backRequested()
      }
    }
    Rule {}
    RowLayout {
      Layout.fillWidth: true; Layout.leftMargin: theme.px(12); Layout.rightMargin: theme.px(12); spacing: theme.px(2)
      Repeater {
        model: ["microphone", "palette", "people", "voice", "settings", "wrench"]
        Button {
          required property string modelData
          readonly property string pageName: ({ microphone: "audio", palette: "palette", people: "profile", voice: "usage", settings: "room", wrench: "diagnostics" })[modelData]
          Layout.fillWidth: true; implicitHeight: theme.px(48)
          Accessible.name: pageName + " settings"
          background: Rectangle { color: pageName === root.section ? theme.selected : "transparent"; Rectangle { anchors.bottom: parent.bottom; height: 2; width: parent.width; color: theme.accent; visible: pageName === root.section } }
          contentItem: Item { NativeGlyph { anchors.centerIn: parent; width: theme.px(20); height: width; kind: modelData; color: parent.parent.pageName === root.section ? theme.secondary : theme.muted } }
          onClicked: root.section = pageName
          ToolTip.visible: hovered; ToolTip.text: Accessible.name; ToolTip.delay: 600
        }
      }
    }
    Rule {}
    Flickable {
      id: viewport; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; visible: root.section === "palette"
      contentHeight: appearance.implicitHeight + theme.px(24); boundsBehavior: Flickable.StopAtBounds
      ScrollBar.vertical: ScrollBar { width: theme.px(4); policy: ScrollBar.AsNeeded }
      ColumnLayout {
        id: appearance; x: theme.px(12); y: theme.px(10); width: viewport.width - theme.px(24); spacing: theme.px(8)
        Copy { text: "APPEARANCE"; color: theme.accent; font.pixelSize: theme.px(10); font.letterSpacing: 3 }
        Heading { title: "Interface"; glyph: "monitor" }
        Rule {}
        Rectangle {
          Layout.fillWidth: true; implicitHeight: theme.px(40); color: theme.selected; border.color: theme.subtleBorder
          RowLayout { anchors.fill: parent; anchors.margins: theme.px(12); spacing: theme.px(14); NativeGlyph { width: theme.px(16); height: width; kind: "monitor"; color: theme.secondary } Copy { text: "Linux · compact"; font.bold: true } Copy { Layout.fillWidth: false; text: "✓"; color: theme.accent } }
          Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: theme.accent }
        }
        Heading { title: "Theme colours"; glyph: "palette" }
        Rule {}
        Repeater {
          model: Palette.choices
          Button {
            id: choice; required property var modelData
            objectName: "theme-" + modelData.id
            readonly property bool chosen: theme.palette.id === modelData.id
            Layout.fillWidth: true; implicitHeight: theme.px(40); padding: theme.px(12)
            Accessible.name: modelData.name; Accessible.checkable: true; Accessible.checked: chosen
            background: Rectangle {
              color: choice.chosen ? theme.selected : choice.hovered ? theme.raised : "transparent"
              border.width: choice.activeFocus ? 1 : 0; border.color: theme.accent
              Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: theme.accent; visible: choice.chosen }
            }
            contentItem: RowLayout {
              spacing: theme.px(14)
              Rectangle { implicitWidth: theme.px(32); implicitHeight: theme.px(24); color: modelData.accent; Rectangle { anchors.right: parent.right; width: parent.width / 2; height: parent.height; color: modelData.secondary } }
              Copy { text: modelData.name; font.bold: true }
              Copy { Layout.fillWidth: false; text: choice.chosen ? "✓" : ""; color: theme.accent }
            }
            onClicked: root.themeSelected(modelData.id)
          }
        }
        Rule {}
        Copy { text: "Omarchy plugin · compact only"; color: theme.muted; font.pixelSize: theme.px(10) }
        Copy { visible: !!root.service && root.service.update.available; text: visible ? "Plugin " + root.service.update.latest + " available\nomarchy plugin update com.sovchat.omarchy\nThen rerun setup.py in the plugin folder and reload the shell. See the release notes." : ""; color: theme.accent; font.pixelSize: theme.px(10) }
        Copy { visible: text !== ""; text: root.service ? root.service.updateError || "" : ""; color: theme.muted; font.pixelSize: theme.px(10) }
        RowLayout {
          Repeater {
            model: ["Check updates", "Sign out"]
            Button {
              required property string modelData
              visible: modelData !== "Sign out" || (!!root.service && root.service.session !== null)
              enabled: !!root.service && root.service.ready && (modelData === "Sign out" || !root.service.busy)
              implicitWidth: label.implicitWidth + theme.px(20); implicitHeight: theme.px(34)
              Accessible.name: modelData
              background: Rectangle { color: theme.sunken; border.color: parent.activeFocus ? theme.accent : theme.subtleBorder }
              contentItem: Copy { id: label; text: modelData; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? theme.foreground : theme.muted }
              onClicked: root.service.request(modelData === "Sign out" ? "logout" : "updates")
            }
          }
        }
      }
    }
    FeatureSettings {
      Layout.fillWidth: true; Layout.fillHeight: true; visible: root.section !== "palette"
      theme: root.paletteTheme; service: root.service; section: root.section
    }
  }
}
