.pragma library
function priority(op) {
  return ["voice-mute", "voice-leave", "voice-deafen", "voice-idle", "screen-stop", "screen-unwatch", "logout"].indexOf(op) !== -1
}
function active(requests, control) {
  return Object.keys(requests).some(function(id) { return priority(requests[id].op) === control })
}
function operation(requests) {
  var ids = Object.keys(requests)
  var selected = ids.filter(function(id) { return priority(requests[id].op) })[0] || ids[0]
  return selected ? requests[selected].op : ""
}
function accepts(ready, requests, op) {
  var ops = Object.keys(requests).map(function(id) { return requests[id].op })
  return ready && ops.indexOf("logout") === -1 && ops.indexOf(op) === -1 &&
    (priority(op) || (!active(requests, true) && !active(requests, false)))
}
