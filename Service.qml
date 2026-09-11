import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "ControlPolicy.js" as ControlPolicy

Item {
  id: root
  property var shell: null
  property var manifest: null
  property bool ready: false
  property var pendingRequests: ({})
  property bool roomTransition: false
  readonly property bool busy: roomTransition || Object.keys(pendingRequests).length !== 0
  readonly property bool controlBusy: ControlPolicy.active(pendingRequests, true)
  readonly property string pendingOp: ControlPolicy.operation(pendingRequests)
  property var session: null
  property var currentRoom: null
  property var joinedRooms: []
  property var messages: []
  property var avatars: ({})
  property var profile: ({})
  property var ownedRoom: null
  property var roomCodes: ({})
  property var currentRoomMembers: []
  property var ownedRoomMembers: []
  property var ownedRoomBans: []
  property var presence: []
  property var participants: []
  property var usage: ({})
  property var streamUsage: ({})
  property var devices: ({ inputs: [], outputs: [] })
  property var audioApplications: []
  property bool secureStorage: false
  property string errorCode: ""
  property var media: ({ available: false, connected: false, muted: true })
  property var update: ({ available: false })
  property string error: ""
  property string updateError: ""
  property string notice: ""
  property bool updateDue: false
  property int serial: 0
  signal messageSent()
  IdleMonitor {
    enabled: root.ready && !!root.media.connected
    timeout: 300
    respectInhibitors: false
    onIsIdleChanged: root.request("voice-idle", { idle: isIdle })
  }
  IdleMonitor {
    enabled: root.ready && !!root.media.connected && !!root.media.audioOptions && root.media.audioOptions.afkMinutes > 0
    timeout: root.media.audioOptions ? Math.max(1, root.media.audioOptions.afkMinutes || 0) * 60 : 60
    respectInhibitors: false
    onIsIdleChanged: if (isIdle) { root.request("voice-leave"); root.notice = "Left voice because you were idle." }
  }
  IdleMonitor {
    enabled: root.ready && !!root.media.sharing
    timeout: 900
    respectInhibitors: false
    onIsIdleChanged: if (isIdle) { root.request("screen-stop"); root.notice = "Stopped sharing after 15 minutes idle." }
  }

  function resetSession() {
    session = null
    roomTransition = false
    currentRoom = null
    joinedRooms = []
    messages = []
    avatars = ({})
    profile = ({}); ownedRoom = null; roomCodes = ({})
    currentRoomMembers = []; ownedRoomMembers = []; ownedRoomBans = []
    presence = []; participants = []; usage = ({}); streamUsage = ({}); audioApplications = []
    media = ({ available: false, connected: false, muted: true })
  }

  function request(op, data) {
    if (!ControlPolicy.accepts(ready, pendingRequests, op)) return false
    if (op !== "refresh" && op !== "updates" && op !== "hello") {
      error = ""
      errorCode = ""
      notice = ""
    }
    if (serial >= 2147483647) { failProtocol(); return false }
    var id = ++serial
    var next = Object.assign({}, pendingRequests)
    next[id] = { op: op, deadline: Date.now() + (op === "google-login" ? 220000 : op === "screen-start" ? 120000 : 65000) }
    pendingRequests = next
    helper.write(JSON.stringify({ id: id, op: op, data: data || {} }) + "\n")
    return true
  }

  function receive(line) {
    var response
    try { response = JSON.parse(line) } catch (_) { failProtocol(); return }
    if (!response || typeof response !== "object") { failProtocol(); return }
    if (response.event === "snapshot" && response.result) { applyResult(response.result); return }
    if (response.event === "notice") { error = String(response.error || ""); return }
    if (response.event === "media" && response.media) {
      media = response.media
      return
    }
    // Logout clears private presentation immediately, before network revocation.
    if (response.event === "session" && response.session === null) {
      resetSession()
      return
    }
    var pending = pendingRequests[response.id]
    if (!pending || typeof response.ok !== "boolean") { failProtocol(); return }
    var op = pending.op
    var next = Object.assign({}, pendingRequests)
    delete next[response.id]
    pendingRequests = next
    if (!response.ok) {
      errorCode = String(response.code || "")
      if (response.signedOut) resetSession()
      if (response.media) media = response.media
      if (op === "updates") updateError = String(response.error || "Update check failed.")
      else if (response.code !== "CANCELLED") error = String(response.error || "SovChat request failed.")
      if (response.code === "VOICE_REVOCATION_PENDING") Qt.callLater(function() { root.request("refresh") })
      if (updateDue) Qt.callLater(root.checkUpdates)
      return
    }
    var result = response.result || {}
    applyResult(result)
    if (result.sent) messageSent()
    if (result.changed || (op === "hello" && session) || ["login", "google-login", "switch", "join-room", "create-room", "room-action", "send"].indexOf(op) !== -1)
      Qt.callLater(function() { root.request("refresh") })
    if (op === "hello") updateDue = true
    if (updateDue) Qt.callLater(root.checkUpdates)
  }

  function applyResult(result) {
    if (Object.prototype.hasOwnProperty.call(result, "roomTransition")) roomTransition = result.roomTransition === true
    if (Object.prototype.hasOwnProperty.call(result, "secureStorage")) secureStorage = result.secureStorage
    for (var key of ["profile", "ownedRoom", "roomCodes", "currentRoomMembers", "ownedRoomMembers", "ownedRoomBans", "presence", "participants", "usage", "streamUsage", "devices", "audioApplications"])
      if (Object.prototype.hasOwnProperty.call(result, key)) root[key] = result[key]
    if (Object.prototype.hasOwnProperty.call(result, "session")) {
      if (!result.session) resetSession()
      session = result.session
    }
    if (Object.prototype.hasOwnProperty.call(result, "currentRoom")) currentRoom = result.currentRoom
    if (result.joinedRooms) joinedRooms = result.joinedRooms
    if (result.messages) messages = result.messages
    if (result.avatars) avatars = result.avatars
    if (result.media) media = result.media
    if (result.update) { update = result.update; updateError = "" }
    if (result.notice) notice = String(result.notice)
  }

  function checkUpdates() { if (request("updates")) updateDue = false }
  function failProtocol() {
    error = "The native helper stopped responding safely. Restart it and sign in again."
    helper.running = false
    killDeadline.restart()
    ready = false
    pendingRequests = ({})
    resetSession()
  }
  function restart() {
    if (helper.running) return
    resetSession()
    error = ""
    helper.running = true
  }

  Process {
    id: helper
    command: [Quickshell.env("SOVCHAT_NATIVE_PYTHON") || "/usr/bin/python3", "-B", "-u",
              decodeURIComponent(Qt.resolvedUrl("runtime/launch.py").toString().replace(/^file:\/\//, ""))]
    stdinEnabled: true
    running: true
    onStarted: { root.ready = true; root.pendingRequests = ({}); root.request("hello") }
    stdout: SplitParser { onRead: function(data) { root.receive(data) } }
    stderr: SplitParser { onRead: function(data) {} }
    onExited: function(exitCode) {
      root.ready = false
      root.pendingRequests = ({})
      root.resetSession()
      killDeadline.stop()
      if (root.error === "") root.error = "Native helper stopped. Restart it to sign in again."
    }
  }
  Timer {
    interval: 500; repeat: true; running: root.busy
    onTriggered: {
      var now = Date.now()
      if (Object.keys(root.pendingRequests).some(function(id) { return root.pendingRequests[id].deadline < now })) root.failProtocol()
    }
  }
  Timer { id: killDeadline; interval: 5000; onTriggered: if (helper.running) helper.signal(9) }
  Timer { interval: 1800000; repeat: true; running: root.ready; onTriggered: { root.updateDue = true; root.checkUpdates() } }
  Component.onDestruction: helper.running = false
}
