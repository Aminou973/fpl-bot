"""Render the FPL 2026/27 two-team dashboard as one self-contained HTML file."""
import json
from pathlib import Path

HERE = Path(__file__).parent


def build(bundle_path=HERE / "bundle.json", out=HERE / "fpl-2026-27-dashboard.html"):
    data = json.loads(Path(bundle_path).read_text())
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    Path(out).write_text(html)
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FPL 2026/27 — Minoux_69 &amp; Minoux_41</title>
<style>
:root{
  color-scheme: dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --accent:#3987e5; --accent2:#d95926;
  --easy:#3987e5; --hard:#e34948; --neutral:#383835;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --pitch:#161d17;
}
:root[data-theme="light"]{
  color-scheme: light;
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --accent:#2a78d6; --accent2:#eb6834;
  --easy:#2a78d6; --hard:#e34948; --neutral:#f0efec;
  --good:#006300; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --pitch:#eef3ee;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:1280px;margin:0 auto;padding:24px 20px 72px}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:15px;margin:0 0 2px;letter-spacing:-.005em}
h3{font-size:13px;margin:16px 0 6px;color:var(--ink2);font-weight:600}
.sub{color:var(--muted);font-size:13px;margin:0}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;
  flex-wrap:wrap;margin-bottom:20px}
button,select,input{font:inherit;color:var(--ink);background:var(--surface);
  border:1px solid var(--ring);border-radius:8px;padding:6px 10px}
button{cursor:pointer}
button:hover{border-color:var(--muted)}
button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:14px;
  padding:16px 18px;margin-bottom:16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:16px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:14px;padding:14px 16px}
.tile .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.tile .v{font-size:27px;font-weight:600;margin-top:4px;letter-spacing:-.02em}
.tile .n{color:var(--ink2);font-size:12px;margin-top:2px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child,th.l,td.l{text-align:left}
th{color:var(--muted);font-weight:500;font-size:12px;cursor:pointer;user-select:none;
  position:sticky;top:0;background:var(--surface);z-index:2}
tbody tr:hover{background:color-mix(in oklab,var(--accent) 10%,transparent)}
.scroll{max-height:520px;overflow:auto;border:1px solid var(--grid);border-radius:10px}
.pitch{background:var(--pitch);border-radius:14px;padding:18px 10px;
  background-image:linear-gradient(var(--ring) 1px,transparent 1px);background-size:100% 25%}
.line{display:flex;justify-content:center;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.pl{width:106px;background:var(--surface);border:1px solid var(--ring);border-radius:10px;
  padding:7px 6px;text-align:center;position:relative}
.pl .nm{font-weight:600;font-size:12.5px;overflow:hidden;text-overflow:ellipsis}
.pl .mt{color:var(--muted);font-size:11px}
.pl .xp{font-size:15px;font-weight:600;margin-top:3px}
.pl.cap{outline:2px solid var(--accent);outline-offset:1px}
.pl.diff{border-color:var(--accent2)}
.badge{position:absolute;top:-7px;right:-7px;background:var(--accent);color:#fff;
  font-size:10px;font-weight:700;border-radius:6px;padding:1px 5px}
.bench{opacity:.72;margin-top:6px;border-top:1px dashed var(--axis);padding-top:12px}
.grid{border-collapse:separate;border-spacing:3px;width:auto;table-layout:fixed}
.grid td{padding:0;border:none;width:74px}
.grid th{padding:2px 0;text-align:center;cursor:default;position:static}
.grid td.l{width:auto;padding-right:8px;border:none}
.cell{width:74px;height:38px;border-radius:6px;display:flex;flex-direction:column;
  align-items:center;justify-content:center;font-size:11.5px;line-height:1.15;
  border:1px solid var(--ring)}
.cell b{font-size:12.5px;font-weight:600}
.season{border-collapse:separate;border-spacing:2px;width:auto;table-layout:fixed}
.season td,.season th{padding:0;border:none;width:34px;text-align:center}
.season th{font-size:10px;color:var(--muted);position:static;cursor:default}
.season td.l{width:44px;text-align:left;font-weight:600;font-size:12px;
  position:sticky;left:0;background:var(--surface);z-index:1;padding-right:4px}
.scell{width:34px;height:26px;border-radius:4px;display:flex;align-items:center;
  justify-content:center;font-size:10px;font-weight:600;border:1px solid var(--ring)}
.season .brk{width:8px;background:transparent}
.bar{height:16px;border-radius:0 4px 4px 0;background:var(--accent)}
.bar.alt{background:var(--accent2)}
.legend{display:flex;gap:14px;align-items:center;color:var(--ink2);font-size:12px;margin:8px 0 0;flex-wrap:wrap}
.sw{width:12px;height:12px;border-radius:3px;display:inline-block;margin-right:5px;vertical-align:-2px}
.flag{font-size:11px;padding:1px 6px;border-radius:5px;border:1px solid currentColor}
.f-crit{color:var(--critical)} .f-warn{color:var(--serious)} .f-diff{color:var(--accent2)}
.note{color:var(--ink2);font-size:12.5px;margin:8px 0 0}
.tt{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);
  border-radius:8px;padding:8px 10px;font-size:12px;box-shadow:0 6px 22px rgba(0,0,0,.28);
  z-index:50;display:none;max-width:280px}
.split{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:900px){.split{grid-template-columns:1fr}}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.hint{color:var(--muted);font-size:12px}
#paths table{table-layout:auto}
#paths td.l{white-space:normal;line-height:1.45;min-width:180px}
#paths td,#paths th{vertical-align:top}
.chip{border:1px solid var(--ring);border-radius:10px;padding:12px 14px;background:var(--plane)}
.chips{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.chip b{display:block;margin-bottom:3px}
.role{font-size:11px;border-radius:5px;padding:1px 7px;border:1px solid currentColor;margin-left:8px}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div>
    <h1>FPL 2026/27 — Minoux_69 &amp; Minoux_41</h1>
    <p class="sub" id="strap"></p>
  </div>
  <div class="row" style="margin:0"><button id="theme">Light mode</button></div>
</header>

<div class="tiles" id="tiles"></div>

<div class="card">
  <div class="row" style="justify-content:space-between">
    <div><h2 id="squadTitle">Squad</h2><p class="sub" id="squadSub"></p></div>
    <div class="tabs" id="squadTabs"></div>
  </div>
  <div class="row" id="viewTabs"></div>
  <div class="row" id="gwTabs"></div>
  <div class="pitch" id="pitch"></div>
  <p class="note" id="pitchNote"></p>
  <div class="legend">
    <span><span class="sw" style="background:var(--accent)"></span>captain</span>
    <span><span class="sw" style="background:var(--accent2)"></span>differential (under 8% owned)</span>
  </div>
</div>

<div class="split">
  <div class="card">
    <h2>Captain shortlist — gameweek <span id="capGw"></span></h2>
    <p class="sub" id="capSub"></p>
    <div class="row" id="capTabs"></div>
    <div id="capChart"></div>
    <p class="note" id="capNote"></p>
  </div>
  <div class="card">
    <h2>Where each squad stands</h2>
    <p class="sub">Projected points over the next five gameweeks, and how far each
      squad sits from the crowd.</p>
    <div id="cmpChart"></div>
    <div id="cmpTable"></div>
  </div>
</div>

<div class="card">
  <h2>Transfer plan — week by week</h2>
  <p class="sub" id="pathSub"></p>
  <div class="row" id="pathTabs"></div>
  <div id="paths"></div>
  <p class="note" id="pathNote"></p>
</div>

<div class="card">
  <h2>Fixture ticker — next five gameweeks</h2>
  <p class="sub">Colour is the official FPL difficulty rating; the opponent code is
    always shown, so nothing depends on colour alone. Hover for expected goals and
    clean-sheet probability.</p>
  <div class="row">
    <label class="hint">Sort by <select id="tickSort">
      <option value="fdr">easiest run</option>
      <option value="att">best attacking run</option>
      <option value="def">best clean-sheet run</option>
      <option value="name">club name</option>
    </select></label>
  </div>
  <div style="overflow:auto"><table class="grid" id="ticker"></table></div>
  <div class="legend">
    <span><span class="sw" style="background:color-mix(in oklab,var(--easy) 55%,var(--surface))"></span>easy (2)</span>
    <span><span class="sw" style="background:var(--neutral)"></span>average (3)</span>
    <span><span class="sw" style="background:color-mix(in oklab,var(--hard) 55%,var(--surface))"></span>hard (5)</span>
  </div>
</div>

<div class="card">
  <h2>Chip planner</h2>
  <p class="sub" id="chipSub"></p>
  <div class="chips" id="chipCards"></div>
  <h3>Best fixture runs — three consecutive gameweeks</h3>
  <div class="split">
    <div><p class="hint">First half (up to the chip deadline)</p><div id="win1"></div></div>
    <div><p class="hint">Second half</p><div id="win2"></div></div>
  </div>
  <h3>Whole season, all 38 gameweeks</h3>
  <p class="sub">The gap marks the first-set chip deadline. Scroll sideways.</p>
  <div style="overflow:auto;max-height:620px"><table class="season" id="season"></table></div>
</div>

<div class="card">
  <h2>Player explorer</h2>
  <p class="sub">Every available player. <b>3 GW</b> and <b>5 GW</b> are expected points
    over the next three and five gameweeks — sort by 3 GW when you are buying for right
    now, by 5 GW when you are building. <b>Ceil</b> reweights the explosive returns
    (goals, assists, bonus) — use it for captaincy and for Minoux_41. Click any column to sort.</p>
  <div class="row">
    <select id="fPos"><option value="">All positions</option><option>GKP</option><option>DEF</option><option>MID</option><option>FWD</option></select>
    <select id="fTeam"><option value="">All clubs</option></select>
    <label class="hint">Max £<input id="fPrice" type="number" step="0.5" min="3.5" max="16" value="16" style="width:74px"></label>
    <label class="hint">Max owned <input id="fOwn" type="number" step="1" min="0" max="100" value="100" style="width:70px">%</label>
    <label class="hint">Min start <input id="fMin" type="number" step="5" min="0" max="100" value="0" style="width:70px">%</label>
    <input id="fSearch" placeholder="Search name" style="width:150px">
    <span class="hint" id="cnt"></span>
  </div>
  <div class="scroll"><table id="tbl"></table></div>
</div>

<div class="card">
  <h2>How the numbers are built</h2>
  <p class="sub" id="method"></p>
</div>
</div>
<div class="tt" id="tt"></div>

<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const byId = Object.fromEntries(D.players.map(p => [p.id, p]));
const GWS = D.gws, G0 = GWS[0];
const NAMES = Object.keys(D.builds);
const DIFF_OWN = 8;
const fmt = (x, n = 1) => (x == null ? "–" : Number(x).toFixed(n));
// short-horizon totals: the first three gameweeks only
const H3 = GWS.slice(0, 3);
D.players.forEach(p => {
  p.xp3 = +H3.reduce((a, g) => a + (p["xp" + g] || 0), 0).toFixed(2);
  p.ceiling3 = +H3.reduce((a, g) => a + (p["cxp" + g] || 0), 0).toFixed(2);
  p.value3 = +(p.xp3 / p.price).toFixed(2);
});

/* ---------------------------------------------------------------- theme -- */
$("#theme").onclick = () => {
  const light = document.documentElement.dataset.theme === "light";
  document.documentElement.dataset.theme = light ? "dark" : "light";
  $("#theme").textContent = light ? "Light mode" : "Dark mode";
};

/* ------------------------------------------------------------- tooltips -- */
const tt = $("#tt");
function showTip(e, html) {
  tt.innerHTML = html; tt.style.display = "block";
  const r = tt.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
  tt.style.left = x + "px"; tt.style.top = y + "px";
}
const hideTip = () => tt.style.display = "none";
function tipify(el, html) {
  el.addEventListener("mousemove", e => showTip(e, html));
  el.addEventListener("mouseleave", hideTip);
}

/* ---------------------------------------------------------------- strap -- */
const dl = new Date(D.deadline);
$("#strap").textContent =
  `Gameweek ${G0} deadline ${dl.toUTCString().slice(0, 22)} UK · projections over `
  + `gameweeks ${G0}–${GWS[GWS.length - 1]} · data generated ${D.generated.slice(0, 10)}`;

/* ---------------------------------------------------------------- tiles -- */
const tiles = [];
NAMES.forEach(n => {
  const b = D.builds[n];
  tiles.push([`${n} — now`, fmt(b.current_report.xp_total, 0) + " pts",
    `${b.role === "main" ? "main" : "risk"} team · ${fmt(b.own_current, 0)}% average ownership`]);
  tiles.push([`${n} — target`, fmt(b.target_report.xp_total, 0) + " pts",
    `+${fmt(b.target_report.xp_total - b.current_report.xp_total, 0)} available · `
    + `${fmt(b.own_target, 0)}% ownership`]);
});
$("#tiles").innerHTML = tiles.map(([k, v, n]) =>
  `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`).join("");

/* ---------------------------------------------------------------- pitch -- */
let curTeam = NAMES[0], curView = "target", curGw = G0;
$("#squadTabs").innerHTML = NAMES.map(n =>
  `<button data-n="${n}" aria-pressed="${n === curTeam}">${n}</button>`).join("")
  + `<button data-n="__ref" aria-pressed="false">Reference</button>`;
$("#viewTabs").innerHTML =
  `<button data-v="target" aria-pressed="true">Recommended</button>
   <button data-v="current" aria-pressed="false">As drafted</button>`;
$("#gwTabs").innerHTML = GWS.map(g =>
  `<button data-g="${g}" aria-pressed="${g === curGw}">GW${g}</button>`).join("");

$("#squadTabs").onclick = e => { if (e.target.dataset.n) { curTeam = e.target.dataset.n; sync(); renderPitch(); } };
$("#viewTabs").onclick = e => { if (e.target.dataset.v) { curView = e.target.dataset.v; sync(); renderPitch(); } };
$("#gwTabs").onclick = e => { if (e.target.dataset.g) { curGw = +e.target.dataset.g; sync(); renderPitch(); renderCap(); } };
function sync() {
  $("#squadTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.n === curTeam));
  $("#viewTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.v === curView));
  $("#viewTabs").style.display = curTeam === "__ref" ? "none" : "flex";
  $("#gwTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", +b.dataset.g === curGw));
}
function activeSquad() {
  if (curTeam === "__ref")
    return { report: D.reference.report, label: "Reference build",
             blurb: "The best legal 15 with no constraints beyond the official rules — "
                  + "the yardstick both teams are measured against." };
  const b = D.builds[curTeam];
  return { report: curView === "target" ? b.target_report : b.current_report,
           label: curTeam + (curView === "target" ? " — recommended" : " — as drafted"),
           blurb: b.blurb };
}
function card(p, gw, isCap) {
  const el = document.createElement("div");
  const diff = p.selected_by < DIFF_OWN;
  el.className = "pl" + (isCap ? " cap" : "") + (diff ? " diff" : "");
  el.innerHTML = `${isCap ? '<span class="badge">C</span>' : ""}
    <div class="nm">${p.name}</div>
    <div class="mt">${p.team} · £${fmt(p.price)} · ${p["fx" + gw] || ""}</div>
    <div class="xp">${fmt(p["xp" + gw], 2)}</div>`;
  tipify(el, `<b>${p.name}</b> — ${p.pos}, ${p.team}, £${fmt(p.price)}m<br>
    Owned by ${fmt(p.selected_by, 1)}% · start chance ${Math.round(p.start_share * 100)}%<br>
    2025/26: ${p.hist_starts} starts, ${p.hist_pts} points<br>
    GW${gw} ${p["fx" + gw]} — expected ${fmt(p["xp" + gw], 2)}, ceiling ${fmt(p["cxp" + gw], 2)}<br>
    <span style="color:var(--muted)">Points split (GW${G0}):</span>
    appearance ${fmt(p.b_app, 2)}, goals ${fmt(p.b_goals, 2)}, assists ${fmt(p.b_assists, 2)},
    clean sheet ${fmt(p.b_cs, 2)}, saves ${fmt(p.b_saves, 2)},
    def. contribution ${fmt(p.b_dc, 2)}, bonus ${fmt(p.b_bonus, 2)}
    ${p.news ? `<br><span style="color:var(--critical)">${p.news}</span>` : ""}`);
  return el;
}
function renderPitch() {
  const a = activeSquad(), g = a.report.gws[curGw];
  const xi = g.xi.map(i => byId[i]), bench = g.bench.map(i => byId[i]);
  const lines = { GKP: [], DEF: [], MID: [], FWD: [] };
  xi.forEach(p => lines[p.pos].push(p));
  const host = $("#pitch"); host.innerHTML = "";
  ["GKP", "DEF", "MID", "FWD"].forEach(k => {
    const row = document.createElement("div"); row.className = "line";
    lines[k].sort((x, y) => y["xp" + curGw] - x["xp" + curGw])
      .forEach(p => row.appendChild(card(p, curGw, p.id === g.captain)));
    host.appendChild(row);
  });
  const b = document.createElement("div"); b.className = "line bench";
  bench.forEach(p => b.appendChild(card(p, curGw, false)));
  host.appendChild(b);
  const form = ["DEF", "MID", "FWD"].map(k => lines[k].length).join("-");
  const own = xi.concat(bench).reduce((s, p) => s + p.selected_by, 0) / 15;
  $("#squadTitle").textContent = a.label;
  $("#squadSub").textContent = a.blurb;
  $("#pitchNote").innerHTML =
    `GW${curGw}: <b>${form}</b>, £${fmt(a.report.cost)}m, ${fmt(g.xp, 1)} projected points
     including the captain (<b>${byId[g.captain].name}</b>). Average ownership
     ${fmt(own, 1)}%. Bench order left to right. Hover any player for the full breakdown.`;
}

/* ------------------------------------------------------- captain chart -- */
let capMode = NAMES[0];
$("#capTabs").innerHTML = NAMES.map(n =>
  `<button data-c="${n}" aria-pressed="${n === capMode}">${n}</button>`).join("");
$("#capTabs").onclick = e => {
  if (!e.target.dataset.c) return;
  capMode = e.target.dataset.c;
  $("#capTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.c === capMode));
  renderCap();
};
function renderCap() {
  $("#capGw").textContent = curGw;
  const risk = D.builds[capMode].role === "risk";
  const key = risk ? "cxp" : "xp";
  let cands = D.players.filter(p =>
    (p.pos === "MID" || p.pos === "FWD") && p.status === "a" && p.start_share > 0.5);
  if (risk) cands = cands.filter(p => p.selected_by < 25);
  cands = cands.sort((a, b) => b[key + curGw] - a[key + curGw]).slice(0, 8);
  const max = cands[0][key + curGw];
  $("#capSub").textContent = risk
    ? "Ranked on ceiling, and capped at 25% ownership — a captain everyone owns cannot win you rank."
    : "Ranked on expected points. The safe pick is usually the right pick for the main team.";
  $("#capChart").innerHTML = `<table>${cands.map(p => `
    <tr><td class="l" style="width:160px">${p.name} <span class="hint">${p.team} · ${fmt(p.selected_by, 0)}%</span></td>
    <td style="width:100%"><div class="bar${risk ? " alt" : ""}" style="width:${(p[key + curGw] / max * 100).toFixed(1)}%"></div></td>
    <td style="width:104px">${fmt(p["xp" + curGw], 2)} → <b>${fmt(p["xp" + curGw] * 2, 1)}</b></td></tr>`).join("")}</table>`;
  $("#capNote").textContent = risk
    ? "Bar length is the ceiling score; the number is expected points, then doubled. Minoux_41 should take the highest ceiling it can stomach."
    : "Bar length and number are both expected points, then doubled. Triple captain multiplies by three instead.";
}

/* ------------------------------------------------------ squad compare --- */
function renderCmp() {
  const rows = [{ label: "Reference build", v: D.reference.report.xp_total, own: null, alt: false }];
  NAMES.forEach(n => {
    const b = D.builds[n];
    rows.push({ label: n + " recommended", v: b.target_report.xp_total, own: b.own_target, alt: b.role === "risk" });
    rows.push({ label: n + " as drafted", v: b.current_report.xp_total, own: b.own_current, alt: b.role === "risk" });
  });
  const max = Math.max(...rows.map(r => r.v));
  $("#cmpChart").innerHTML = `<table>${rows.map(r => `
    <tr><td class="l" style="width:190px">${r.label}</td>
    <td style="width:100%"><div class="bar${r.alt ? " alt" : ""}" style="width:${(r.v / max * 100).toFixed(1)}%"></div></td>
    <td style="width:60px"><b>${fmt(r.v, 0)}</b></td>
    <td style="width:60px" class="hint">${r.own == null ? "" : fmt(r.own, 0) + "%"}</td></tr>`).join("")}</table>`;
  $("#cmpTable").innerHTML = `<p class="note">Blue is the main team's scale, orange the
    risk team's. The right-hand column is average ownership: Minoux_69 wants that number
    close to the crowd, Minoux_41 wants it far below.</p>`;
}

/* --------------------------------------------------------- upgrade path -- */
let curPath = NAMES[0];
$("#pathTabs").innerHTML = NAMES.map(n =>
  `<button data-n="${n}" aria-pressed="${n === curPath}">${n}</button>`).join("");
$("#pathTabs").onclick = e => {
  if (!e.target.dataset.n) return;
  curPath = e.target.dataset.n;
  $("#pathTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.n === curPath));
  renderPaths();
};
function renderPlan(u) {
  const w = u.plan.weeks, hp = u.hit_policy || {};
  const r = i => byId[i];
  const rows = w.map(k => `<tr>
    <td class="l"><b>GW${k.gw}</b></td>
    <td class="l">${k.out.map(i => r(i).name).join(", ") || "<span class='hint'>roll</span>"}</td>
    <td class="l">${k.in.map(i => `${r(i).name} <span class='hint'>£${fmt(r(i).price)}</span>`).join(", ") || "–"}</td>
    <td class="l">${r(k.captain).name}</td>
    <td>${k.free_transfers}</td>
    <td>${k.hits ? `<span style="color:var(--critical)">−${k.hits * 4}</span>` : "0"}</td>
    <td>£${fmt(k.bank)}m</td>
    <td><b>${fmt(k.xp, 1)}</b></td></tr>`).join("");
  const chips = (u.chips || []);
  const bestTc = chips.reduce((a, c) => (!a || c.triple_captain > a.triple_captain ? c : a), null);
  const bestBb = chips.reduce((a, c) => (!a || c.bench_boost > a.bench_boost ? c : a), null);
  return `<table>
    <thead><tr><th class="l">Week</th><th class="l">Out</th><th class="l">In</th>
      <th class="l">Captain</th><th>FT left</th><th>Hit</th><th>Bank</th><th>Points</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="note">Starting from ${u.free_transfers} free transfer${u.free_transfers === 1 ? "" : "s"}
      and £${fmt(u.bank)}m in the bank. Free transfers bank up to five.
      ${hp.took_hits ? `A hit is worth it here — it gains ${hp.gain_over_no_hit} points against a
        ${hp.threshold}-point threshold.`
        : hp.rejected_hits ? `A hit was considered and rejected: it gained only
        ${hp.gain_over_no_hit} points against a ${hp.threshold}-point threshold.`
        : "No hit is worth taking in this window."}
      ${bestTc ? `Best triple captain in the window: GW${bestTc.gw} on ${bestTc.captain}
        (+${fmt(bestTc.triple_captain, 1)} extra). Best bench boost: GW${bestBb.gw}
        (+${fmt(bestBb.bench_boost, 1)}).` : ""}</p>`;
}
function renderPaths() {
  const u = D.builds[curPath], base = u.current_report.xp_total;
  $("#pathSub").textContent = u.blurb;
  if (u.plan) {
    $("#paths").innerHTML = renderPlan(u);
    $("#pathNote").innerHTML = `Every row is a decision the optimiser would actually make:
      it can bank a transfer, spend one, or pay a −4 when the gain clears this team's threshold.`;
    return;
  }
  $("#paths").innerHTML = `<table>
    <thead><tr><th class="l">Changes</th><th class="l">Out</th><th class="l">In</th>
      <th>Cost</th><th>5-GW points</th><th>Gain</th></tr></thead>
    <tbody>
      <tr><td class="l">keep as drafted</td><td class="l">–</td><td class="l">–</td>
        <td>£${fmt(u.current_report.cost)}m</td><td>${fmt(base, 0)}</td><td>–</td></tr>
      ${u.paths.map(p => p.infeasible ? `<tr>
        <td class="l">${p.k}</td>
        <td class="l hint" colspan="5">not enough changes to satisfy this team's brief —
          Minoux_41 has to drop Haaland and reach nine sub-8% players</td></tr>` : `<tr>
        <td class="l">${p.k}</td>
        <td class="l">${p.out.map(i => byId[i].name).join(", ") || "–"}</td>
        <td class="l">${p.in.map(i => `${byId[i].name} <span class='hint'>£${fmt(byId[i].price)} · ${fmt(byId[i].selected_by, 0)}%</span>`).join(", ") || "–"}</td>
        <td>£${fmt(p.cost)}m</td><td>${fmt(p.xp_total, 0)}</td>
        <td style="color:var(--good)">+${fmt(p.xp_total - base, 0)}</td></tr>`).join("")}
    </tbody></table>`;
  $("#pathNote").innerHTML = `Transfers are unlimited and free until the gameweek ${G0}
    deadline. After that you get one a week, bankable up to five — if a move gains less
    than about three points over five gameweeks, roll the transfer instead.`;
}

/* -------------------------------------------------------- fixture ticker -- */
function cellColor(fdr) {
  if (fdr <= 2) return `color-mix(in oklab,var(--easy) ${fdr === 1 ? 78 : 55}%,var(--surface))`;
  if (fdr === 3) return "var(--neutral)";
  return `color-mix(in oklab,var(--hard) ${fdr === 5 ? 78 : 55}%,var(--surface))`;
}
function renderTicker() {
  const mode = $("#tickSort").value;
  const clubs = Object.keys(D.fixture_grid);
  const score = c => {
    const r = D.fixture_grid[c].filter(Boolean);
    if (!r.length) return 99;
    if (mode === "fdr") return r.reduce((a, x) => a + x.fdr, 0) / r.length;
    if (mode === "att") return -r.reduce((a, x) => a + x.xgf, 0) / r.length;
    if (mode === "def") return r.reduce((a, x) => a + x.xga, 0) / r.length;
    return c;
  };
  clubs.sort((a, b) => (mode === "name" ? a.localeCompare(b) : score(a) - score(b)));
  $("#ticker").innerHTML =
    `<thead><tr><th class="l"></th>${GWS.map(g => `<th>GW${g}</th>`).join("")}</tr></thead>
     <tbody>${clubs.map(c => `<tr><td class="l"><b>${c}</b></td>` +
      D.fixture_grid[c].map((x, i) => {
        if (!x) return `<td><div class="cell" style="background:var(--neutral)">–</div></td>`;
        return `<td><div class="cell" style="background:${cellColor(x.fdr)}"
          data-tip="${c} ${x.home ? "vs" : "at"} ${x.opp} · GW${GWS[i]}|expected goals for ${x.xgf}, against ${x.xga}|clean-sheet chance ${(Math.exp(-x.xga) * 100).toFixed(0)}%">
          <b>${x.opp}</b><span style="color:var(--ink2)">${x.home ? "H" : "A"} · ${x.fdr}</span></div></td>`;
      }).join("") + "</tr>").join("")}</tbody>`;
  $("#ticker").querySelectorAll("[data-tip]").forEach(el =>
    tipify(el, el.dataset.tip.split("|").join("<br>")));
}
$("#tickSort").onchange = renderTicker;

/* ----------------------------------------------------------- chip planner */
const CHIP_GW = 19;
function runs(from, to, len) {
  const out = [];
  Object.entries(D.season_grid).forEach(([club, row]) => {
    for (let s = from - 1; s + len <= to; s++) {
      const win = row.slice(s, s + len);
      const flat = win.flat().filter(Boolean);
      if (!flat.length) continue;
      out.push({
        club, gw: s + 1, len,
        fdr: flat.reduce((a, x) => a + x.fdr, 0) / flat.length,
        xgf: flat.reduce((a, x) => a + x.xgf, 0) / flat.length,
        games: flat.length,
      });
    }
  });
  const best = {};
  out.forEach(r => { if (!best[r.club] || r.fdr < best[r.club].fdr) best[r.club] = r; });
  return Object.values(best).sort((a, b) => a.fdr - b.fdr).slice(0, 8);
}
function winTable(rows) {
  const max = Math.max(...rows.map(r => 5 - r.fdr));
  return `<table>${rows.map(r => `<tr>
    <td class="l" style="width:52px"><b>${r.club}</b></td>
    <td class="l hint" style="width:96px">GW${r.gw}–${r.gw + r.len - 1}</td>
    <td style="width:100%"><div class="bar" style="width:${((5 - r.fdr) / max * 100).toFixed(1)}%"></div></td>
    <td style="width:78px">${fmt(r.fdr, 2)} avg</td></tr>`).join("")}</table>`;
}
function renderChips() {
  const cd = new Date(D.chip_deadline);
  $("#chipSub").innerHTML = `Two full sets this season — Wildcard, Free Hit, Triple Captain
    and Bench Boost in each. <b>The first set expires ${cd.toUTCString().slice(0, 16)} 13:30 GMT,
    before gameweek ${CHIP_GW}</b>, and anything unused is lost. Do not hoard.`;
  $("#chipCards").innerHTML = [
    ["Wildcard", "Hold it for a structural problem, not two injuries. Around gameweeks 6–9 the early-season picture is honest and the promoted sides have sorted themselves out. On Minoux_41 you can fire it earlier — the risk team is supposed to move."],
    ["Triple Captain", "A premium attacker, at home, against a weak defence, ideally in a double gameweek. Watch the captain shortlist: play it when the leader is clearly ahead of the pack, not merely first."],
    ["Bench Boost", "Needs all 15 playing, so pair it with a wildcard the week before that deliberately builds a strong bench, and aim it at a double gameweek."],
    ["Free Hit", "Blank-gameweek insurance. Keep one for a week you would otherwise field seven players. Doubles and blanks are not in the fixture list yet — they appear once cup rounds are scheduled."],
  ].map(([k, v]) => `<div class="chip"><b>${k}</b><span class="hint">${v}</span></div>`).join("");
  $("#win1").innerHTML = winTable(runs(1, CHIP_GW - 1, 3));
  $("#win2").innerHTML = winTable(runs(CHIP_GW, 38, 3));
}
function renderSeason() {
  const clubs = Object.keys(D.season_grid).sort();
  const head = `<tr><th class="l"></th>` + Array.from({ length: 38 }, (_, i) =>
    (i === CHIP_GW - 1 ? `<th class="brk"></th>` : "") + `<th>${i + 1}</th>`).join("") + `</tr>`;
  const body = clubs.map(c => `<tr><td class="l">${c}</td>` +
    D.season_grid[c].map((cells, i) => {
      const brk = i === CHIP_GW - 1 ? `<td class="brk"></td>` : "";
      if (!cells || !cells.length)
        return brk + `<td><div class="scell" style="background:var(--neutral);color:var(--muted)">–</div></td>`;
      const avg = cells.reduce((a, x) => a + x.fdr, 0) / cells.length;
      const lbl = cells.length > 1 ? cells.length + "×" : cells[0].opp;
      return brk + `<td><div class="scell" style="background:${cellColor(Math.round(avg))}"
        data-tip="${c} · GW${i + 1}|${cells.map(x => (x.home ? "vs " : "at ") + x.opp + " (FDR " + x.fdr + ")").join("|")}">${lbl}</div></td>`;
    }).join("") + "</tr>").join("");
  $("#season").innerHTML = `<thead>${head}</thead><tbody>${body}</tbody>`;
  $("#season").querySelectorAll("[data-tip]").forEach(el =>
    tipify(el, el.dataset.tip.split("|").join("<br>")));
}

/* -------------------------------------------------------- player table --- */
const COLS = [
  ["name", "Player", "l"], ["pos", "Pos", "l"], ["team", "Club", "l"],
  ["price", "£", ""], ["selected_by", "Owned %", ""], ["start_share", "Start %", ""],
  ["xp" + G0, "GW" + G0, ""], ["xp3", "3 GW", ""], ["xp_total", "5 GW", ""],
  ["ceiling3", "Ceil 3", ""], ["ceiling_total", "Ceil 5", ""],
  ["value", "Pts / £m", ""], ["hist_pts", "25/26 pts", ""],
];
let sortKey = "xp_total", sortDir = -1;
[...new Set(D.players.map(p => p.team))].sort().forEach(t =>
  $("#fTeam").insertAdjacentHTML("beforeend", `<option>${t}</option>`));
function renderTable() {
  const pos = $("#fPos").value, team = $("#fTeam").value,
    maxP = +$("#fPrice").value, maxO = +$("#fOwn").value,
    minS = +$("#fMin").value / 100, q = $("#fSearch").value.toLowerCase();
  const rows = D.players.filter(p =>
    (!pos || p.pos === pos) && (!team || p.team === team) &&
    p.price <= maxP && p.selected_by <= maxO && p.start_share >= minS &&
    (!q || p.name.toLowerCase().includes(q)));
  rows.sort((a, b) => (a[sortKey] > b[sortKey] ? 1 : a[sortKey] < b[sortKey] ? -1 : 0) * sortDir);
  $("#cnt").textContent = rows.length + " players";
  $("#tbl").innerHTML = `<thead><tr>${COLS.map(([k, l, c]) =>
    `<th class="${c}" data-k="${k}">${l}${sortKey === k ? (sortDir < 0 ? " ↓" : " ↑") : ""}</th>`).join("")}<th>Flag</th></tr></thead>
    <tbody>${rows.slice(0, 400).map(p => `<tr>
      <td class="l">${p.name}</td><td class="l">${p.pos}</td><td class="l">${p.team}</td>
      <td>${fmt(p.price)}</td><td>${fmt(p.selected_by, 1)}</td>
      <td>${Math.round(p.start_share * 100)}</td>
      <td>${fmt(p["xp" + G0], 2)}</td><td>${fmt(p.xp3, 1)}</td><td>${fmt(p.xp_total, 1)}</td>
      <td>${fmt(p.ceiling3, 1)}</td><td>${fmt(p.ceiling_total, 1)}</td>
      <td>${fmt(p.value, 2)}</td><td>${p.hist_pts}</td>
      <td class="l">${p.status !== "a" ? '<span class="flag f-crit">doubt</span>'
        : p.start_share < 0.5 ? '<span class="flag f-warn">rotation</span>'
        : p.selected_by < DIFF_OWN ? '<span class="flag f-diff">differential</span>' : ""}</td>
      </tr>`).join("")}</tbody>`;
  $("#tbl").querySelectorAll("th[data-k]").forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = -1; }
    renderTable();
  });
}
["fPos", "fTeam", "fPrice", "fOwn", "fMin", "fSearch"].forEach(id =>
  $("#" + id).addEventListener("input", renderTable));

/* ---------------------------------------------------------------- method -- */
$("#method").innerHTML = `
  Every player gets a per-start rate for each scoring component — goals, assists, clean
  sheets, goals conceded, saves, defensive contribution, bonus and cards — estimated from
  their 2025/26 gameweek-by-gameweek record, blended with expected goals and expected
  assists so a hot or cold finishing run is not extrapolated, and shrunk toward what a
  player at that price normally returns. Minutes are modelled as the chance of being
  available multiplied by the chance of starting when available, so an injury-hit season
  does not permanently brand a now-fit player a rotation risk. Club attack and defence
  ratings come from 2025/26 goals and expected goals; newly promoted clubs get typical
  promoted-side ratings until they have played. Each fixture then scales the attacking
  components by that match's expected goals and the clean-sheet components by a Poisson
  clean-sheet probability. The ceiling score reweights the explosive components upward,
  because a captain or a differential is bought for its upside rather than its median.
  Both squads are then chosen by an exact integer program over five gameweeks at once —
  15 players, 2/5/5/3, at most three per club, £100.0m, a legal XI and one captain each
  week — with Minoux_69 locking Haaland in and leaning toward well-owned players, and
  Minoux_41 barring him, requiring at least nine players under 8% ownership, and
  optimising ceiling instead of expected points. Once real 2026/27 gameweeks are played
  the model folds them in automatically and the estimates sharpen.`;

sync(); renderPitch(); renderCap(); renderCmp(); renderPaths();
renderTicker(); renderChips(); renderSeason(); renderTable();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print(build())
