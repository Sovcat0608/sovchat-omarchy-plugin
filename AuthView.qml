import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Flickable {
  id: root
  required property var theme
  property var service: null
  property bool signup: false
  readonly property Item preferredFocus: email
  readonly property bool ready: !!service && service.ready && !service.busy
  signal appearanceRequested()
  clip: true
  contentHeight: form.implicitHeight + theme.px(40)
  boundsBehavior: Flickable.StopAtBounds
  function clearSensitive() { password.clear() }
  function submit() {
    if (!ready || !email.text.trim() || !password.text || (signup && nickname.text.trim().length < 2)) return
    if (service.request(signup ? "signup" : "login", { email: email.text, password: password.text,
        nickname: nickname.text, rememberMe: remember.checked && !signup,
        disconnectOtherSessions: disconnect.checked })) password.clear()
  }
  component Copy: Label {
    Layout.fillWidth: true; textFormat: Text.PlainText; wrapMode: Text.Wrap
    color: theme.muted; font.family: theme.fontFamily; font.pixelSize: theme.px(11)
  }
  component Field: TextField {
    id: field
    property string glyph: ""
    Layout.fillWidth: true; implicitHeight: theme.px(44)
    leftPadding: theme.px(40); rightPadding: theme.px(12)
    color: theme.foreground; placeholderTextColor: theme.muted
    font.family: theme.fontFamily; font.pixelSize: theme.px(12)
    selectionColor: theme.accent; selectedTextColor: theme.sunken
    Accessible.name: placeholderText
    background: Rectangle {
      color: theme.sunken; radius: theme.px(6); border.color: field.activeFocus ? theme.accent : theme.subtleBorder
      NativeGlyph { x: theme.px(12); anchors.verticalCenter: parent.verticalCenter; width: theme.px(16); height: width; kind: field.glyph; color: theme.muted }
    }
  }
  component Action: Button {
    id: action
    property bool primary: false
    Layout.fillWidth: true; implicitHeight: theme.px(44)
    font.family: theme.fontFamily; font.pixelSize: theme.px(12)
    background: Rectangle { radius: theme.px(6); color: action.primary ? theme.accent : action.hovered ? theme.raised : theme.sunken; border.color: action.activeFocus ? theme.secondary : theme.subtleBorder }
    contentItem: Text { text: action.text; textFormat: Text.PlainText; font: action.font; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: action.primary ? theme.sunken : action.enabled ? theme.foreground : theme.muted }
  }
  ColumnLayout {
    id: form
    x: theme.px(28); y: theme.px(20); width: parent.width - theme.px(56); spacing: theme.px(12)
    Item {
      Layout.fillWidth: true; implicitHeight: theme.px(110)
      Image { anchors.centerIn: parent; width: Math.min(parent.width, theme.px(190)); height: theme.px(80); source: "assets/wordmark.svg"; fillMode: Image.PreserveAspectFit; smooth: true; Accessible.name: "SovChat" }
    }
    Field { id: nickname; visible: root.signup; glyph: "people"; placeholderText: "display name"; maximumLength: 20; onAccepted: email.forceActiveFocus() }
    Field { id: email; glyph: "mail"; placeholderText: "email"; maximumLength: 254; inputMethodHints: Qt.ImhEmailCharactersOnly | Qt.ImhNoPredictiveText; onAccepted: password.forceActiveFocus() }
    Field { id: password; glyph: "lock"; placeholderText: "password"; maximumLength: 72; echoMode: TextInput.Password; inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText; onAccepted: root.submit() }
    CheckBox {
      id: remember; visible: !root.signup; enabled: !!root.service && root.service.secureStorage
      text: "Remember me"; font.family: theme.fontFamily; font.pixelSize: theme.px(11)
      contentItem: Copy { text: remember.text; leftPadding: theme.px(28); verticalAlignment: Text.AlignVCenter }
      ToolTip.visible: hovered && !enabled; ToolTip.text: "Requires an unlocked Linux Secret Service keyring."
    }
    CheckBox {
      id: disconnect; visible: !!root.service && root.service.errorCode === "SESSION_CONFLICT"
      text: "Disconnect my other device"; font.family: theme.fontFamily; font.pixelSize: theme.px(10)
      contentItem: Copy { text: disconnect.text; leftPadding: theme.px(28); wrapMode: Text.Wrap }
    }
    Action { primary: true; text: root.signup ? "Create account" : "Sign in"; enabled: root.ready && email.text.trim() !== "" && password.text !== ""; onClicked: root.submit() }
    Action { visible: !!root.service && root.service.errorCode === "LOGOUT_PENDING"; text: "Retry server sign-out"; enabled: root.ready; onClicked: root.service.request("logout") }
    Action { text: "G   Continue with Google"; enabled: root.ready; onClicked: root.service.request("google-login", { rememberMe: remember.checked && !root.signup }) }
    Action { visible: !!root.service && root.service.pendingOp === "google-login"; text: "Cancel Google sign-in"; onClicked: root.service.request("logout") }
    RowLayout {
      Layout.alignment: Qt.AlignHCenter; Layout.topMargin: theme.px(10)
      Copy { Layout.fillWidth: false; text: root.signup ? "Already have an account?" : "Need an account?" }
      Button {
        text: root.signup ? "Sign in" : "Create one"; enabled: root.ready
        font.family: theme.fontFamily; font.pixelSize: theme.px(11)
        background: Item {}
        contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: theme.foreground; font: parent.font; verticalAlignment: Text.AlignVCenter }
        onClicked: { root.signup = !root.signup; password.clear(); disconnect.checked = false }
      }
    }
    Action { visible: !!root.service && (root.service.errorCode === "EMAIL_NOT_VERIFIED" || root.service.notice.indexOf("verification") !== -1 || root.signup); text: "Resend verification email"; enabled: root.ready && email.text.trim() !== ""; onClicked: root.service.request("resend", { email: email.text }) }
    Copy { visible: root.signup; text: "Open signup · maximum 500 accounts.\nVerify your email before signing in."; horizontalAlignment: Text.AlignHCenter; font.pixelSize: theme.px(10) }
    Button {
      Layout.alignment: Qt.AlignHCenter; text: "Appearance"; font.family: theme.fontFamily; font.pixelSize: theme.px(10)
      background: Item {}
      contentItem: Copy { text: parent.text; color: theme.muted }
      onClicked: root.appearanceRequested()
    }
  }
  ScrollBar.vertical: ScrollBar { width: theme.px(4); policy: ScrollBar.AsNeeded }
}
