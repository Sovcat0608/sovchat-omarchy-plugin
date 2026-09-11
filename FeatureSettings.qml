import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Flickable {
  id: root
  required property var theme
  property var service: null
  property string section: "profile"
  property var confirmedAction: ({})
  readonly property bool ready: !!service && service.ready && !service.busy
  readonly property bool signedIn: !!service && service.session !== null
  onSignedInChanged: if (!signedIn) { joinCode.clear(); createCode.clear(); createName.clear() }
  readonly property var ownerRoom: service ? service.ownedRoom : null
  function deviceIndex(rows, value) {
    for (var i = 0; i < rows.length; ++i) if (rows[i].id === value) return i
    return 0
  }
  clip: true; contentHeight: content.implicitHeight + theme.px(24)
  boundsBehavior: Flickable.StopAtBounds
  function refresh() {
    if (!visible || !service || !service.ready) return
    if (section === "audio") service.request("audio-devices")
    else if (signedIn) service.request(section === "profile" ? "profile" : section === "usage" ? "usage" : "refresh")
    nickname.text = signedIn ? service.session.nickname : ""
    roomName.text = ownerRoom ? ownerRoom.name : ""
    limit.value = ownerRoom ? ownerRoom.dailyStreamLimitMinutes || 0 : 0
    filler.checked = ownerRoom ? !!ownerRoom.fillerMode : false
  }
  onVisibleChanged: if (visible) refresh()
  onSectionChanged: refresh()
  Timer {
    id: outputCommit; interval: 120
    onTriggered: {
      if (!root.service || !root.service.ready) return
      if (!root.service.request("output-volume", { volume: masterOutput.value / 100 })) restart()
    }
  }
  function confirm(data) { confirmedAction = data; confirmation.open() }
  component Copy: Label {
    Layout.fillWidth: true; textFormat: Text.PlainText; wrapMode: Text.Wrap
    color: theme.foreground; font.family: theme.fontFamily; font.pixelSize: theme.px(11)
  }
  component Heading: Copy { color: theme.accent; font.pixelSize: theme.px(10); font.letterSpacing: 2; Layout.topMargin: theme.px(12) }
  component Action: Button {
    id: button; implicitHeight: theme.px(34); implicitWidth: Math.max(theme.px(36), label.implicitWidth + theme.px(16))
    font.family: theme.fontFamily; font.pixelSize: theme.px(11)
    background: Rectangle { color: button.hovered ? theme.raised : theme.sunken; border.color: button.activeFocus ? theme.accent : theme.subtleBorder }
    contentItem: Text { id: label; text: button.text; textFormat: Text.PlainText; font: button.font; color: button.enabled ? theme.foreground : theme.muted; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
  }
  component Entry: TextField {
    id: entry; Layout.fillWidth: true; implicitHeight: theme.px(36)
    font.family: theme.fontFamily; font.pixelSize: theme.px(12); color: theme.foreground; placeholderTextColor: theme.muted
    background: Rectangle { color: theme.sunken; border.color: entry.activeFocus ? theme.accent : theme.subtleBorder }
  }
  component Check: CheckBox {
    id: check; font.family: theme.fontFamily; font.pixelSize: theme.px(11)
    contentItem: Copy { text: check.text; leftPadding: theme.px(30); verticalAlignment: Text.AlignVCenter }
  }
  component Select: ComboBox {
    id: box; Layout.fillWidth: true; implicitHeight: theme.px(36); textRole: "name"
    background: Rectangle { color: theme.sunken; border.color: box.activeFocus ? theme.accent : theme.subtleBorder }
    contentItem: Copy { text: box.displayText; leftPadding: theme.px(8); rightPadding: theme.px(20); verticalAlignment: Text.AlignVCenter; maximumLineCount: 1; elide: Text.ElideRight }
    delegate: ItemDelegate {
      required property var modelData; width: box.width
      contentItem: Copy { text: modelData.name; maximumLineCount: 1; elide: Text.ElideRight }
      background: Rectangle { color: parent.hovered ? theme.raised : theme.sunken }
    }
  }
  FileDialog {
    id: avatarFile; property bool roomImage: false
    title: "Choose a PNG, JPEG or WebP avatar"; fileMode: FileDialog.OpenFile
    nameFilters: ["Images (*.png *.jpg *.jpeg *.webp)"]
    onAccepted: {
      if (roomImage) root.service.request("room-action", { action: "update-owned", name: roomName.text,
        fillerMode: filler.checked, dailyStreamLimitMinutes: limit.value, avatarFile: selectedFile.toString() })
      else root.service.request("profile", { avatarFile: selectedFile.toString() })
    }
  }
  Dialog {
    id: confirmation; anchors.centerIn: parent; width: Math.min(parent.width - theme.px(12), theme.px(300)); implicitHeight: theme.px(220); modal: true
    title: "Confirm room action"; standardButtons: Dialog.Yes | Dialog.No
    contentItem: Copy { text: "Apply this room change? Member removal, bans, room deletion and code resets take effect immediately." }
    onAccepted: root.service.request("room-action", root.confirmedAction)
  }
  ColumnLayout {
    id: content; x: theme.px(12); y: theme.px(12); width: parent.width - theme.px(24); spacing: theme.px(10)
    Copy { visible: !root.signedIn && root.section !== "audio" && root.section !== "diagnostics"; text: "Sign in to manage these settings."; color: theme.muted }
    ColumnLayout {
      Layout.fillWidth: true; visible: root.section === "profile" && root.signedIn; spacing: theme.px(10)
      Heading { text: "YOUR PROFILE" }
      NativeAvatar { Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: theme.px(64); Layout.preferredHeight: theme.px(64); nickname: root.signedIn ? root.service.session.nickname : ""; avatar: root.service && root.service.profile ? root.service.profile.avatarImage || "" : "" }
      Entry { id: nickname; placeholderText: "Display name"; maximumLength: 20 }
      Action { text: "Save display name"; enabled: root.ready && nickname.text.trim().length >= 2; onClicked: root.service.request("profile", { nickname: nickname.text }) }
      GridLayout {
        Layout.fillWidth: true; columns: 5
        Repeater {
          model: 15
          Button {
            required property int index; Layout.fillWidth: true; implicitHeight: theme.px(42); enabled: root.ready
            Accessible.name: "Choose avatar " + (index + 1)
            background: Rectangle { color: parent.hovered ? theme.selected : "transparent"; border.width: parent.activeFocus ? 1 : 0; border.color: theme.accent }
            contentItem: NativeAvatar { avatar: "avatar-" + (parent.index + 1) + ".png" }
            onClicked: root.service.request("profile", { avatarId: "avatar-" + (index + 1) })
          }
        }
      }
      Action { text: "Upload avatar…"; enabled: root.ready; onClicked: { avatarFile.roomImage = false; avatarFile.open() } }
      Copy { text: "PNG, JPEG or WebP, up to 8 MB / 40 megapixels. Resized locally before upload."; color: theme.muted; font.pixelSize: theme.px(10) }
    }
    ColumnLayout {
      Layout.fillWidth: true; visible: root.section === "audio"; spacing: theme.px(10)
      Heading { text: "VOICE & DEVICES" }
      Copy { text: "Leave voice before changing devices or processing."; color: theme.muted }
      Copy { text: "Microphone" }
      Select { id: inputDevice; model: [{ id: "", name: "System default" }].concat(root.service && root.service.devices ? root.service.devices.inputs : []); currentIndex: root.deviceIndex(model, root.service && root.service.media.audioOptions ? root.service.media.audioOptions.input : "") }
      Copy { text: "Output" }
      Select { id: outputDevice; model: [{ id: "", name: "System default" }].concat(root.service && root.service.devices ? root.service.devices.outputs : []); currentIndex: root.deviceIndex(model, root.service && root.service.media.audioOptions ? root.service.media.audioOptions.output : "") }
      Copy { text: "SovChat output volume · " + Math.round(masterOutput.value) + "%" }
      Slider { id: masterOutput; Layout.fillWidth: true; from: 0; to: 100; stepSize: 1; enabled: root.ready; value: root.service && root.service.media.audioOptions ? (root.service.media.audioOptions.outputVolume === undefined ? 1 : root.service.media.audioOptions.outputVolume) * 100 : 100; onMoved: outputCommit.restart() }
      Check { id: noise; text: "Noise suppression"; checked: root.service && root.service.media.audioOptions ? root.service.media.audioOptions.noiseSuppression : true }
      Check { id: echo; text: "Echo cancellation"; checked: root.service && root.service.media.audioOptions ? root.service.media.audioOptions.echoCancellation : true }
      Check { id: gain; text: "Automatic gain control"; checked: root.service && root.service.media.audioOptions ? root.service.media.audioOptions.autoGainControl : true }
      Copy { text: "Auto leave voice after idle minutes (0 = off)" }
      SpinBox { id: afk; from: 0; to: 120; editable: true; value: root.service && root.service.media.audioOptions ? root.service.media.audioOptions.afkMinutes || 0 : 0 }
      Action { text: "Apply audio settings"; enabled: root.ready && !root.service.media.connected; onClicked: root.service.request("audio-settings", { input: inputDevice.model[inputDevice.currentIndex].id, output: outputDevice.model[outputDevice.currentIndex].id, noiseSuppression: noise.checked, echoCancellation: echo.checked, autoGainControl: gain.checked, afkMinutes: afk.value }) }
      Action { text: "Refresh devices"; enabled: root.ready; onClicked: root.service.request("audio-devices") }
      Copy { text: "Native WebRTC processing. No extra amplitude gate. This is not Krisp; physical-device speech quality still needs testing."; font.pixelSize: theme.px(10); color: theme.muted }
    }
    ColumnLayout {
      Layout.fillWidth: true; visible: root.section === "room" && root.signedIn; spacing: theme.px(10)
      Heading { text: "CURRENT ROOM" }
      Copy { text: root.service && root.service.currentRoom ? root.service.currentRoom.name : "No room selected" }
      Copy { text: root.service && root.service.currentRoom && root.service.roomCodes ? "Invite code: " + (root.service.roomCodes[root.service.currentRoom.id] || "—") : "" }
      TextField {
        visible: !!root.service && !!root.service.currentRoom; Layout.fillWidth: true; readOnly: true; selectByMouse: true
        text: root.service && root.service.currentRoom && root.service.roomCodes ? root.service.roomCodes[root.service.currentRoom.id] || "" : ""
        color: theme.foreground; font.family: theme.fontFamily; Accessible.name: "Select and copy invite code"
        background: Rectangle { color: theme.sunken; border.color: theme.subtleBorder }
      }
      Action { text: root.service && root.service.currentRoom && root.service.currentRoom.isOwned ? "Delete current room…" : "Leave current room…"; enabled: root.ready && !!root.service.currentRoom && !root.service.media.connected; onClicked: root.confirm({ action: "remove-room", roomId: root.service.currentRoom.id }) }
      Heading { text: "JOIN A ROOM" }
      Entry { id: joinCode; placeholderText: "Room code"; maximumLength: 100 }
      Action { text: "Join room"; enabled: root.ready && !root.service.media.connected && !root.service.media.connecting && joinCode.text.trim() !== ""; onClicked: root.service.request("join-room", { code: joinCode.text.trim() }) }
      Heading { text: "YOUR OWNED ROOM" }
      ColumnLayout {
        visible: !root.ownerRoom; Layout.fillWidth: true; spacing: theme.px(8)
        Entry { id: createName; placeholderText: "New room name"; maximumLength: 32 }
        Entry { id: createCode; placeholderText: "New room code"; maximumLength: 100 }
        Action { text: "Create room"; enabled: root.ready && !root.service.media.connected && !root.service.media.connecting && createName.text.trim().length >= 2 && createCode.text.trim() !== ""; onClicked: root.service.request("create-room", { name: createName.text.trim(), code: createCode.text.trim() }) }
      }
      ColumnLayout {
        visible: !!root.ownerRoom; Layout.fillWidth: true; spacing: theme.px(10)
        Entry { id: roomName; placeholderText: "Owned room name"; maximumLength: 32 }
        Check { id: filler; text: "Filler mode" }
        Copy { text: "Daily sharing minutes per user (0 = unlimited)" }
        SpinBox { id: limit; from: 0; to: 1440; editable: true }
        Action { text: "Save room settings"; enabled: root.ready && !root.service.media.connected; onClicked: root.service.request("room-action", { action: "update-owned", name: roomName.text, fillerMode: filler.checked, dailyStreamLimitMinutes: limit.value }) }
        Action { text: "Room image…"; enabled: root.ready && !root.service.media.connected; onClicked: { avatarFile.roomImage = true; avatarFile.open() } }
        Action { text: "Remove room image"; enabled: root.ready && !root.service.media.connected; onClicked: root.service.request("room-action", { action: "update-owned", name: roomName.text, fillerMode: filler.checked, dailyStreamLimitMinutes: limit.value, avatarFile: null }) }
        Action { text: "Reset invite code…"; enabled: root.ready && !root.service.media.connected; onClicked: root.confirm({ action: "reset-owned-code" }) }
        Action { text: "Reset daily stream usage…"; enabled: root.ready && !root.service.media.connected; onClicked: root.confirm({ action: "reset-owned-stream-usage" }) }
        Heading { text: "MEMBERS" }
        Repeater {
          model: root.service ? root.service.ownedRoomMembers || [] : []
          ColumnLayout {
            required property var modelData; Layout.fillWidth: true
            Copy { text: modelData.nickname + (modelData.isOwner ? " · Owner" : "") }
            RowLayout {
              visible: !modelData.isOwner
              Action { text: "Remove…"; enabled: root.ready && !root.service.media.connected; onClicked: root.confirm({ action: "remove-owned-member", userId: modelData.userId }) }
              Action { text: "Ban…"; enabled: root.ready && !root.service.media.connected; onClicked: root.confirm({ action: "ban-owned-member", userId: modelData.userId }) }
            }
          }
        }
        Heading { text: "BANNED MEMBERS" }
        Repeater {
          model: root.service ? root.service.ownedRoomBans || [] : []
          RowLayout {
            required property var modelData; Layout.fillWidth: true
            Copy { text: modelData.nickname }
            Action { text: "Unban…"; enabled: root.ready && !root.service.media.connected; onClicked: root.confirm({ action: "unban-owned-member", userId: modelData.userId }) }
          }
        }
      }
    }
    ColumnLayout {
      visible: root.section === "usage" && root.signedIn; Layout.fillWidth: true
      Heading { text: "ROOM USAGE" }
      Entry { id: usageMonth; placeholderText: "Month: YYYY-MM"; maximumLength: 7 }
      Action { text: "Load selected month"; enabled: root.ready && /^\d{4}-(0[1-9]|1[0-2])$/.test(usageMonth.text); onClicked: root.service.request("usage", { month: usageMonth.text }) }
      Copy { text: root.service && root.service.usage ? "Month: " + (root.service.usage.month || "—") + "\nVoice minutes: " + (root.service.usage.totalWebRtcMinutes || 0) + "\nStreaming minutes: " + (root.service.usage.totalStreamMinutes || 0) + "\nStream data (GB): " + (root.service.usage.totalStreamGb || 0) : "" }
      Action { text: "Refresh usage"; enabled: root.ready; onClicked: root.service.request("usage") }
      Copy { text: root.service && root.service.usage ? "Daily averages: " + (root.service.usage.averageWebRtcMinutesPerDay || 0) + " voice min · " + (root.service.usage.averageStreamMinutesPerDay || 0) + " stream min · " + (root.service.usage.averageStreamGbPerDay || 0) + " GB" : "" }
      Heading { text: "DAILY BREAKDOWN" }
      Repeater {
        model: root.service && root.service.usage ? root.service.usage.days || [] : []
        Copy { required property var modelData; text: modelData.dateKey + "\n" + modelData.webRtcMinutes + " voice min · " + modelData.streamMinutes + " stream min · " + modelData.streamGb + " GB"; Layout.bottomMargin: theme.px(8) }
      }
    }
    ColumnLayout {
      visible: root.section === "diagnostics"; Layout.fillWidth: true
      Heading { text: "NATIVE DIAGNOSTICS" }
      Copy { text: "Omarchy plugin · no Electron or embedded browser\nShared SovChat accounts and LiveKit" }
      Copy { text: "Helper: " + (root.service && root.service.ready ? "Ready" : "Stopped") + "\nNative audio: " + (root.service && root.service.media.available ? "Available" : "Not enabled / missing runtime") + "\nScreen capture: " + (root.service && root.service.media.screenSharingAvailable ? "Available" : "Missing runtime or bridge") + "\nSecure storage: " + (root.service && root.service.secureStorage ? "Secret Service" : "Unavailable") }
      Copy { text: "Native release. Capability availability is not an end-to-end QA result. See release notes for known limitations."; color: theme.muted }
    }
  }
  ScrollBar.vertical: ScrollBar { width: theme.px(4); policy: ScrollBar.AsNeeded }
}
