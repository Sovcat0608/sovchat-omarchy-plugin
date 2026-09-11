.pragma library

function background(operation) {
  return operation === "refresh" || operation === "updates" || operation === "hello"
}

function label(operation) {
  if (background(operation)) return ""
  var labels = {
    "login": "Signing in…", "signup": "Creating account…", "logout": "Signing out…",
    "send": "Sending…", "resend": "Requesting email…", "switch": "Switching room…",
    "join-room": "Joining room…", "create-room": "Creating room…",
    "voice-join": "Connecting voice…", "voice-leave": "Leaving voice…", "voice-mute": "Updating mic…",
    "google-login": "Waiting for browser sign-in…", "audio-devices": "Finding devices…",
    "audio-settings": "Saving audio settings…", "profile": "Updating profile…",
    "room-action": "Updating room…", "reaction": "Updating reaction…",
    "delete-message": "Deleting message…", "save-attachment": "Saving attachment…",
    "screen-start": "Choose a source in Omarchy…", "screen-stop": "Stopping share…",
    "screen-watch": "Opening stream…", "screen-unwatch": "Closing stream…",
    "voice-volume": "Setting volume…", "voice-deafen": "Updating headphones…",
    "voice-idle": "", "usage": "Loading usage…",
    "audio-applications": "Finding audio apps…", "screen-volume": "Setting stream audio…",
    "output-volume": "Setting output volume…"
  }
  return labels[operation] || "Please wait…"
}
