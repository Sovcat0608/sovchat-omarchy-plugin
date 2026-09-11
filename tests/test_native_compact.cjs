const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const read = name => fs.readFileSync(path.join(root, "native-plugin", name), "utf8");
const feedback = {};
const palette = {};
const avatar = {};
const roomPolicy = {};
vm.runInNewContext(read("RoomPolicy.js").replace(/^\.pragma library\r?\n/, ""), roomPolicy);
vm.runInNewContext(read("AvatarPolicy.js").replace(/^\.pragma library\r?\n/, ""), avatar);
vm.runInNewContext(read("Palette.js").replace(/^\.pragma library\r?\n/, ""), palette);
vm.runInNewContext(read("FeedbackPolicy.js").replace(/^\.pragma library\r?\n/, ""), feedback);

test("own avatar uses profile-backed presence instead of session's bundled fallback", () => {
  const session = { userId: "qa", avatarImage: "avatar-1.png" };
  const presence = [{ userId: "other", avatarImage: "other-image" }, { userId: "qa", avatarImage: "custom-photo" }];
  assert.equal(avatar.selfImage(session, presence, { avatarImage: "old-photo" }), "custom-photo");
  assert.equal(avatar.selfImage(session, [], { avatarImage: "profile-photo" }), "profile-photo");
  assert.equal(avatar.selfImage(session, [], {}), "avatar-1.png");
  assert.equal(avatar.selfImage(null, presence, { avatarImage: "profile-photo" }), "");
  assert.match(read("CompactView.qml"), /AvatarPolicy\.selfImage/);
  assert.match(read("CompactView.qml"), /onSignedInChanged: if \(!signedIn\) page = "lobby"/);
});

test("desktop room switch order is current, owned, joined with stable ID deduplication", () => {
  const current = { id: "current", name: "Current" }, owned = { id: "own", name: "Owned" };
  assert.deepEqual(Array.from(roomPolicy.ordered(current, owned, [owned, current, { id: "joined" }]), r => r.id), ["current", "own", "joined"]);
  assert.equal(roomPolicy.ordered(null, null, []).length, 0);
  assert.equal(roomPolicy.ordered({ id: "__proto__" }, null, [{ id: "__proto__" }]).length, 1);
});

test("room switch interactions guard current/busy/voice targets and use native dismissal", () => {
  assert.equal(roomPolicy.canSwitch(true, false, {}, "a", "b"), true);
  for (const state of [{ connected: true }, { connecting: true }, { screenPending: true }]) assert.equal(roomPolicy.canSwitch(true, false, state, "a", "b"), false);
  assert.equal(roomPolicy.canSwitch(true, true, {}, "a", "b"), false);
  assert.equal(roomPolicy.canSwitch(true, false, {}, "a", "a"), false);
  assert.match(read("RoomSwitcher.qml"), /Popup.CloseOnEscape \| Popup.CloseOnPressOutsideParent/);
  assert.match(read("RoomSwitcher.qml"), /onCurrentIdChanged: menu.close\(\)/);
  assert.doesNotMatch(read("CompactView.qml"), /id: rooms;|property bool roomTools/);
});

test("polling, startup and update checks never announce working", () => {
  for (const op of ["refresh", "updates", "hello"]) {
    assert.equal(feedback.background(op), true);
    assert.equal(feedback.label(op), "");
  }
  assert.doesNotMatch(read("CompactView.qml"), /Working/);
});

test("all six original themes exist and reference Ember Shift has exact CSS colours", () => {
  assert.deepEqual(Array.from(palette.choices, p => p.name), ["Solar Flare", "Neon Current", "Rose Circuit", "Glacier Signal", "Ember Shift", "Night Bloom"]);
  const ember = palette.selected("ember-shift");
  assert.equal(palette.mix(ember.bottom, "#080a0b", 0.84), "#201b1d");
  assert.equal(palette.mix(ember.bottom, "#050607", 0.68), "#1b1619");
  assert.equal(ember.accent, "#ff795e");
  assert.equal(ember.secondary, "#65c7ff");
  for (const choice of palette.choices) assert.equal(palette.valid(choice.id), true);
  for (const value of [undefined, null, "", "windows", "../theme"]) {
    assert.equal(palette.valid(value), false);
    assert.equal(palette.selected(value).id, "ember-shift");
  }
});

test("native screens use service roster data and persist only plugin settings", () => {
  const view = read("CompactView.qml");
  for (const page of ["lobby", "chat", "settings"]) assert.ok(view.includes('page === "' + page + '"'));
  assert.match(view, /root\.service\.participants/);
  assert.match(view, /root\.service\.presence/);
  assert.doesNotMatch(view, /Roster preview · this account only/);
  assert.match(read("AppearanceView.qml"), /Linux · compact/);
  assert.match(read("Panel.qml"), /if \(!Palette\.valid\(value\)\) return/);
  assert.match(read("Panel.qml"), /updateEntryInline\(root\.moduleName, entry\)/);
  assert.match(read("BarWidget.qml"), /update\.available/);
  assert.match(read("NativeAvatar.qml"), /350000/);
});

test("timestamps never display malformed server values", () => {
  for (const value of [undefined, null, "", "not a date"]) assert.equal(palette.timestamp(value), "");
  assert.equal(palette.timestamp("2026-09-09T09:26:00"), "9 Sep, 09:26");
});

test("native line icons use host-independent curve antialiasing", () => {
  const glyph = read("NativeGlyph.qml");
  assert.match(glyph, /preferredRendererType: Shape\.CurveRenderer/);
  assert.match(glyph, /antialiasing: true/);
  assert.doesNotMatch(glyph, /Shape\.GeometryRenderer/);
});
test("foreground operations retain delayed feedback without changing screen geometry", () => {
  for (const op of ["login", "signup", "send", "logout", "voice-join"]) {
    assert.equal(feedback.background(op), false);
    assert.notEqual(feedback.label(op), "");
  }
  assert.match(read("CompactView.qml"), /interval: 450/);
  assert.match(read("CompactView.qml"), /height: theme\.px\(16\)/);
  assert.match(read("CompactView.qml"), /showProgress = false/);
});
test("plugin has only compact layout and retains the original Omarchy brand tokens", () => {
  const theme = read("CompactTheme.qml");
  assert.match(theme, /readonly property string layoutMode: "compact"/);
  assert.ok(theme.includes("#e8e8e8"));
  for (const hex of ["#ffca2a", "#71dce1", "#ff795e", "#65c7ff"])
    assert.ok(read("Palette.js").includes(hex));
  assert.match(read("Panel.qml"), /CompactView/);
  assert.match(read("Panel.qml"), /Style\.space\(352\)/);
  assert.doesNotMatch(read("CompactView.qml"), /toggleCompact|layoutSelector|Electron|AppImage/);
});
test("styled controls and messages retain plain-text safety and small-screen scrolling", () => {
  const view = read("CompactView.qml");
  assert.match(view, /component Action: Button/);
  assert.match(view, /component Entry: TextField/);
  assert.match(view, /Flickable/);
  assert.match(view, /textFormat: Text\.PlainText/g);
  assert.doesNotMatch(view, /Text\.RichText|Text\.AutoText/);
  assert.match(view, /focusTarget|preferredFocus/);
});
