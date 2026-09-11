.pragma library

// Refresh creates new objects. Only an account/room identity change should
// discard an unsent draft; JSON encoding also avoids ambiguous delimiter keys.
function contextKey(session, room) {
  return JSON.stringify([session ? session.userId : null, room ? room.id : null])
}

function editable(ready, session, room, busy, operation) {
  return !!ready && !!session && !!room
    && (!busy || operation === "refresh" || operation === "updates")
}
