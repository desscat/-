const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync("browser_login/index.html", "utf8").match(/<script>([\s\S]*?)<\/script>/)[1];
const key = "iread.remembered-login.v1";
const store = new Map();

function frame(blocked = false) {
  const messages = [];
  let listener;
  const parent = {postMessage: message => messages.push(message)};
  const context = {
    URL,
    window: {parent, addEventListener: (type, callback) => {listener = callback;}},
    document: {referrer: "https://example.test/"},
    location: {href: "https://example.test/component/browser_login/index.html"},
    localStorage: {
      getItem: name => {if (blocked) throw Error("blocked"); return store.get(name) || null;},
      setItem: (name, value) => {if (blocked) throw Error("blocked"); store.set(name, value);},
      removeItem: name => {if (blocked) throw Error("blocked"); store.delete(name);},
    },
  };
  vm.runInNewContext(code, context);
  return {
    call(args, origin = "https://example.test", source = parent) {
      listener({source, origin, data: {type: "streamlit:render", args}});
      return messages.at(-1)?.value;
    },
    messages,
  };
}

const login = {version: 1, username: "test-teacher", token: "fake-test-token", expires_at: Date.now() / 1000 + 3600, password: "never-save"};
const first = frame();
const savedResult = first.call({action: "save", login});
assert.equal(savedResult.status, "saved");
assert.equal(savedResult.expires_at, login.expires_at);
assert.equal(savedResult.login, null, "Save acknowledgement must not echo credentials");
assert.equal(JSON.parse(store.get(key)).password, undefined);
const nextDay = frame();
assert.equal(nextDay.call({action: "load"}).login.token, login.token);
const messageCount = nextDay.messages.length;
nextDay.call({action: "load"});
assert.equal(nextDay.messages.length, messageCount, "Identical renders must not trigger a rerun loop");
nextDay.call({action: "clear"});
assert.equal(store.has(key), false);
assert.equal(frame().call({action: "load"}).login, null);
for (const saved of ["bad-json", JSON.stringify({...login, token: ""}), JSON.stringify({...login, expires_at: Date.now() / 1000 - 1}), JSON.stringify({...login, expires_at: Date.now() / 1000 + 31 * 86400})]) {
  store.set(key, saved);
  assert.equal(frame().call({action: "load"}).login, null);
  assert.equal(store.has(key), false);
}
assert.equal(frame(true).call({action: "load"}).error, true);
first.call({action: "save", login: {...login, username: "other-teacher", token: "other-token"}});
assert.equal(frame().call({action: "load"}).login.username, "other-teacher");
const hostile = frame();
const initialCount = hostile.messages.length;
hostile.call({action: "clear"}, "https://untrusted.test");
hostile.call({action: "clear"}, "https://example.test", {});
assert.equal(hostile.messages.length, initialCount);
assert.equal(store.has(key), true);
console.log("Browser login storage checks passed");
