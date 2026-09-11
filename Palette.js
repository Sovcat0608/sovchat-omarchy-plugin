.pragma library

// Authoritative pairs and base colours from SovChat/lib/theme-store.ts and
// app/globals.css (Linux interface). Ember Shift matches the supplied reference.
var choices = [
  { id: "solar-flare", name: "Solar Flare", accent: "#ffca2a", secondary: "#71dce1", bottom: "#19292c" },
  { id: "neon-current", name: "Neon Current", accent: "#5ce7ee", secondary: "#ff6e91", bottom: "#122529" },
  { id: "rose-circuit", name: "Rose Circuit", accent: "#ff6fb5", secondary: "#6fe7d7", bottom: "#221a24" },
  { id: "glacier-signal", name: "Glacier Signal", accent: "#8bd5ff", secondary: "#b9f36c", bottom: "#14242c" },
  { id: "ember-shift", name: "Ember Shift", accent: "#ff795e", secondary: "#65c7ff", bottom: "#251e21" },
  { id: "night-bloom", name: "Night Bloom", accent: "#b58cff", secondary: "#73e6b1", bottom: "#1d1b29" }
]
function valid(id) { return choices.some(function(p) { return p.id === id }) }
function selected(id) { return choices.filter(function(p) { return p.id === id })[0] || choices[4] }
function mix(a, b, fraction) {
  var result = "#"
  for (var i = 1; i < 7; i += 2) {
    var value = Math.round(parseInt(a.slice(i, i + 2), 16) * fraction + parseInt(b.slice(i, i + 2), 16) * (1 - fraction))
    result += ("0" + value.toString(16)).slice(-2)
  }
  return result
}
function timestamp(value) {
  var date = new Date(value)
  if (!value || !isFinite(date.getTime())) return ""
  return date.getDate() + " " + ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][date.getMonth()]
    + ", " + ("0" + date.getHours()).slice(-2) + ":" + ("0" + date.getMinutes()).slice(-2)
}
