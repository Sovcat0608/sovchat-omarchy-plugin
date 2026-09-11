.pragma library

function ordered(current, owned, joined) {
  var result = [], seen = {}
  ;[current, owned].concat(joined || []).forEach(function(room) {
    if (!room || typeof room.id !== "string" || !room.id || Object.prototype.hasOwnProperty.call(seen, room.id)) return
    Object.defineProperty(seen, room.id, { value: true, enumerable: true })
    result.push(room)
  })
  return result
}

function canSwitch(ready, busy, media, currentId, targetId) {
  return !!ready && !busy && !!targetId && targetId !== currentId
    && !(media && (media.connected || media.connecting || media.screenPending))
}
