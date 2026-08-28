'use strict';
// Functional check of the dashboard's Live tab: run the dashboard <script>
// under a minimal DOM stub whose fetch() serves site/live.json in a
// three-beat sequence - a live snapshot, then an empty one, then the live
// snapshot again - and assert each state rendered correctly.
// Run:  node tools/dash_live_check.js [site/live.json]
const fs = require("fs");
const path = require("path");

const snapFile = process.argv[2] || path.join(__dirname, "..", "site", "live.json");
const liveSnap = JSON.parse(fs.readFileSync(snapFile, "utf8"));
const snaps = [liveSnap, {}, liveSnap];   // one per fetch() call, in order
let fetchN = 0;
global.fetch = async () => {
  const payload = snaps[Math.min(fetchN++, snaps.length - 1)];
  return {ok: true, status: 200, json: async () => payload};
};

function mkEl() {
  return {innerHTML: "", textContent: "", dataset: {}, value: "",
          style: {setProperty() {}, color: "", getPropertyValue: () => ""},
          classList: {add() {}, remove() {}, toggle() {}, contains: () => false},
          addEventListener() {}, insertAdjacentHTML() {}, appendChild() {},
          setAttribute() {}, getAttribute: () => null, focus() {},
          querySelector: () => mkEl(), querySelectorAll: () => [],
          getContext: () => new Proxy({}, {get: () => () => ({width: 0})})};
}
const store = {};
function el(sel) { return (store[sel] = store[sel] || mkEl()); }
global.document = {
  querySelector: el, querySelectorAll: () => [],
  getElementById: id => el("#" + id),
  addEventListener() {},
  createElement: () => mkEl(),
  createElementNS: () => mkEl(),
  documentElement: {dataset: {}, style: {getPropertyValue: () => ""}},
};
global.getComputedStyle = () => ({getPropertyValue: () => ""});
global.matchMedia = () => ({matches: false, addEventListener() {}});
global.requestAnimationFrame = () => 0;
global.window = global;
global.addEventListener = () => {};      // bare addEventListener(...) in the script
global.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
let tick = null;
global.setInterval = (fn) => (tick = fn, 0);

/* The dashboard template keeps its data as `const D = __DATA__` and 'python
   dashboard.py' substitutes the token when it writes site/index.html from
   site/bundle.json. Running the raw script, substitute the same bundle. */
const dashScr = fs.readFileSync(
  path.join(__dirname, "..", "fplbot", "dashboard.py"), "utf8");
const bundle = JSON.parse(fs.readFileSync(
  path.join(__dirname, "..", "site", "bundle.json"), "utf8"));
const js = dashScr.slice(dashScr.indexOf("<script>") + 8,
                         dashScr.lastIndexOf("</scr" + "ipt>"))
  .replace("__DATA__", JSON.stringify(bundle));
let bootErr = null;
try { new Function(js)(); }          // load path: fetch() #0 -> live snapshot
catch (e) { bootErr = e; }

function fail(when, miss, html) {
  console.error(`live tab, ${when}: missing`, miss, "\n---\n" + html.slice(0, 300));
  process.exit(1);
}

// fetch #0 was served during boot; assert the live render landed.
setTimeout(() => {
  if (bootErr) { console.error("dashboard script failed to load:", bootErr); process.exit(1); }
  const liveHtml = el("#liveBody").innerHTML;
  const miss = ["Live points", "Proj final", "Saka", "Palmer", "in play"]
    .filter(w => !liveHtml.includes(w));
  if (miss.length) fail("live snapshot render", miss, liveHtml);
  console.log("fetch #0: live state rendered,", liveHtml.length, "chars");

  tick();                            // fetch #1: empty payload -> empty state
}, 60);

setTimeout(() => {
  const sub = el("#liveSub").textContent, emptyHtml = el("#liveBody").innerHTML;
  if (!sub.includes("Nothing in play") || emptyHtml !== "") {
    console.error("empty payload did not reset the tab. sub:", JSON.stringify(sub),
                  "body:", JSON.stringify(emptyHtml.slice(0, 200)));
    process.exit(1);
  }
  console.log("fetch #1: empty state rendered (", sub.length, "chars )");

  tick();                            // fetch #2: live snapshot again
}, 140);

setTimeout(() => {
  const liveHtml = el("#liveBody").innerHTML;
  const miss = ["Live points", "Proj final", "Saka", "Palmer", "in play"]
    .filter(w => !liveHtml.includes(w));
  if (miss.length) fail("live re-render", miss, liveHtml);
  console.log("fetch #2: live state restored,", liveHtml.length, "chars - OK");
  process.exit(0);
}, 240);