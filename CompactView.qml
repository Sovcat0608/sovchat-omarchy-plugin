import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "DraftPolicy.js" as DraftPolicy
import "FeedbackPolicy.js" as FeedbackPolicy
import "Palette.js" as Palette
import "AvatarPolicy.js" as AvatarPolicy

Rectangle {
  id: root
  property var service: null
  property real uiScale: 1
  property string fontFamily: "monospace"
  property string themeId: "ember-shift"
  property string page: "lobby"
  property bool showProgress: false
  property var attachedFiles: []
  property var whisperIds: []
  property var replyTarget: null
  property string attachmentId: ""
  property string deleteId: ""
  property string reactionId: ""
  property string volumeTarget: ""
  readonly property string layoutMode: theme.layoutMode
  readonly property var viewTheme: theme
  readonly property bool signedIn: !!service && service.session !== null
  readonly property bool actionsReady: !!service && service.ready && !service.busy
  readonly property bool controlsReady: !!service && service.ready
  readonly property bool backgroundBusy: !!service && service.busy && FeedbackPolicy.background(service.pendingOp)
  readonly property string foregroundOperation: service && service.busy && !backgroundBusy ? service.pendingOp : ""
  readonly property string draftContext: DraftPolicy.contextKey(
    service ? service.session : null, service ? service.currentRoom : null)
  readonly property string roomName: service && service.currentRoom ? service.currentRoom.name : "Select a room"
  readonly property Item preferredFocus: !signedIn && page !== "settings" ? authView.preferredFocus : page === "chat" ? draft : root
  signal closeRequested()
  signal themeSelected(string value)
  color: theme.background
  implicitWidth: theme.px(352)
  implicitHeight: theme.px(654)
  CompactTheme { id: theme; scale: root.uiScale; fontFamily: root.fontFamily; themeId: root.themeId }

  function clearSensitive() {
    authView.clearSensitive()
    if (root.service && root.service.media.watching) root.service.request("screen-unwatch")
  }
  function roster(group) {
    if (!root.signedIn) return []
    var live = root.service.participants || []
    if (group === "LIVE") return live.map(function(p) { return { participantId: p.participantId, userId: p.userId || p.participantId, nickname: p.displayName, avatarImage: p.avatarImage || "", muted: p.isSelfMuted, deafened: p.isSelfDeafened } })
    return (root.service.presence || []).filter(function(p) { return !live.some(function(v) { return v.userId === p.userId }) })
  }
  function clearDraft() { if (draft) draft.clear(); attachedFiles = []; whisperIds = []; replyTarget = null }
  function sendDraft() {
    if (root.actionsReady && (draft.text.trim() !== "" || attachedFiles.length))
      service.request("send", { body: draft.text, files: attachedFiles, whisperRecipientIds: whisperIds,
        replyToMessageId: replyTarget ? replyTarget.id : null })
  }
  function replyTo(message) {
    replyTarget = message
    whisperIds = message.private ? (message.recipientIds || []).filter(function(id) { return id !== root.service.session.userId }) : []
    draft.forceActiveFocus()
  }
  onDraftContextChanged: clearDraft()
  onSignedInChanged: if (!signedIn) page = "lobby"
  onForegroundOperationChanged: {
    showProgress = false
    if (foregroundOperation !== "") progressDelay.restart()
    else progressDelay.stop()
  }
  Timer { id: progressDelay; interval: 450; onTriggered: root.showProgress = root.foregroundOperation !== "" }
  Connections {
    target: root.service
    function onMessageSent() { root.clearDraft() }
    function onSessionChanged() { authView.clearSensitive() }
  }

  component Copy: Label {
    textFormat: Text.PlainText
    color: theme.foreground
    font.family: theme.fontFamily
    font.pixelSize: theme.px(12)
    wrapMode: Text.Wrap
    Layout.fillWidth: true
  }
  component Action: Button {
    id: control
    property string glyph: ""
    property string hint: text
    property bool primary: false
    property bool selected: false
    property bool chrome: true
    property color ink: theme.muted
    implicitHeight: theme.px(36)
    implicitWidth: glyph !== "" ? theme.px(36) : Math.max(theme.px(36), implicitContentWidth + theme.px(16))
    padding: theme.px(6)
    hoverEnabled: true
    font.family: theme.fontFamily
    font.pixelSize: theme.px(11)
    Accessible.name: hint
    ToolTip.visible: hovered && hint !== ""
    ToolTip.text: hint
    ToolTip.delay: 600
    background: Rectangle {
      color: control.primary ? theme.accent : control.selected ? theme.selected
        : control.hovered && control.enabled ? theme.raised : control.chrome ? theme.sunken : "transparent"
      border.width: control.chrome || control.activeFocus ? 1 : 0
      border.color: control.activeFocus ? theme.accent : theme.subtleBorder
      Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; visible: control.selected; color: theme.accent }
    }
    contentItem: Item {
      implicitWidth: control.glyph !== "" ? theme.px(20) : caption.implicitWidth
      implicitHeight: theme.px(20)
      NativeGlyph { anchors.centerIn: parent; width: theme.px(20); height: width; visible: control.glyph !== ""; kind: control.glyph; color: control.primary ? theme.background : control.ink }
      Text { id: caption; anchors.fill: parent; visible: control.glyph === ""; text: control.text; textFormat: Text.PlainText; font: control.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; color: control.primary ? theme.background : control.enabled ? theme.foreground : theme.muted }
    }
  }
  component Entry: TextField {
    id: control
    Layout.fillWidth: true
    implicitHeight: theme.px(34)
    leftPadding: theme.px(10); rightPadding: theme.px(10)
    font.family: theme.fontFamily; font.pixelSize: theme.px(12)
    color: theme.foreground; placeholderTextColor: theme.muted
    selectionColor: theme.accent; selectedTextColor: theme.sunken
    Accessible.name: placeholderText
    background: Rectangle { color: theme.sunken; border.color: control.activeFocus ? theme.accent : theme.subtleBorder }
  }
  component Rule: Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: theme.subtleBorder }

  FileDialog {
    id: chooseAttachments; title: "Attach up to 6 files (8 MB each, 20 MB total)"; fileMode: FileDialog.OpenFiles
    onAccepted: { if (selectedFiles.length <= 6) root.attachedFiles = selectedFiles.map(function(value) { return value.toString() }); else root.service.error = "Choose no more than six files." }
  }
  Dialog {
    id: participantVolume; anchors.centerIn: parent; width: Math.min(parent.width - theme.px(24), theme.px(300)); modal: true
    title: "Participant volume"; standardButtons: Dialog.Close
    contentItem: ColumnLayout {
      Copy { text: Math.round(volumeSlider.value * 100) + "%" }
      Slider { id: volumeSlider; Layout.fillWidth: true; from: 0; to: 2; stepSize: 0.05; onMoved: volumeCommit.restart() }
      Action { text: "Mute locally"; onClicked: { volumeSlider.value = 0; volumeCommit.restart() } }
    }
  }
  Timer {
    id: volumeCommit; interval: 120
    onTriggered: {
      if (!root.service || !root.service.media.connected) return
      if (!root.service.request("voice-volume", { participantId: root.volumeTarget, volume: volumeSlider.value })) restart()
    }
  }
  Dialog {
    id: shareSource; objectName: "shareSourceDialog"; anchors.centerIn: parent; width: Math.min(parent.width - theme.px(24), theme.px(300)); height: Math.min(root.height - theme.px(24), theme.px(620)); modal: true
    title: "Share a screen or application"; standardButtons: Dialog.Cancel
    font.family: theme.fontFamily; font.pixelSize: theme.px(11)
    palette.window: theme.background; palette.windowText: theme.foreground
    palette.base: theme.sunken; palette.text: theme.foreground
    palette.button: theme.raised; palette.buttonText: theme.foreground
    palette.highlight: theme.accent; palette.highlightedText: theme.sunken
    onOpened: { applicationAudio.currentIndex = 0; root.service.request("audio-applications") }
    contentItem: Flickable {
      clip: true; contentHeight: shareOptions.implicitHeight; boundsBehavior: Flickable.StopAtBounds
      ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
      ColumnLayout {
      id: shareOptions; width: parent.width; spacing: theme.px(8)
      Copy { text: "Omarchy will ask which source to share. No capture starts without your selection." }
      ComboBox { id: quality; Layout.fillWidth: true; model: ["auto", "480p", "720p", "1080p", "1440p"]; currentIndex: 0 }
      ComboBox { id: frameRate; Layout.fillWidth: true; model: [15, 30, 60]; currentIndex: 1 }
      Copy { text: "Auto uses 720p and lowers FPS under CPU/bandwidth pressure. 1440p/60 needs more CPU. Audio and microphone are separate."; color: theme.muted; font.pixelSize: theme.px(10) }
      ComboBox { id: applicationAudio; Layout.fillWidth: true; textRole: "name"; model: [{ id: "", name: "No application audio" }].concat(root.service ? root.service.audioApplications || [] : []) }
      Copy { text: "Only playing apps are listed. Native SovChat playback and the speaker mix are excluded."; font.pixelSize: theme.px(9); color: theme.muted }
      Action { text: "Refresh audio apps"; enabled: root.actionsReady; onClicked: root.service.request("audio-applications") }
      Action { text: "Monitor…"; enabled: root.actionsReady; onClicked: { shareSource.close(); root.service.request("screen-start", { source: "monitor", quality: quality.currentText, fps: Number(frameRate.currentText), audioNode: applicationAudio.model[applicationAudio.currentIndex].id }) } }
      Action { text: "Application window…"; enabled: root.actionsReady; onClicked: { shareSource.close(); root.service.request("screen-start", { source: "window", quality: quality.currentText, fps: Number(frameRate.currentText), audioNode: applicationAudio.model[applicationAudio.currentIndex].id }) } }
      }
    }
  }
  FileDialog {
    id: saveAttachment; title: "Save attachment to a new file"; fileMode: FileDialog.SaveFile
    onAccepted: root.service.request("save-attachment", { attachmentId: root.attachmentId, destination: selectedFile.toString() })
  }
  Dialog {
    id: deleteConfirm; anchors.centerIn: parent; width: Math.min(parent.width - theme.px(24), theme.px(300)); modal: true
    title: "Delete this message?"; standardButtons: Dialog.Yes | Dialog.No
    onAccepted: root.service.request("delete-message", { messageId: root.deleteId })
  }
  Dialog {
    id: recipients; anchors.centerIn: parent; width: Math.min(parent.width - theme.px(24), theme.px(300)); height: Math.min(parent.height - theme.px(40), theme.px(420)); modal: true
    title: "Message recipients"; standardButtons: Dialog.Close
    contentItem: ColumnLayout {
      Action { text: "Whole room"; onClicked: { root.whisperIds = []; root.replyTarget = null; recipients.close() } }
      ListView {
        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
        model: root.service ? root.service.currentRoomMembers || [] : []
        delegate: CheckBox {
          required property var modelData; width: ListView.view.width
          visible: root.signedIn && modelData.userId !== root.service.session.userId
          height: visible ? theme.px(34) : 0
          checked: root.whisperIds.indexOf(modelData.userId) !== -1
          contentItem: Copy { text: modelData.nickname; leftPadding: theme.px(30); verticalAlignment: Text.AlignVCenter }
          onClicked: {
            var next = root.whisperIds.filter(function(id) { return id !== modelData.userId })
            if (checked && next.length < 32) next.push(modelData.userId)
            root.whisperIds = next
            root.replyTarget = null
          }
        }
      }
    }
  }
  Dialog {
    id: emojiPicker; anchors.centerIn: parent; width: Math.min(parent.width - theme.px(24), theme.px(300)); modal: true
    title: root.reactionId ? "React to message" : "Add emoji"; standardButtons: Dialog.Close
    contentItem: ColumnLayout {
      GridLayout {
        columns: 5
        Repeater {
          model: ["😀", "😂", "❤️", "👍", "👎", "🎉", "🔥", "👀", "✅", "🙏", "☕", "👋", "🤔", "😢", "🚀"]
          Action {
            required property string modelData; text: modelData
            onClicked: {
              if (root.reactionId) root.service.request("reaction", { messageId: root.reactionId, emoji: modelData })
              else draft.insert(draft.cursorPosition, modelData)
              emojiPicker.close()
            }
          }
        }
      }
      RowLayout {
        Entry { id: customEmoji; placeholderText: "Other reaction"; maximumLength: 16 }
        Action { text: "Add"; enabled: customEmoji.text.trim() !== ""; onClicked: { if (root.reactionId) root.service.request("reaction", { messageId: root.reactionId, emoji: customEmoji.text }); else draft.insert(draft.cursorPosition, customEmoji.text); customEmoji.clear(); emojiPicker.close() } }
      }
    }
  }

  Rectangle {
    id: header
    width: parent.width; height: theme.px(46); color: theme.sunken
    Image { anchors.left: parent.left; anchors.leftMargin: theme.px(12); anchors.verticalCenter: parent.verticalCenter; width: theme.px(22); height: width; source: "assets/ico.svg"; fillMode: Image.PreserveAspectFit }
    Copy { objectName: "operationStatus"; anchors.right: closeButton.left; anchors.rightMargin: theme.px(8); anchors.verticalCenter: parent.verticalCenter; height: theme.px(16); width: theme.px(210); horizontalAlignment: Text.AlignRight; text: root.showProgress ? FeedbackPolicy.label(root.foregroundOperation) : ""; color: theme.secondary; font.pixelSize: theme.px(10); maximumLineCount: 1 }
    Action { id: closeButton; anchors.right: parent.right; height: parent.height; width: theme.px(44); glyph: "close"; hint: "Close SovChat"; chrome: false; onClicked: root.closeRequested() }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.secondary; opacity: 0.4 }
  }
  Column {
    id: notices
    anchors.top: header.bottom; width: parent.width
    Copy { width: parent.width; padding: text ? theme.px(12) : 0; visible: text !== ""; text: !root.service ? "Native service unavailable." : root.service.error || ""; color: theme.danger }
    Copy { width: parent.width; padding: text ? theme.px(12) : 0; visible: text !== ""; text: root.service ? root.service.notice || "" : ""; color: theme.secondary }
    Action { visible: !!root.service && !root.service.ready; text: "Restart native helper"; onClicked: root.service.restart() }
  }
  Item {
    id: stage
    anchors.top: notices.bottom; anchors.bottom: dock.visible ? dock.top : parent.bottom
    width: parent.width; clip: true
    AuthView {
      id: authView; anchors.fill: parent
      visible: !root.signedIn && root.page !== "settings"
      theme: root.viewTheme; service: root.service
      onAppearanceRequested: root.page = "settings"
    }

    // Roster comes from the shared service, never fabricated placeholder users.
    Flickable {
      id: lobbyViewport
      anchors.fill: parent; visible: root.signedIn && root.page === "lobby"
      contentHeight: Math.max(height, lobbyContent.implicitHeight); clip: true
      boundsBehavior: Flickable.StopAtBounds
      ColumnLayout {
        id: lobbyContent; width: parent.width; height: lobbyViewport.contentHeight; spacing: theme.px(12)
        RoomSwitcher {
          Layout.alignment: Qt.AlignHCenter; Layout.topMargin: theme.px(6)
          theme: root.viewTheme; service: root.service
          viewportWidth: root.width; viewportHeight: root.height
          onSettingsRequested: { settingsView.section = "room"; root.page = "settings" }
        }
        Repeater {
          model: ["LIVE", "LOBBY"]
          Rectangle {
            required property string modelData
            readonly property var people: root.roster(modelData)
            Layout.fillWidth: true; Layout.leftMargin: theme.px(12); Layout.rightMargin: theme.px(18)
            implicitHeight: theme.px(38 + people.length * 42); color: "transparent"; border.color: theme.subtleBorder
            ColumnLayout {
              anchors.fill: parent; anchors.margins: theme.px(8); spacing: 0
              RowLayout { Layout.fillWidth: true; spacing: theme.px(12); Copy { Layout.fillWidth: false; text: modelData; font.pixelSize: theme.px(9) } Rule {} Copy { Layout.fillWidth: false; text: String(people.length); color: theme.muted; font.pixelSize: theme.px(9) } }
              Repeater {
                model: people
                RowLayout {
                  required property var modelData; Layout.fillWidth: true; Layout.preferredHeight: theme.px(42); spacing: theme.px(10)
                  NativeAvatar { Layout.preferredWidth: theme.px(30); Layout.preferredHeight: theme.px(30); nickname: modelData.nickname; avatar: modelData.avatarImage || "" }
                  Copy { text: modelData.nickname; font.bold: true; maximumLineCount: 1; elide: Text.ElideRight }
                  Copy { Layout.fillWidth: false; text: root.signedIn && modelData.userId === root.service.session.userId ? "YOU" : ""; color: theme.muted; font.pixelSize: theme.px(9) }
                  NativeGlyph { visible: !!modelData.muted; width: theme.px(14); height: width; kind: "microphone"; color: theme.muted }
                  NativeGlyph { visible: !!modelData.deafened; width: theme.px(14); height: width; kind: "headphones"; color: theme.muted }
                  Action { glyph: "settings"; implicitWidth: theme.px(22); visible: !!modelData.participantId && modelData.userId !== root.service.session.userId; enabled: root.actionsReady && root.service.media.connected; hint: "Participant volume"; onClicked: { root.volumeTarget = modelData.participantId; volumeSlider.value = root.service.media.volumes && root.service.media.volumes[root.volumeTarget] !== undefined ? root.service.media.volumes[root.volumeTarget] : 1; participantVolume.open() } }
                }
              }
            }
          }
        }
        Repeater {
          model: root.service ? root.service.media.streams || [] : []
          RowLayout {
            required property var modelData; Layout.fillWidth: true; Layout.leftMargin: theme.px(12); Layout.rightMargin: theme.px(12)
            Copy { text: modelData.nickname + " is sharing"; maximumLineCount: 1; elide: Text.ElideRight }
            Action { text: "Watch"; enabled: root.actionsReady && root.service.media.videoRenderer; onClicked: { if (root.service.request("screen-watch", { id: modelData.id })) root.page = "stream" } }
          }
        }
        Item { Layout.fillHeight: true; Layout.preferredHeight: 0 }
        RowLayout {
          Layout.alignment: Qt.AlignHCenter; spacing: 0
          Action { glyph: "noise"; implicitWidth: theme.px(44); implicitHeight: theme.px(44); ink: theme.accent; hint: "Audio processing"; onClicked: { settingsView.section = "audio"; root.page = "settings" } }
          Action { glyph: "share"; implicitWidth: theme.px(44); implicitHeight: theme.px(44); selected: !!root.service && !!(root.service.media.sharing || root.service.media.screenPending); enabled: root.controlsReady && root.service.media.connected && root.service.media.screenSharingAvailable; hint: selected ? "Stop sharing / cancel selection" : "Share screen or application"; onClicked: selected ? root.service.request("screen-stop") : shareSource.open() }
          Action { glyph: "voice"; implicitWidth: theme.px(44); implicitHeight: theme.px(44); primary: true; hint: root.service && root.service.media.connecting ? "Cancel voice connection" : root.service && root.service.media.available ? root.service.media.connected ? "Leave voice" : "Join voice muted" : "Native runtime setup is required"; enabled: (root.service && (root.service.media.connected || root.service.media.connecting) ? root.controlsReady : root.actionsReady) && !!root.service.currentRoom && root.service.media.available; onClicked: root.service.request(root.service.media.connected || root.service.media.connecting ? "voice-leave" : "voice-join") }
        }
        Copy { Layout.bottomMargin: theme.px(5); text: root.service ? root.service.media.videoError || root.service.media.audioError || root.service.media.shareAudioError || (root.service.media.sharingAudio ? "Sharing selected application audio" : "") : ""; visible: text !== ""; horizontalAlignment: Text.AlignHCenter; color: theme.danger; font.pixelSize: theme.px(9) }
      }
    }

    ColumnLayout {
      anchors.fill: parent; visible: root.signedIn && root.page === "chat"; spacing: 0
      RowLayout {
        Layout.fillWidth: true; Layout.leftMargin: theme.px(12); Layout.rightMargin: theme.px(12); Layout.topMargin: theme.px(8); Layout.bottomMargin: theme.px(8)
        ColumnLayout { spacing: theme.px(8); Copy { text: "ROOM CHAT"; color: theme.accent; font.pixelSize: theme.px(10); font.letterSpacing: 2 } Copy { text: root.roomName; color: theme.muted; font.bold: true; font.pixelSize: theme.px(14) } }
        Action { glyph: "close"; hint: "Back to lobby"; onClicked: root.page = "lobby" }
      }
      Rule {}
      ListView {
        id: messageList; Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: theme.px(12)
        clip: true; model: root.service ? root.service.messages : []
        ScrollBar.vertical: ScrollBar { width: theme.px(4); policy: ScrollBar.AsNeeded }
        delegate: Item {
          required property var modelData
          width: messageList.width; height: Math.max(theme.px(62), messageContent.implicitHeight + theme.px(24))
          NativeAvatar { x: 0; y: theme.px(10); width: theme.px(32); height: width; nickname: modelData.nickname; avatar: root.service && root.service.avatars ? root.service.avatars[modelData.userId] || "" : "" }
          ColumnLayout {
            id: messageContent; x: theme.px(42); y: theme.px(10); width: parent.width - x; spacing: theme.px(14)
            RowLayout {
              Layout.fillWidth: true; spacing: theme.px(8)
              Copy { Layout.fillWidth: false; Layout.minimumWidth: 0; Layout.maximumWidth: Math.max(theme.px(20), Math.min(theme.px(118), messageContent.width - timestampLabel.implicitWidth - theme.px((root.signedIn && modelData.userId === root.service.session.userId ? 46 : 0) + (modelData.private ? 34 : 0) + 24))); text: modelData.nickname; font.bold: true; maximumLineCount: 1; elide: Text.ElideRight }
              Rectangle { visible: root.signedIn && modelData.userId === root.service.session.userId; implicitWidth: theme.px(38); implicitHeight: theme.px(18); radius: height / 2; color: "#3f341f"; Text { anchors.centerIn: parent; text: "YOU"; color: theme.accent; font.family: theme.fontFamily; font.pixelSize: theme.px(9); font.letterSpacing: 1 } }
              Rectangle { visible: !!modelData.private; implicitWidth: theme.px(26); implicitHeight: theme.px(18); radius: height / 2; color: "#3a2534"; Text { anchors.centerIn: parent; text: "W"; color: "#ff6fb5"; font.family: theme.fontFamily; font.pixelSize: theme.px(9) } ToolTip.text: "Private message"; ToolTip.visible: whisperHover.hovered; HoverHandler { id: whisperHover } }
              Item { Layout.fillWidth: true }
              Copy { id: timestampLabel; Layout.fillWidth: false; text: Palette.timestamp(modelData.createdAt); color: theme.muted; font.pixelSize: theme.px(9); maximumLineCount: 1 }
            }
            Copy { visible: !!modelData.replyTo; text: modelData.replyTo ? "↳ " + modelData.replyTo.nickname + ": " + modelData.replyTo.body : ""; maximumLineCount: 2; elide: Text.ElideRight; font.pixelSize: theme.px(10); color: theme.muted }
            Copy { text: modelData.body; color: modelData.private ? "#ff6fb5" : theme.foreground; font.bold: true; font.pixelSize: theme.px(13) }
            Repeater {
              model: modelData.attachments || []
              Action {
                required property var modelData; Layout.fillWidth: true
                text: "Save " + modelData.fileName; hint: "Save attachment without opening it"; enabled: root.actionsReady
                onClicked: { root.attachmentId = modelData.id; saveAttachment.open() }
              }
            }
            Flow {
              Layout.fillWidth: true; spacing: theme.px(3)
              Repeater {
                model: modelData.reactions || []
                Action {
                  required property var modelData; text: modelData.emoji + " " + modelData.count; selected: !!modelData.reactedByMe; enabled: root.actionsReady
                  onClicked: root.service.request("reaction", { messageId: messageContent.parent.modelData.id, emoji: modelData.emoji })
                }
              }
            }
            RowLayout {
              spacing: theme.px(3)
              Action { text: "Reply"; enabled: root.actionsReady; onClicked: root.replyTo(modelData) }
              Action { glyph: "smile"; hint: "React"; enabled: root.actionsReady; onClicked: { root.reactionId = modelData.id; emojiPicker.open() } }
              Action { text: "Delete"; visible: root.signedIn && modelData.userId === root.service.session.userId; enabled: root.actionsReady; onClicked: { root.deleteId = modelData.id; deleteConfirm.open() } }
            }
          }
          Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.subtleBorder }
        }
        onCountChanged: positionViewAtEnd()
      }
      Copy { visible: messageList.count === 0; Layout.margins: theme.px(12); text: "No messages in this room yet."; color: theme.muted }
      RowLayout {
        visible: root.replyTarget !== null || root.attachedFiles.length > 0; Layout.leftMargin: theme.px(12); Layout.rightMargin: theme.px(12)
        Copy { text: (root.replyTarget ? "Reply to " + root.replyTarget.nickname + " · " : "") + (root.attachedFiles.length ? root.attachedFiles.length + " attachments" : ""); font.pixelSize: theme.px(10); color: theme.secondary }
        Action { glyph: "close"; hint: "Clear reply and attachments"; onClicked: { root.replyTarget = null; root.attachedFiles = [] } }
      }
      Rectangle {
        Layout.fillWidth: true; Layout.margins: theme.px(12); implicitHeight: theme.px(46); radius: theme.px(8); color: theme.sunken; border.color: theme.border
        RowLayout {
          anchors.fill: parent; anchors.margins: theme.px(6); spacing: theme.px(3)
          Action { text: root.whisperIds.length ? "W " + root.whisperIds.length : "All ⌄"; hint: "Choose recipients"; chrome: false; enabled: root.actionsReady; onClicked: recipients.open() }
          Rectangle { implicitWidth: 1; implicitHeight: theme.px(20); color: theme.subtleBorder }
          Entry {
            id: draft; objectName: "messageDraft"; placeholderText: "Message " + root.roomName; maximumLength: 4000
            font.pixelSize: theme.px(11); leftPadding: theme.px(6); rightPadding: 0; background: Item {}
            enabled: !!root.service && root.service.ready && root.signedIn && !!root.service.currentRoom
            readOnly: !DraftPolicy.editable(root.service && root.service.ready,
              root.service ? root.service.session : null, root.service ? root.service.currentRoom : null,
              root.service && root.service.busy, root.service ? root.service.pendingOp : "")
            onAccepted: root.sendDraft()
          }
          Action { glyph: "attach"; implicitWidth: theme.px(24); chrome: false; enabled: root.actionsReady; hint: "Attach files"; onClicked: chooseAttachments.open() }
          Action { glyph: "smile"; implicitWidth: theme.px(24); chrome: false; enabled: root.actionsReady; hint: "Emoji picker"; onClicked: { root.reactionId = ""; emojiPicker.open() } }
          Action { glyph: "send"; implicitWidth: theme.px(24); chrome: false; hint: root.whisperIds.length ? "Send private message" : "Send to the whole room"; enabled: root.actionsReady && !!root.service.currentRoom && (draft.text.trim() !== "" || root.attachedFiles.length > 0); onClicked: root.sendDraft() }
        }
      }
    }

    AppearanceView {
      id: settingsView
      objectName: "appearanceView"
      anchors.fill: parent; visible: root.page === "settings"; paletteTheme: theme; service: root.service
      onBackRequested: root.page = "lobby"
      onThemeSelected: function(value) { root.themeSelected(value) }
    }
    Loader {
      id: videoView; anchors.fill: parent; active: root.page === "stream" && !!root.service && !!root.service.media.videoRenderer
      source: active ? "VideoPane.qml" : ""
      onLoaded: { item.paletteTheme = root.viewTheme; item.service = root.service; item.backRequested.connect(function() { root.service.request("screen-unwatch"); root.page = "lobby" }) }
      Binding { target: videoView.item; property: "frameName"; value: root.service ? root.service.media.frameName || "" : ""; when: videoView.status === Loader.Ready }
    }
  }
  Rectangle {
    id: dock; anchors.bottom: parent.bottom; width: parent.width; height: theme.px(64); color: theme.sunken
    visible: root.signedIn && root.page === "lobby"
    Rectangle { width: parent.width; height: 1; color: theme.secondary; opacity: 0.4 }
    RowLayout {
      anchors.fill: parent; anchors.margins: theme.px(12); spacing: theme.px(4)
      NativeAvatar { Layout.preferredWidth: theme.px(32); Layout.preferredHeight: theme.px(32); nickname: root.signedIn ? root.service.session.nickname : ""; avatar: root.signedIn ? AvatarPolicy.selfImage(root.service.session, root.service.presence, root.service.profile) : "" }
      Copy { Layout.leftMargin: theme.px(6); text: root.signedIn ? root.service.session.nickname : ""; font.bold: true; maximumLineCount: 1; elide: Text.ElideRight }
      Action { glyph: "chat"; chrome: false; implicitWidth: theme.px(30); hint: "Room chat"; onClicked: root.page = "chat" }
      Action { glyph: "microphone"; chrome: false; implicitWidth: theme.px(30); hint: root.service && root.service.media.connected ? root.service.media.muted ? "Unmute microphone" : "Mute microphone" : "Join voice to use the microphone"; enabled: root.controlsReady && root.service.media.connected; onClicked: root.service.request("voice-mute", { muted: !root.service.media.muted }) }
      Action { glyph: "headphones"; chrome: false; implicitWidth: theme.px(30); selected: !!root.service && !!root.service.media.deafened; enabled: root.controlsReady && root.service.media.connected; hint: selected ? "Undeafen" : "Deafen"; onClicked: root.service.request("voice-deafen", { deafened: !root.service.media.deafened }) }
      Action { glyph: "settings"; chrome: false; implicitWidth: theme.px(30); hint: "Settings"; onClicked: root.page = "settings" }
    }
  }
}
