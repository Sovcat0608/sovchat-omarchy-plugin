import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "RoomPolicy.js" as RoomPolicy

Button {
  id: root
  required property var theme
  property var service: null
  property real viewportWidth: 352
  property real viewportHeight: 654
  readonly property string currentId: service && service.currentRoom ? service.currentRoom.id : ""
  readonly property string roomName: service && service.currentRoom ? service.currentRoom.name : "No room"
  readonly property var rooms: service ? RoomPolicy.ordered(service.currentRoom, service.ownedRoom, service.joinedRooms) : []
  readonly property bool expanded: menu.opened
  signal settingsRequested()
  objectName: "roomSwitcher"
  implicitWidth: Math.min(Math.max(theme.px(100), Math.ceil(titleMetrics.advanceWidth) + theme.px(58)), viewportWidth * 0.62)
  implicitHeight: theme.px(34)
  enabled: !!service && service.ready && !!service.session
  hoverEnabled: true
  Accessible.name: "Open room switcher"
  Accessible.description: expanded ? "Room menu expanded" : "Room menu collapsed"
  onCurrentIdChanged: menu.close()
  onVisibleChanged: if (!visible) menu.close()
  onEnabledChanged: if (!enabled) menu.close()
  onClicked: menu.opened ? menu.close() : menu.open()
  function openMenu() { if (enabled) menu.open() }
  function closeMenu() { menu.close() }
  function choose(roomId) {
    if (!service || !rooms.some(function(room) { return room.id === roomId })
        || !RoomPolicy.canSwitch(service.ready, service.busy, service.media, currentId, roomId)) return false
    if (!service.request("switch", { roomId: roomId })) return false
    menu.close()
    return true
  }
  background: Rectangle {
    radius: root.theme.px(2)
    color: root.hovered || root.expanded ? root.theme.raised : root.theme.sunken
    border.color: root.hovered || root.activeFocus || root.expanded ? root.theme.secondary : root.theme.subtleBorder
  }
  contentItem: RowLayout {
    spacing: root.theme.px(8)
    RoomEmblem { theme: root.theme; name: root.roomName; image: root.service && root.service.currentRoom ? root.service.currentRoom.avatarImage || "" : "" }
    Text { id: title; Layout.fillWidth: true; text: root.roomName; textFormat: Text.PlainText; elide: Text.ElideRight; color: root.theme.foreground; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(14); font.bold: true }
  }
  leftPadding: theme.px(9); rightPadding: theme.px(9); topPadding: theme.px(3); bottomPadding: theme.px(3)
  TextMetrics { id: titleMetrics; font: title.font; text: root.roomName }
  Popup {
    id: menu; objectName: "roomSwitcherMenu"
    x: (root.width - width) / 2; y: root.height + root.theme.px(12)
    width: Math.min(root.theme.px(416), root.viewportWidth - root.theme.px(48))
    height: Math.min(content.implicitHeight + padding * 2, root.viewportHeight - root.theme.px(96))
    padding: root.theme.px(8); margins: root.theme.px(12)
    focus: true; modal: false
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
    background: Rectangle { color: root.theme.sunken; radius: root.theme.px(2); border.color: root.theme.border }
    onOpened: list.forceActiveFocus()
    onClosed: if (root.visible && root.enabled) root.forceActiveFocus()
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 120 } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }
    contentItem: ColumnLayout {
      id: content; spacing: root.theme.px(8)
      Text { text: "QUICK SWITCH"; color: root.theme.muted; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(10); font.letterSpacing: 1; Layout.margins: root.theme.px(4) }
      ListView {
        id: list; objectName: "roomSwitcherList"; Layout.fillWidth: true; Layout.fillHeight: true
        Layout.preferredHeight: Math.min(contentHeight, root.theme.px(352), root.viewportHeight * 0.48)
        clip: true; spacing: root.theme.px(4); model: root.rooms; currentIndex: 0; keyNavigationEnabled: true
        Keys.onReturnPressed: if (currentItem) root.choose(currentItem.roomId)
        Keys.onEnterPressed: if (currentItem) root.choose(currentItem.roomId)
        Keys.onSpacePressed: if (currentItem) root.choose(currentItem.roomId)
        delegate: ItemDelegate {
          id: row; required property var modelData
          readonly property string roomId: modelData.id
          readonly property bool isCurrent: roomId === root.currentId
          width: list.width; height: root.theme.px(58)
          enabled: !!root.service && RoomPolicy.canSwitch(root.service.ready, root.service.busy, root.service.media, root.currentId, roomId)
          Accessible.name: modelData.name + (isCurrent ? ", current room" : "")
          Accessible.checkable: true; Accessible.checked: isCurrent
          onClicked: root.choose(roomId)
          background: Rectangle { radius: root.theme.px(2); color: row.isCurrent ? root.theme.selected : row.hovered ? root.theme.raised : "transparent"; border.width: row.activeFocus || (list.activeFocus && row.ListView.isCurrentItem) ? 1 : 0; border.color: root.theme.secondary }
          contentItem: RowLayout {
            spacing: root.theme.px(12)
            RoomEmblem { theme: root.theme; name: row.modelData.name; image: row.modelData.avatarImage || ""; Layout.preferredWidth: root.theme.px(40); Layout.preferredHeight: root.theme.px(40) }
            ColumnLayout {
              Layout.fillWidth: true; spacing: root.theme.px(3)
              Text { Layout.fillWidth: true; text: row.modelData.name; textFormat: Text.PlainText; elide: Text.ElideRight; color: root.theme.foreground; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(14) }
              Text { Layout.fillWidth: true; text: row.modelData.isOwned ? "Your room" : root.service && root.service.roomCodes && root.service.roomCodes[row.roomId] ? "Code " + root.service.roomCodes[row.roomId] : "Joined room"; textFormat: Text.PlainText; elide: Text.ElideRight; color: root.theme.muted; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(11) }
            }
            Text { text: row.isCurrent ? "✓" : ""; color: root.theme.secondary; font.pixelSize: root.theme.px(16); Layout.preferredWidth: root.theme.px(20) }
          }
        }
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: root.theme.px(4) }
      }
      Text { visible: root.rooms.length === 0; text: "No rooms available yet."; color: root.theme.muted; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(12); Layout.margins: root.theme.px(8) }
      Text { visible: !!root.service && !!root.service.media && !!(root.service.media.connected || root.service.media.connecting || root.service.media.screenPending); Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Leave voice to switch rooms."; color: root.theme.muted; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(10) }
      Rectangle { Layout.fillWidth: true; height: 1; color: root.theme.subtleBorder }
      Button {
        objectName: "roomSwitcherSettings"; Layout.fillWidth: true; implicitHeight: root.theme.px(34)
        text: "Room settings"; Accessible.name: text
        onClicked: { menu.close(); root.settingsRequested() }
        background: Rectangle { color: parent.hovered ? root.theme.raised : "transparent"; border.width: parent.activeFocus ? 1 : 0; border.color: root.theme.secondary; radius: root.theme.px(2) }
        contentItem: Item { implicitWidth: settingsContent.implicitWidth; implicitHeight: settingsContent.implicitHeight; Row { id: settingsContent; spacing: root.theme.px(8); anchors.centerIn: parent; NativeGlyph { kind: "settings"; color: root.theme.foreground; width: root.theme.px(16); height: width } Text { text: "Room settings"; color: root.theme.foreground; font.family: root.theme.fontFamily; font.pixelSize: root.theme.px(12) } } }
      }
    }
  }
}
