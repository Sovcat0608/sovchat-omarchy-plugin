.pragma library

function selfImage(session, presence, profile) {
  if (!session || !session.userId) return ""
  // Shared session tokens deliberately omit custom photo data. Presence is
  // refreshed from the profile table and is authoritative for the current room.
  var own = (presence || []).find(function(person) { return person.userId === session.userId })
  if (own && own.avatarImage) return own.avatarImage
  if (profile && profile.avatarImage) return profile.avatarImage
  return session.avatarImage || ""
}
