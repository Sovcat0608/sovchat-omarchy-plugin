const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const policy = {};
const source = fs.readFileSync(path.join(root, "native-plugin/DraftPolicy.js"), "utf8");
vm.runInNewContext(source.replace(/^\.pragma library\r?\n/, ""), policy);
const account = { userId: "qa-user", nickname: "Tester" };
const room = { id: "qa-room", name: "QA" };

test("routine session and room object replacements preserve the draft context", () => {
  const key = policy.contextKey(account, room);
  assert.equal(policy.contextKey({ ...account, nickname: "Renamed" }, { ...room, name: "Renamed" }), key);
});

test("account switch, room switch, sign-out and room removal clear context", () => {
  const key = policy.contextKey(account, room);
  for (const [session, currentRoom] of [
    [{ userId: "another" }, room], [account, { id: "another" }],
    [null, room], [account, null], [null, null],
  ]) assert.notEqual(policy.contextKey(session, currentRoom), key);
  assert.notEqual(policy.contextKey({ userId: "a\nb" }, { id: "c" }),
    policy.contextKey({ userId: "a" }, { id: "b\nc" }));
});

test("background refresh and update checks do not interrupt typing", () => {
  for (const operation of ["refresh", "updates"])
    assert.equal(policy.editable(true, account, room, true, operation), true);
  assert.equal(policy.editable(true, account, room, false, ""), true);
});

test("send and room/account mutations freeze the draft until acknowledged", () => {
  for (const operation of ["send", "switch", "create-room", "join-room", "logout", "login", "voice-join", "unknown"])
    assert.equal(policy.editable(true, account, room, true, operation), false);
  for (const [ready, session, currentRoom] of [[false, account, room], [true, null, room], [true, account, null]])
    assert.equal(policy.editable(ready, session, currentRoom, false, ""), false);
});

test("native panel wires identity-based clearing and protects submit while busy", () => {
  const panel = fs.readFileSync(path.join(root, "native-plugin/CompactView.qml"), "utf8");
  assert.match(panel, /import "DraftPolicy\.js" as DraftPolicy/);
  assert.match(panel, /readonly property string draftContext: DraftPolicy\.contextKey/);
  assert.match(panel, /onDraftContextChanged: clearDraft\(\)/);
  assert.match(panel, /onMessageSent\(\) \{ root\.clearDraft\(\) \}/);
  assert.match(panel, /function clearDraft\(\).*draft\.clear\(\).*attachedFiles = \[\].*whisperIds = \[\].*replyTarget = null/);
  assert.doesNotMatch(panel, /onCurrentRoomChanged\(\).*draft\.clear/);
  assert.doesNotMatch(panel, /onSessionChanged\(\).*draft\.clear/);
  assert.match(panel, /readOnly: !DraftPolicy\.editable/);
  assert.match(panel, /onAccepted: root\.sendDraft\(\)/);
  assert.match(panel, /if \(root\.actionsReady && \(draft\.text\.trim\(\) !== "" \|\| attachedFiles\.length\)\)/);
});
