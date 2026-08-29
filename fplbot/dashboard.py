"""Render the FPL dashboard as one self-contained, responsive HTML file."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def build(bundle_path=None, out=None):
    bundle_path = Path(bundle_path or HERE / "site" / "bundle.json")
    out = Path(out or HERE / "site" / "index.html")
    data = json.loads(bundle_path.read_text())
    out.write_text(TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":"))),
                   encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark light">
<title>FPL — Minoux_69 &amp; Minoux_41</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  color-scheme: dark;
  /* official FPL brand: deep purple plane, neon green + cyan accents */
  --plane:#23052a; --surface:#310839; --raised:#3d0c46;
  --ink:#ffffff; --ink2:#e3d2ea; --muted:#b298bf;
  --grid:rgba(255,255,255,.08); --axis:rgba(255,255,255,.15); --ring:rgba(255,255,255,.11);
  --s1:#00ff87; --s2:#05f0ff; --s3:#e90052;
  --easy:#00c46a; --hard:#e90052; --neutral:rgba(255,255,255,.10);
  --good:#00ff87; --warning:#ffd449; --serious:#ff7a59; --critical:#ff4d6d;
  --deemph:#6e547e; --pitch:#0c2a1c;
  --plcard:#0b1f15; --plmuted:#9fc4ae; --plstripe:rgba(255,255,255,.045);
  --glow:0 0 14px rgba(0,255,135,.25);
}
:root[data-theme="light"]{
  color-scheme: light;
  --plane:#f4eff6; --surface:#ffffff; --raised:#f1e7f4;
  --ink:#1e0524; --ink2:#54425e; --muted:#8a7495;
  --grid:#e9dfee; --axis:#d4c3da; --ring:rgba(30,5,36,.12);
  --s1:#00a35a; --s2:#0891b2; --s3:#d61e63;
  --easy:#00a35a; --hard:#d61e63; --neutral:#e6dae9;
  --good:#00a35a; --warning:#c78a00; --serious:#d96a3d; --critical:#d61e63;
  --deemph:#c4b3cc; --pitch:#dcefe4;
  --plcard:#ffffff; --plmuted:#6b8a78; --plstripe:rgba(0,0,0,.035);
  --glow:0 0 14px rgba(0,163,90,.20);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:104px}
body{margin:0;background:radial-gradient(1100px 520px at 75% -8%,
  rgba(90,12,104,.55) 0%, transparent 60%),var(--plane);color:var(--ink);
  font:14px/1.5 Sora,system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-text-size-adjust:100%}
::selection{background:var(--s1);color:#0b0210}
.wrap{max-width:1300px;margin:0 auto;padding:0 18px 80px}

/* ---------------------------------------------------------------- header */
.top{position:sticky;top:0;z-index:40;padding-top:14px;
  background:rgba(24,2,28,.82);backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px)}
:root[data-theme="light"] .top{background:rgba(255,255,255,.85)}
.top::after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;
  background:linear-gradient(90deg,var(--s1) 0%,var(--s2) 55%,var(--s3) 100%)}
.topin{max-width:1300px;margin:0 auto;padding:0 18px 10px}
.titlerow{display:flex;justify-content:space-between;align-items:center;gap:10px}
.titlerow>div{min-width:0;flex:1}
h1{font-size:17px;margin:0;letter-spacing:.02em;text-transform:uppercase;
  font-weight:800;display:flex;align-items:center;gap:9px}
.crest{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;
  border-radius:9px;background:linear-gradient(135deg,var(--s1),#00c46a);
  color:#0b0210;font-size:16px;box-shadow:var(--glow);flex:none}
.sub{color:var(--muted);font-size:12.5px;margin:2px 0 0}
nav{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}
nav::-webkit-scrollbar{display:none}
/* tier 1 - group pills, one per area of the dashboard */
#nav{position:relative;margin-top:12px}
#nav a{color:var(--ink2);text-decoration:none;font-size:12.5px;font-weight:700;
  letter-spacing:.02em;padding:6.5px 14px;border-radius:999px;flex:none;
  border:1px solid transparent;white-space:nowrap}
#nav a:hover{color:var(--ink);border-color:var(--ring)}
#nav a[aria-current="true"]{background:linear-gradient(135deg,var(--s1),#00c46a);
  color:#0b0210;border-color:transparent;box-shadow:var(--glow)}
/* tier 2 - the active group's tabs */
#subnav{position:relative;margin-top:11px;gap:2px;
  border-bottom:1px solid var(--grid)}
#subnav a{color:var(--muted);text-decoration:none;font-size:13px;font-weight:600;
  padding:8px 11px;white-space:nowrap;flex:none}
#subnav a:hover{color:var(--ink)}
#subnav a[aria-current="true"]{color:var(--s1)}

h2{font-size:16px;margin:0;letter-spacing:-.005em;font-weight:700}
h3{font-size:11.5px;margin:18px 0 8px;color:var(--muted);font-weight:700;
  text-transform:uppercase;letter-spacing:.08em}
button,select,input{font:inherit;color:var(--ink);background:var(--raised);
  border:1px solid var(--ring);border-radius:999px;padding:7px 13px;min-height:36px}
button{cursor:pointer;font-weight:600}
button:hover{border-color:var(--s1);color:var(--s1)}
button[aria-pressed="true"]{background:var(--s1);border-color:var(--s1);color:#0b0210}
:focus-visible{outline:2px solid var(--s1);outline-offset:2px}
section{scroll-margin-top:104px}
section[hidden]{display:none}
.card{background:linear-gradient(165deg,rgba(255,255,255,.045),transparent 45%),var(--surface);
  border:1px solid var(--ring);border-radius:18px;
  padding:18px 20px;margin:16px 0;box-shadow:0 12px 34px rgba(10,0,14,.35)}
:root[data-theme="light"] .card{box-shadow:0 10px 26px rgba(30,5,36,.08)}
.card>header{display:flex;justify-content:space-between;align-items:flex-start;
  gap:12px;flex-wrap:wrap;margin-bottom:10px}
.tabs{display:flex;gap:6px;flex-wrap:wrap}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.hint{color:var(--muted);font-size:12px}
.note{color:var(--ink2);font-size:12.5px;margin:10px 0 0}
.empty{color:var(--muted);font-size:13px;padding:22px 4px;text-align:center;
  border:1px dashed var(--axis);border-radius:12px}

/* ------------------------------------------------------------ stat tiles */
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:10px}
.tile{position:relative;overflow:hidden;background:var(--surface);
  border:1px solid var(--ring);border-radius:16px;padding:13px 15px}
.tile::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;
  background:linear-gradient(90deg,var(--s1),var(--s2));opacity:.65}
.tile .k{color:var(--muted);font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.09em}
.tile .v{font-size:27px;font-weight:800;margin-top:3px;letter-spacing:-.02em}
.tile .n{color:var(--ink2);font-size:12px;margin-top:2px}
.tile.hero{background:linear-gradient(140deg,rgba(0,255,135,.16) 0%,
  rgba(5,240,255,.10) 55%,transparent 100%),var(--surface);
  border-color:color-mix(in oklab,var(--s1) 40%,transparent)}
.tile.hero::before{opacity:1;height:4px}
.tile.hero .v{font-size:46px;line-height:1.05;font-weight:800}
.up{color:var(--good)} .down{color:var(--critical)}

/* ---------------------------------------------------------------- tables */
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
th,td{text-align:right;padding:7px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child,th.l,td.l{text-align:left}
th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;
  letter-spacing:.05em;position:sticky;top:0;
  background:var(--surface);z-index:2}
th[data-k]{cursor:pointer;user-select:none}
tbody tr:hover{background:color-mix(in oklab,var(--s1) 9%,transparent)}
.scroll{max-height:520px;overflow:auto;border:1px solid var(--grid);border-radius:12px}
.xscroll{overflow-x:auto;-webkit-overflow-scrolling:touch}

/* ----------------------------------------------------------------- pitch */
.teams2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.pitch{border-radius:16px;padding:16px 10px;border:1px solid rgba(0,255,135,.18);
  background:
    repeating-linear-gradient(90deg,var(--plstripe) 0 44px,transparent 44px 88px),
    radial-gradient(120% 90% at 50% -10%,rgba(0,255,135,.10),transparent 55%),
    var(--pitch)}
:root[data-theme="light"] .pitch{border-color:rgba(0,163,90,.25)}
.line{display:flex;justify-content:center;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.pl{width:98px;background:var(--plcard);border:1px solid var(--ring);
  border-left:3px solid var(--club,var(--axis));border-radius:10px;
  padding:6px 5px 7px;text-align:center;position:relative;cursor:default;
  box-shadow:0 4px 14px rgba(0,0,0,.28)}
:root[data-theme="light"] .pl{box-shadow:0 3px 10px rgba(30,5,36,.12)}
.pl .nm{font-weight:700;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pl .mt{color:var(--plmuted);font-size:10.5px;margin-top:1px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.pl .fx{display:inline-block;margin-top:3px;font-size:10px;padding:1px 5px;
  border-radius:4px;border:1px solid var(--ring)}
.pl .xp{font-size:15px;font-weight:800;margin-top:3px;font-variant-numeric:tabular-nums}
.pl.cap{outline:2px solid var(--s1);outline-offset:1px}
.pl.diff::after{content:"";position:absolute;top:5px;right:5px;width:6px;height:6px;
  border-radius:50%;background:var(--s3)}
.pl.flagged .nm{color:var(--critical)}
.badge{position:absolute;top:-7px;left:-6px;background:var(--s1);color:#0b0210;
  font-size:10px;font-weight:800;border-radius:6px;padding:1px 5px;box-shadow:var(--glow)}
.badge.v{background:var(--raised);color:var(--ink2);border:1px solid var(--ring);box-shadow:none}
.pl.vice{outline:1px dashed var(--muted);outline-offset:1px}
.bench{opacity:.75;margin-top:4px;border-top:1px dashed var(--axis);padding-top:10px}

/* -------------------------------------------------------------- fixtures */
.grid{border-collapse:separate;border-spacing:3px;width:auto;table-layout:fixed}
.grid td{padding:0;border:none;width:70px}
.grid th{padding:2px 0;text-align:center;position:static;background:none;font-size:11px}
.grid td.l{width:44px;padding-right:6px;border:none;position:sticky;left:0;
  background:var(--surface);z-index:1}
.cell{width:70px;height:36px;border-radius:6px;display:flex;flex-direction:column;
  align-items:center;justify-content:center;font-size:11px;line-height:1.15;
  border:1px solid var(--ring)}
.cell b{font-size:12px}
.season{border-collapse:separate;border-spacing:2px;width:auto;table-layout:fixed}
.season td,.season th{padding:0;border:none;width:32px;text-align:center}
.season th{font-size:9.5px;color:var(--muted);position:static;background:none}
.season td.l{width:42px;text-align:left;font-weight:600;font-size:11.5px;
  position:sticky;left:0;background:var(--surface);z-index:1;padding-right:4px}
.scell{width:32px;height:24px;border-radius:4px;display:flex;align-items:center;
  justify-content:center;font-size:9.5px;font-weight:600;border:1px solid var(--ring)}
.season .brk{width:9px;background:transparent}

/* ------------------------------------------------------------ bar rows */
.bar{height:14px;border-radius:0 4px 4px 0;background:var(--s1)}
.bar.alt{background:var(--s2)}
.bar.neg{background:var(--critical)}
.barrow td{border-bottom:1px solid var(--grid)}

/* ---------------------------------------------------------------- misc */
.legend{display:flex;gap:14px;align-items:center;color:var(--ink2);font-size:12px;
  margin-top:10px;flex-wrap:wrap}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px;vertical-align:-1px}
.lk{width:14px;height:2px;border-radius:2px;display:inline-block;margin-right:6px;vertical-align:3px}
.flag{font-size:10.5px;padding:1px 6px;border-radius:5px;border:1px solid currentColor}
.f-crit{color:var(--critical)} .f-warn{color:var(--serious)} .f-diff{color:var(--s2)}
.chips{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}
.chip{border:1px solid var(--ring);border-radius:12px;padding:11px 13px;
  background:linear-gradient(150deg,rgba(0,255,135,.06),transparent 55%),var(--raised)}
.chip b{display:block;margin-bottom:3px}
.tt{position:fixed;pointer-events:none;background:var(--raised);border:1px solid var(--ring);
  border-radius:12px;padding:9px 11px;font-size:12px;box-shadow:0 8px 28px rgba(0,0,0,.45);
  z-index:60;display:none;max-width:min(300px,80vw);line-height:1.45}
.tt b{color:var(--ink)}
.split{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.foot{max-width:1300px;margin:0 auto;padding:0 18px 34px;color:var(--muted);
  font-size:12px;line-height:1.6}
.foot .st{margin:0 4px 0 0}
svg{display:block;max-width:100%}
.axis{fill:var(--muted);font-size:10.5px}
.gl{stroke:var(--grid);stroke-width:1}
.al{stroke:var(--axis);stroke-width:1}

/* --------------------------------------------------------------- mobile */
@media(max-width:860px){
  .split,.teams2{grid-template-columns:1fr}
}
@media(max-width:640px){
  .autogrid{grid-template-columns:1fr 1fr}
}

/* ==================================================== motion & upgrade */
/* every animation honours the visitor's reduced-motion preference */
@media (prefers-reduced-motion: no-preference){
  html{scroll-behavior:smooth}
  body,.card,.tile,.top{transition:background-color .35s ease,color .35s ease}

  /* reveal on scroll: sections/cards/tiles fade and rise in */
  .reveal{opacity:0;transform:translateY(14px)}
  .reveal.in{opacity:1;transform:none;transition:opacity .55s cubic-bezier(.2,.7,.3,1),
    transform .55s cubic-bezier(.2,.7,.3,1)}

  /* tab bars: a glowing underline slides under the active sub tab */
  #nav a,#subnav a{transition:color .25s}
  #navcursor,#subcursor{position:absolute;bottom:0;height:2.5px;border-radius:2px;
    background:var(--s1);box-shadow:0 0 10px var(--s1);
    transition:left .3s cubic-bezier(.3,.8,.3,1),width .3s cubic-bezier(.3,.8,.3,1);
    pointer-events:none;display:none}

  /* stat tiles count up on first paint */
  .tile .v{transition:opacity .4s}
  .tile.hero .v{font-variant-numeric:tabular-nums}

  /* bars grow from zero when they enter the viewport */
  .bar{transform-origin:left;animation:barGrow .7s cubic-bezier(.2,.7,.3,1) backwards}
  @keyframes barGrow{from{transform:scaleX(0)}}

  /* pitch cards stagger in */
  .pl{animation:plIn .4s cubic-bezier(.2,.7,.3,1) backwards}
  @keyframes plIn{from{opacity:0;transform:translateY(8px) scale(.96)}}
  .pl:hover{transform:translateY(-2px);box-shadow:0 8px 22px rgba(0,0,0,.35);
    transition:transform .18s,box-shadow .18s}
  #cd.urgent .u{animation:pulse 1.6s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
}
@media (prefers-reduced-motion: reduce){
  .reveal{opacity:1 !important;transform:none !important}
  #navcursor,#subcursor{display:none !important}
}

/* ---- these are structure, not motion: styled for everyone, motion or not */
.iochip{display:inline-flex;align-items:center;gap:4px;border-radius:999px;
  padding:2px 9px;margin:1px 3px 1px 0;font-size:12px;font-weight:700;
  border:1px solid var(--ring)}
.iochip.in{background:color-mix(in oklab,var(--s1) 16%,var(--surface));
  color:var(--s1);border-color:color-mix(in oklab,var(--s1) 45%,transparent)}
.iochip.out{background:color-mix(in oklab,var(--s3) 15%,var(--surface));
  color:var(--s3);border-color:color-mix(in oklab,var(--s3) 40%,transparent)}
.iochip.roll{background:var(--raised);color:var(--ink2);font-weight:500}

/* applied-but-not-yet-published transfer banner (squads go public at the deadline) */
.pending{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 10px;
  padding:8px 12px;border-radius:10px;font-size:12px;color:var(--ink2);
  border:1px solid color-mix(in oklab,var(--s1) 35%,transparent);
  background:color-mix(in oklab,var(--s1) 8%,var(--surface))}
.pending .hint{margin-left:auto}

/* deadline countdown */
#cd{display:flex;align-items:baseline;gap:6px;font-variant-numeric:tabular-nums}
#cd .u{font-size:26px;font-weight:800;letter-spacing:-.02em;color:var(--s1)}
#cd .l{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
#cd.urgent .u{color:var(--serious)}

/* status badges */
.st{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;font-weight:600;
  padding:3px 9px;border-radius:999px;border:1px solid var(--ring);background:var(--raised)}
.st .dot{width:7px;height:7px;border-radius:50%;background:var(--muted);flex:none}
.st.ok .dot{background:var(--good);box-shadow:0 0 6px color-mix(in oklab,var(--good) 60%,transparent)}
.st.warn .dot{background:var(--warning)}
.st.bad .dot{background:var(--critical)}
.autogrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:10px}
.autocell{border:1px solid var(--ring);border-radius:14px;padding:12px 14px;
  background:linear-gradient(150deg,rgba(5,240,255,.05),transparent 60%),var(--raised)}
.autocell .k{color:var(--muted);font-size:10.5px;font-weight:600;text-transform:uppercase;
  letter-spacing:.07em;display:flex;justify-content:space-between;align-items:center;gap:6px}
.autocell .v{font-size:19px;font-weight:800;margin-top:4px;letter-spacing:-.01em}
.autocell .n{color:var(--ink2);font-size:12px;margin-top:2px}
@media(max-width:640px){
  .wrap{padding:0 12px 72px}
  .topin{padding:0 12px}
  h1{font-size:15.5px;line-height:1.25}
  #theme{padding:5px 9px;min-height:30px;font-size:12.5px}
  .top{padding-top:10px}
  nav a{padding:6px 11px;font-size:12px}
  #subnav a{padding:7px 9px;font-size:12.5px}
  .card{padding:13px 13px;border-radius:12px}
  .tiles{grid-template-columns:1fr 1fr;gap:8px}
  .tile .v{font-size:22px}
  .tile.hero .v{font-size:34px}
  .pl{width:calc(20% - 6px);min-width:62px;padding:5px 3px 6px}
  .pl .nm{font-size:11px}
  .pl .mt{font-size:9.5px}
  .pl .fx{display:none}
  .pl .xp{font-size:13px}
  .line{gap:4px}
  .hide-s{display:none !important}
  th,td{padding:6px 6px;font-size:12.5px}
  .cell{width:58px;height:34px;font-size:10px}
  .grid td{width:58px}
}
</style>
</head>
<body>

<div class="top">
  <div class="topin">
    <div class="titlerow">
      <div>
        <h1><span class="crest">⚽</span>FPL 2026/27 — Minoux_69 &amp; Minoux_41</h1>
        <p class="sub" id="strap"></p>
      </div>
      <button id="theme" aria-label="Toggle colour theme">Light</button>
    </div>
    <nav id="nav"><span id="navcursor"></span></nav>
    <nav id="subnav"><span id="subcursor"></span></nav>
  </div>
</div>

<div class="wrap">

<section id="overview">
  <div class="tiles" id="tiles"></div>
  <div class="card" id="autoCard">
    <header><div>
      <h2>Automation</h2>
      <p class="sub">The bot's own state — live squad, transfer budget and what the
        auto-submitter will do at the deadline.</p>
    </div>
    <div id="cd" aria-live="polite"></div></header>
    <div class="autogrid" id="autoGrid"></div>
    <p class="note" id="autoNote"></p>
  </div>
  <div class="card">
    <header><div>
      <h2>Season</h2>
      <p class="sub">Gameweek points against the field average, and overall rank.</p>
    </div></header>
    <div class="split">
      <div><h3>Points per gameweek</h3><div id="ptsChart"></div></div>
      <div><h3>Overall rank</h3><div id="rankChart"></div></div>
    </div>
    <p class="note" id="seasonNote"></p>
  </div>
</section>

<section id="squads">
  <div class="card">
    <header>
      <div><h2>Squads</h2><p class="sub" id="squadSub"></p></div>
      <div class="tabs" id="viewTabs"></div>
    </header>
    <div class="row" id="gwTabs"></div>
    <div class="teams2" id="pitches"></div>
    <div class="legend">
      <span><span class="sw" style="background:var(--s1)"></span>captain</span>
      <span><span class="sw" style="background:var(--s2)"></span>differential, under 8% owned</span>
      <span class="hint">dashed outline = vice-captain</span>
      <span class="hint">the colour strip on each card is the club</span>
    </div>
  </div>
</section>

<section id="plan">
  <div class="card">
    <header>
      <div><h2>Transfer plan</h2><p class="sub" id="planSub"></p></div>
      <div class="tabs" id="planTabs"></div>
    </header>
    <div class="xscroll" id="planBody"></div>
    <p class="note" id="planNote"></p>
  </div>
</section>

<section id="captain">
  <div class="split">
    <div class="card">
      <header><div><h2>Captain — gameweek <span id="capGw"></span></h2>
        <p class="sub" id="capSub"></p></div>
        <div class="tabs" id="capTabs"></div></header>
      <div id="capChart"></div>
      <p class="note" id="capNote"></p>
    </div>
    <div class="card">
      <header><div><h2>Template exposure</h2>
        <p class="sub">The most-owned players in the game, and whether you hold them.
          Not owning a popular player is a bet, the same as owning a rare one.</p></div></header>
      <div id="tmplBody"></div>
    </div>
  </div>
</section>

<section id="value">
  <div class="card">
    <header><div><h2>Value</h2>
      <p class="sub">Price against projected points over the next five gameweeks.
        The line is the best available at each price. Your players are highlighted.</p></div>
      <div class="row" style="margin:0">
        <select id="scPos"><option value="">All positions</option>
          <option>GKP</option><option>DEF</option><option>MID</option><option>FWD</option></select>
      </div>
    </header>
    <div id="scatter"></div>
    <div class="legend">
      <span><span class="sw" style="background:var(--s1)"></span>Minoux_69</span>
      <span><span class="sw" style="background:var(--s2)"></span>Minoux_41</span>
      <span><span class="sw" style="background:var(--deemph)"></span>everyone else</span>
      <span><span class="lk" style="background:var(--s3)"></span>best available at each price</span>
    </div>
  </div>
</section>

<section id="fixtures">
  <div class="card">
    <header><div><h2>Fixture ticker</h2>
      <p class="sub">Official difficulty rating. The opponent code is always shown, so
        nothing depends on colour alone.</p></div>
      <div class="row" style="margin:0">
        <label class="hint">Sort <select id="tickSort">
          <option value="fdr">easiest run</option>
          <option value="att">best for attackers</option>
          <option value="def">best for clean sheets</option>
          <option value="name">club name</option>
        </select></label>
      </div>
    </header>
    <div class="xscroll"><table class="grid" id="ticker"></table></div>
    <div class="legend">
      <span><span class="sw" style="background:color-mix(in oklab,var(--easy) 55%,var(--surface))"></span>easy</span>
      <span><span class="sw" style="background:var(--neutral)"></span>average</span>
      <span><span class="sw" style="background:color-mix(in oklab,var(--hard) 55%,var(--surface))"></span>hard</span>
    </div>
  </div>
</section>

<section id="chips">
  <div class="card">
    <header><div><h2>Chips</h2><p class="sub" id="chipSub"></p></div></header>
    <div id="chipArmed"></div>
    <div class="chips" id="chipCards"></div>
    <div class="row" id="chipTabs" style="margin-top:16px"></div>
    <h3>When to play each chip</h3>
    <div id="chipPicks"></div>
    <h3>Every gameweek, scored</h3>
    <div id="chipStrips"></div>
    <p class="note" id="chipNote"></p>
    <h3>Best three-gameweek fixture runs</h3>
    <div class="split">
      <div><p class="hint">Before the first-set deadline</p><div id="win1"></div></div>
      <div><p class="hint">After it</p><div id="win2"></div></div>
    </div>
    <h3>Whole season</h3>
    <p class="sub">The gap marks the first-set chip deadline. Scroll sideways.</p>
    <div class="xscroll" style="max-height:560px"><table class="season" id="season"></table></div>
  </div>
</section>

<section id="livescore">
  <div class="card">
    <header><div><h2>Live gameweek</h2>
      <p class="sub" id="liveSub">Scores, players and mini-leagues while the game is being
        played. Refreshes automatically — the numbers are as fresh as the watcher's last run.</p></div>
      <span class="hint" id="liveAge"></span></header>
    <div id="liveBody"></div>
  </div>
</section>

<section id="price">
  <div class="card">
    <header><div><h2>Price radar</h2>
      <p class="sub">FPL prices move on an accumulator: net transfers fill a threshold that
        scales with ownership. The engine watches the flow hourly and projects which prices
        move in the next ~3 days — it has no inside knowledge, and the planner pays it off
        only in saved budget, never in picks.</p></div></header>
    <div id="priceBody"></div>
  </div>
</section>

<section id="elite">
  <div class="card">
    <header><div><h2>Elite template</h2>
      <p class="sub" id="eliteSub"></p></div>
      <span class="hint" id="eliteMeta"></span></header>
    <div class="split">
      <div><h3>Top-50 template squad</h3><div id="eliteBody"></div></div>
      <div>
        <h3>Elite captains</h3><div id="eliteCaps"></div>
        <h3>Moves into elite squads</h3><div id="eliteIns"></div>
        <h3>Moves out</h3><div id="eliteOuts"></div>
      </div>
    </div>
    <p class="note" id="eliteNote"></p>
  </div>
</section>

<section id="accuracy">
  <div class="card">
    <header><div><h2>Model accuracy</h2>
      <p class="sub">Every projection is stored before the deadline and graded once the
        gameweek finishes. This is the model marking its own homework in public.</p></div></header>
    <div id="accBody"></div>
  </div>
  <div class="card" id="engines">
    <header><div><h2>Engine checks</h2>
      <p class="sub">Each engine grades itself against reality. A check that fails
        stays advisory — no engine is trusted until it has earned it.</p></div></header>
    <div id="engineBody"></div>
  </div>
</section>

<section id="players">
  <div class="card">
    <header><div><h2>Players</h2>
      <p class="sub"><b>3 GW</b> and <b>5 GW</b> are expected points. <b>Ceil</b> weights
        goals, assists and bonus more heavily — use it for captaincy and for Minoux_41.</p></div></header>
    <div class="row">
      <select id="fPos"><option value="">All positions</option>
        <option>GKP</option><option>DEF</option><option>MID</option><option>FWD</option></select>
      <select id="fTeam"><option value="">All clubs</option></select>
      <select id="fOwnQuick"><option value="">Any ownership</option>
        <option value="8">Differentials, under 8%</option>
        <option value="25">Under 25%</option></select>
      <label class="hint">Max £<input id="fPrice" type="number" step="0.5" min="3.5" max="16" value="16" style="width:72px"></label>
      <input id="fSearch" placeholder="Search" style="width:130px">
      <span class="hint" id="cnt"></span>
    </div>
    <div class="scroll"><table id="tbl"></table></div>
  </div>
</section>

<section id="changes">
  <div class="card">
    <header><div><h2>What changed</h2>
      <p class="sub">Since the previous run of the bot.</p></div></header>
    <div id="changeBody"></div>
  </div>
  <div class="card">
    <header><div><h2>How the numbers are built</h2></div></header>
    <p class="sub" id="method"></p>
  </div>
</section>

</div>
<footer class="foot" id="foot"></footer>
<div class="tt" id="tt" role="tooltip"></div>

<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };
const byId = Object.fromEntries((D.players || []).map(p => [p.id, p]));
const GWS = D.gws, G0 = GWS[0];
const NAMES = Object.keys(D.builds || {});
const DIFF_OWN = 8;
const fmt = (x, n = 1) => (x === null || x === undefined || Number.isNaN(x) ? "–" : Number(x).toFixed(n));
const num = x => (x === null || x === undefined) ? "–" : Number(x).toLocaleString("en-GB");

const H3 = GWS.slice(0, 3);
(D.players || []).forEach(p => {
  p.xp3 = +H3.reduce((a, g) => a + (p["xp" + g] || 0), 0).toFixed(2);
  p.ceiling3 = +H3.reduce((a, g) => a + (p["cxp" + g] || 0), 0).toFixed(2);
});

/* club identity - decoration only, never encodes a value */
const CLUB = {ARS:"#ef2b32",AVL:"#a8375a",BOU:"#e0453a",BRE:"#e05a4a",BHA:"#3d7fd6",
  CHE:"#3060c8",COV:"#6cb8e8",CRY:"#3a63b8",EVE:"#3e6ad0",FUL:"#b9b7b0",HUL:"#f0a13c",
  IPS:"#4a7ec4",LEE:"#e0c34a",LIV:"#d43a4c",MCI:"#6cabdd",MUN:"#e04a3c",NEW:"#a8a6a0",
  NFO:"#dc4040",SUN:"#e05050",TOT:"#9fb2d6"};
const clubOf = t => CLUB[t] || "var(--axis)";

/* ------------------------------------------------------------------ theme */
$("#theme").onclick = () => {
  const light = document.documentElement.dataset.theme === "light";
  document.documentElement.dataset.theme = light ? "dark" : "light";
  $("#theme").textContent = light ? "Light" : "Dark";
  redrawCharts();
};

/* --------------------------------------------------------------- tooltips */
const tt = $("#tt");
let ttLock = false;
function showTip(e, html) {
  tt.innerHTML = html;
  tt.style.display = "block";
  const r = tt.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 8) x = Math.max(8, e.clientX - r.width - 14);
  if (y + r.height > innerHeight - 8) y = Math.max(8, e.clientY - r.height - 14);
  tt.style.left = x + "px"; tt.style.top = y + "px";
}
const hideTip = () => { if (!ttLock) tt.style.display = "none"; };
function tipify(node, html) {
  node.addEventListener("pointermove", e => showTip(e, html));
  node.addEventListener("pointerleave", hideTip);
  node.addEventListener("pointerdown", e => {           /* touch: tap to hold */
    if (e.pointerType === "touch") { ttLock = false; showTip(e, html); ttLock = true; }
  });
}
document.addEventListener("pointerdown", e => {
  if (ttLock && !e.target.closest("[data-tip],.pl,.cell,.scell,.dot")) { ttLock = false; hideTip(); }
}, true);

/* ------------------------------------------------------------------- nav */
/* Two-tier tabs instead of one endless scrolling page: six group pills,
   each opening a short row of sub tabs, exactly one section on screen.
   The view is in the URL (#plan, #live) so any tab can be linked or
   bookmarked, and the last-visited tab is remembered. */
const GROUPS = [
  ["home", "Home", [["overview", "Overview"]]],
  ["team", "Team", [["squads", "Squads"], ["plan", "Transfers"], ["captain", "Captain"]]],
  ["live", "Live", [["livescore", "Live scores"]]],
  ["game", "Game", [["fixtures", "Fixtures"], ["chips", "Chips"]]],
  ["market", "Market", [["value", "Value"], ["elite", "Elite"], ["price", "Price radar"], ["players", "Players"]]],
  ["model", "Model", [["accuracy", "Accuracy"], ["changes", "Changes"]]],
];
const TAB = new Map();
GROUPS.forEach(([g, gl, tabs], gi) => tabs.forEach(([id, label], ti) =>
  TAB.set(id, {g, gl, gi, ti, label})));
const navEl = $("#nav"), subEl = $("#subnav");
navEl.insertAdjacentHTML("beforeend", GROUPS.map(([g, label]) =>
  `<a href="#${g}" data-g="${g}">${label}</a>`).join(""));

let curTab = null, subCursor = $("#subcursor");
const lastIn = {};                 // last tab visited inside each group
const storeSet = (k, v) => { try { localStorage.setItem("fpldash:" + k, v); } catch (e) {} };
const storeGet = k => { try { return localStorage.getItem("fpldash:" + k); } catch (e) { return null; } };

function slide(bar, cursor, act) {
  if (!act) { cursor.style.display = "none"; return; }
  try {
    const br = bar.getBoundingClientRect(), ar = act.getBoundingClientRect();
    cursor.style.display = "block";
    cursor.style.left = (ar.left - br.left) + "px";
    cursor.style.width = ar.width + "px";
  } catch (e) { cursor.style.display = "none"; }
}
function positionCursors() {
  slide(navEl, $("#navcursor"), navEl.querySelector('a[aria-current="true"]'));
  slide(subEl, subCursor, subEl.querySelector('a[aria-current="true"]'));
}

function showTab(id) {
  id = TAB.has(id) ? id : "overview";
  if (id === curTab) return;
  curTab = id;
  const meta = TAB.get(id);
  lastIn[meta.g] = id;
  storeSet("tab", id);

  navEl.querySelectorAll("a").forEach(a =>
    a.setAttribute("aria-current", a.dataset.g === meta.g));
  subEl.innerHTML = GROUPS[meta.gi][2].map(([tid, label]) =>
    `<a href="#${tid}" data-s="${tid}"${tid === id ? ' aria-current="true"' : ""}>${label}</a>`).join("")
    + `<span id="subcursor"></span>`;
  subCursor = $("#subcursor");

  document.querySelectorAll("section").forEach(s => { s.hidden = s.id !== id; });
  const sec = document.getElementById(id);
  /* charts sized themselves while the section was hidden - remeasure now
     that it is visible, and let the cards replay their reveal stagger */
  if (sec) requestAnimationFrame(() => {
    sec.querySelectorAll(".reveal").forEach(n => n.classList.add("in"));
    redrawCharts(); renderChips();
    positionCursors();
  });
  try { scrollTo(0, 0); } catch (e) {}
}

function fromHash() {
  const id = ((typeof location !== "undefined" && location.hash) || "").slice(1);
  if (TAB.has(id)) return id;
  const grp = GROUPS.find(([g]) => g === id);
  if (grp) return lastIn[grp[0]] || grp[2][0][0];
  return storeGet("tab") || "overview";
}
addEventListener("hashchange", () => showTab(fromHash()));
let rtNav;
addEventListener("resize", () => { clearTimeout(rtNav); rtNav = setTimeout(positionCursors, 120); });
showTab(fromHash());

/* ------------------------------------------------- reveal on scroll */
const revealIO = new IntersectionObserver(entries => {
  entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add("in"); revealIO.unobserve(en.target); } });
}, {threshold: 0.06});
document.querySelectorAll(".card, .tile").forEach((n, i) => {
  n.classList.add("reveal");
  n.style.transitionDelay = `${Math.min(i * 40, 240)}ms`;
  revealIO.observe(n);
});

/* ------------------------------------------------- count-up numbers */
function countUp(node) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const m = node.textContent.match(/^\s*([\d.,]+)(.*)$/s);
  if (!m) return;
  const target = parseFloat(m[1].replace(/,/g, ""));
  if (!Number.isFinite(target) || target === 0) return;
  const dec = (m[1].split(".")[1] || "").length;
  const suffix = m[2];
  const t0 = performance.now(), dur = 900;
  const step = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    node.textContent = (target * e).toLocaleString("en-GB",
      {minimumFractionDigits: dec, maximumFractionDigits: dec}) + suffix;
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
const tileIO = new IntersectionObserver(entries => {
  entries.forEach(en => {
    if (!en.isIntersecting) return;
    countUp(en.target.querySelector(".v"));
    tileIO.unobserve(en.target);
  });
}, {threshold: 0.4});
document.querySelectorAll(".tile").forEach(n => tileIO.observe(n));

/* ----------------------------------------------------------------- strap */
const dl = D.deadline ? new Date(D.deadline) : null;
const fmtStamp = t => String(t || "").slice(0, 16).replace("T", " ");
$("#strap").innerHTML =
  (dl ? `GW${G0} deadline ${dl.toUTCString().slice(0, 22)} UK · ` : "")
  + `projections GW${G0}–${GWS[GWS.length - 1]} · plan ${fmtStamp(D.generated)}`
  + `<span id="strapLive"></span>`;
$("#foot").innerHTML =
  `Every number on this page comes from the official FPL game API — no
   projections are hand-picked. Plans <b>${fmtStamp(D.generated)}</b> ·
   live data <span id="footLive">–</span> · model and methodology
   described in the <a href="#model" style="color:var(--ink2)">Model</a> tab.`;

/* ======================================================== AUTOMATION */
const AUTO = D.automation || {};
function srcBadge(src) {
  if (src === "api") return `<span class="st ok"><span class="dot"></span>live API</span>`;
  if (!src) return `<span class="st warn"><span class="dot"></span>unknown</span>`;
  return `<span class="st bad"><span class="dot"></span>${src}</span>`;
}
function stBadge(kind, text) {
  return `<span class="st ${kind}"><span class="dot"></span>${text}</span>`;
}
/* Changes the bot applied for the gameweek now being planned, which FPL has
   not published yet: picks only go public after the deadline, so until then
   the squad view shows the last confirmed one while the real squad has moved. */
function pendingFor(n) {
  const sub = ((AUTO.submit || {}).teams || {})[n];
  if (!sub || (sub.status !== "applied" && sub.status !== "already-applied")) return null;
  if (sub.gw !== G0) return null;
  const m = /^gw(\d+)$/.exec((D.builds[n] || {}).picks_source || "");
  if (!m || +m[1] >= G0) return null;      // squad view is already current
  return sub;
}
function renderAutomation() {
  const host = $("#autoGrid");
  const cells = [];
  NAMES.forEach(n => {
    const b = D.builds[n] || {};
    const src = (b.squad_source || "").startsWith("gw") || b.squad_source === "api"
      ? "api" : b.squad_source;
    const wk = b.plan && b.plan.weeks ? b.plan.weeks.find(w => w.gw === G0) : null;
    const hits = wk ? wk.hits : 0;
    const sub = ((AUTO.submit || {}).teams || {})[n];
    const pd = pendingFor(n);
    const subTxt = pd ? "applied — squad updates at the deadline"
      : sub ? (sub.status === "applied" ? "lineup written"
      : sub.status === "already-applied" ? "already in place"
      : sub.status === "dry-run" ? "verified, will apply"
      : sub.status ? sub.status : "—") : "waiting for window";
    cells.push(`<div class="autocell">
      <div class="k">${n} <span class="hint">${b.role === "risk" ? "risk" : "main"}</span></div>
      <div class="v">${b.free_transfers ?? "–"} FT <span class="hint">· ${hits} hit${hits === 1 ? "" : "s"} planned</span></div>
      <div class="n">squad ${srcBadge(src)}<br>submit ${stBadge(
        pd || (sub && (sub.status === "applied" || sub.status === "already-applied")) ? "ok"
        : sub && sub.status === "dry-run" ? "warn" : "", subTxt)}</div>
    </div>`);
  });
  const bank = NAMES.map(n => `${n}: £${fmt((D.builds[n] || {}).bank, 1)}m`).join(" · ");
  cells.push(`<div class="autocell">
    <div class="k">Bank <span class="hint">combined</span></div>
    <div class="v">£${fmt(NAMES.reduce((a, n) => a + ((D.builds[n] || {}).bank || 0), 0), 1)}m</div>
    <div class="n">${bank}</div></div>`);
  host.innerHTML = cells.join("");
  const lastRun = (AUTO.submit || {}).at;
  $("#autoNote").innerHTML =
    (AUTO.apply_window ? `The submitter acts automatically within
      <b>${AUTO.apply_window}h</b> of the deadline: it verifies first, applies an hour
      later, and writes every change to the audit log.` : "")
    + (lastRun ? ` Last submitter run ${String(lastRun).slice(0, 16).replace("T", " ")} UTC.` : "")
    + (AUTO.ft_pin ? ` Free transfers are pinned by config this season (the official
      app is the authority on banking).` : "");
}

/* deadline countdown, ticking every second */
const dlDate = D.deadline ? new Date(D.deadline) : null;
function renderCountdown() {
  const cd = $("#cd");
  if (!dlDate) { cd.textContent = ""; return; }
  let s = Math.floor((dlDate - Date.now()) / 1000);
  if (s <= 0) {
    cd.classList.remove("urgent");
    cd.innerHTML = `<span class="u">deadline passed</span>`;
    return;
  }
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60); s -= m * 60;
  cd.classList.toggle("urgent", dlDate - Date.now() < 24 * 3600e3);
  cd.innerHTML =
    (d ? `<span class="u">${d}</span><span class="l">d</span>` : "") +
    `<span class="u">${h}</span><span class="l">h</span>
     <span class="u">${String(m).padStart(2, "0")}</span><span class="l">m</span>
     <span class="u">${String(s).padStart(2, "0")}</span><span class="l">s</span>`;
}
renderAutomation();
renderCountdown();
setInterval(renderCountdown, 1000);

/* ============================================================== CHART KIT */
const CH = {pad: {t: 14, r: 46, b: 26, l: 40}};
function svgEl(n, a) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", n);
  for (const k in a) e.setAttribute(k, a[k]);
  return e;
}
function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

/**
 * Multi-series line chart. One y-axis only, ever.
 * series: [{name, color, points:[{x,y}], dash}]
 */
function lineChart(host, series, opts = {}) {
  host.innerHTML = "";
  const all = series.flatMap(s => s.points).filter(p => p.y !== null && p.y !== undefined);
  if (!all.length) { host.innerHTML = `<div class="empty">${opts.empty || "No data yet."}</div>`; return; }
  const W = Math.max(280, host.clientWidth || 520), H = opts.height || 210;
  const p = CH.pad;
  const xs = all.map(d => d.x), ys = all.map(d => d.y);
  const x0 = Math.min(...xs), x1 = Math.max(...xs, x0 + 1);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  const padY = (y1 - y0) * 0.12 || 1;
  y1 += padY;
  if (opts.zero && y0 >= 0) y0 = 0; else y0 -= padY;
  const sx = v => p.l + (v - x0) / (x1 - x0) * (W - p.l - p.r);
  const sy = v => opts.invert
    ? p.t + (v - y0) / (y1 - y0) * (H - p.t - p.b)
    : H - p.b - (v - y0) / (y1 - y0) * (H - p.t - p.b);

  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, width: "100%", height: H,
                            role: "img", "aria-label": opts.title || "line chart"});
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const v = y0 + (y1 - y0) * i / ticks;
    svg.appendChild(svgEl("line", {x1: p.l, x2: W - p.r, y1: sy(v), y2: sy(v), class: "gl"}));
    const t = svgEl("text", {x: p.l - 6, y: sy(v) + 3.5, class: "axis", "text-anchor": "end"});
    t.textContent = opts.fmtY ? opts.fmtY(v) : Math.round(v);
    svg.appendChild(t);
  }
  xs.filter((v, i, a) => a.indexOf(v) === i).forEach(v => {
    const t = svgEl("text", {x: sx(v), y: H - 8, class: "axis", "text-anchor": "middle"});
    t.textContent = (opts.xPrefix || "") + v;
    svg.appendChild(t);
  });
  svg.appendChild(svgEl("line", {x1: p.l, x2: W - p.r, y1: H - p.b, y2: H - p.b, class: "al"}));

  series.forEach(s => {
    const pts = s.points.filter(d => d.y !== null && d.y !== undefined);
    if (!pts.length) return;
    const d = pts.map((q, i) => `${i ? "L" : "M"}${sx(q.x)},${sy(q.y)}`).join(" ");
    const path = svgEl("path", {d, fill: "none", stroke: s.color, "stroke-width": 2,
                                "stroke-linejoin": "round", "stroke-linecap": "round"});
    if (s.dash) path.setAttribute("stroke-dasharray", "1 5");
    svg.appendChild(path);
    const last = pts[pts.length - 1];
    svg.appendChild(svgEl("circle", {cx: sx(last.x), cy: sy(last.y), r: 4.5,
      fill: s.color, stroke: css("--surface"), "stroke-width": 2}));
    const lab = svgEl("text", {x: sx(last.x) + 8, y: sy(last.y) + 3.5, class: "axis",
                               fill: css("--ink2")});
    lab.textContent = opts.fmtY ? opts.fmtY(last.y) : Math.round(last.y);
    svg.appendChild(lab);
  });

  const hair = svgEl("line", {y1: p.t, y2: H - p.b, class: "al", opacity: 0});
  svg.appendChild(hair);
  const hit = svgEl("rect", {x: p.l, y: p.t, width: W - p.l - p.r, height: H - p.t - p.b,
                             fill: "transparent"});
  svg.appendChild(hit);
  const snap = ev => {
    const r = svg.getBoundingClientRect();
    const vx = (ev.clientX - r.left) / r.width * W;
    let best = null, bd = 1e9;
    xs.forEach(v => { const d = Math.abs(sx(v) - vx); if (d < bd) { bd = d; best = v; } });
    if (best === null) return;
    hair.setAttribute("x1", sx(best)); hair.setAttribute("x2", sx(best));
    hair.setAttribute("opacity", 1);
    const rows = series.map(s => {
      const q = s.points.find(d => d.x === best);
      if (!q || q.y === null || q.y === undefined) return "";
      return `<div><span class="lk" style="background:${s.color}"></span>` +
        `<b>${opts.fmtY ? opts.fmtY(q.y) : Math.round(q.y)}</b> ` +
        `<span style="color:var(--muted)">${s.name}</span></div>`;
    }).join("");
    showTip(ev, `<b>${(opts.xPrefix || "")}${best}</b>${rows}`);
  };
  hit.addEventListener("pointermove", snap);
  hit.addEventListener("pointerdown", snap);
  hit.addEventListener("pointerleave", () => { hair.setAttribute("opacity", 0); hideTip(); });
  host.appendChild(svg);

  if (series.length > 1) {
    const lg = el("div", "legend");
    lg.innerHTML = series.map(s =>
      `<span><span class="lk" style="background:${s.color}"></span>${s.name}</span>`).join("");
    host.appendChild(lg);
  }
}

/** Scatter with emphasis: highlighted points in accent, the rest recessive. */
function scatterChart(host, pts, opts = {}) {
  host.innerHTML = "";
  if (!pts.length) { host.innerHTML = `<div class="empty">No data.</div>`; return; }
  const W = Math.max(300, host.clientWidth || 700), H = opts.height || 320;
  const p = {t: 14, r: 16, b: 34, l: 44};
  const xs = pts.map(d => d.x), ys = pts.map(d => d.y);
  const x0 = Math.min(...xs) - 0.3, x1 = Math.max(...xs) + 0.3;
  const y0 = 0, y1 = Math.max(...ys) * 1.08 || 1;
  const sx = v => p.l + (v - x0) / (x1 - x0) * (W - p.l - p.r);
  const sy = v => H - p.b - (v - y0) / (y1 - y0) * (H - p.t - p.b);
  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, width: "100%", height: H,
                            role: "img", "aria-label": "price against projected points"});
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4;
    svg.appendChild(svgEl("line", {x1: p.l, x2: W - p.r, y1: sy(v), y2: sy(v), class: "gl"}));
    const t = svgEl("text", {x: p.l - 6, y: sy(v) + 3.5, class: "axis", "text-anchor": "end"});
    t.textContent = Math.round(v); svg.appendChild(t);
  }
  for (let v = Math.ceil(x0); v <= x1; v += 2) {
    const t = svgEl("text", {x: sx(v), y: H - 12, class: "axis", "text-anchor": "middle"});
    t.textContent = "£" + v; svg.appendChild(t);
  }
  const xlab = svgEl("text", {x: (W + p.l) / 2, y: H - 1, class: "axis", "text-anchor": "middle"});
  xlab.textContent = "price"; svg.appendChild(xlab);

  /* frontier: best projection available at each price step */
  const best = new Map();
  pts.forEach(d => { if (!best.has(d.x) || best.get(d.x).y < d.y) best.set(d.x, d); });
  const front = [...best.values()].sort((a, b) => a.x - b.x);
  let run = -1, keep = [];
  front.forEach(d => { if (d.y > run) { run = d.y; keep.push(d); } });
  if (keep.length > 1) {
    svg.appendChild(svgEl("path", {
      d: keep.map((q, i) => `${i ? "L" : "M"}${sx(q.x)},${sy(q.y)}`).join(" "),
      fill: "none", stroke: css("--s3"), "stroke-width": 2, opacity: .85}));
    const tip = keep[keep.length - 1];
    const lab = svgEl("text", {x: sx(tip.x) - 6, y: sy(tip.y) - 9, class: "axis",
                               fill: css("--ink2"), "text-anchor": "end"});
    lab.textContent = "best at each price";
    svg.appendChild(lab);
  }
  const order = [...pts].sort((a, b) => (a.hl ? 1 : 0) - (b.hl ? 1 : 0));
  order.forEach(d => {
    const g = svgEl("circle", {cx: sx(d.x), cy: sy(d.y), r: d.hl ? 5 : 3,
      fill: d.hl ? d.color : css("--deemph"), opacity: d.hl ? 1 : .55, class: "dot"});
    if (d.hl) { g.setAttribute("stroke", css("--surface")); g.setAttribute("stroke-width", 2); }
    svg.appendChild(g);
  });
  const hit = svgEl("rect", {x: 0, y: 0, width: W, height: H, fill: "transparent"});
  svg.appendChild(hit);
  const near = ev => {
    const r = svg.getBoundingClientRect();
    const mx = (ev.clientX - r.left) / r.width * W, my = (ev.clientY - r.top) / r.height * H;
    let b = null, bd = 1e9;
    pts.forEach(d => {
      const dd = (sx(d.x) - mx) ** 2 + (sy(d.y) - my) ** 2;
      if (dd < bd) { bd = dd; b = d; }
    });
    if (b && bd < 1600) showTip(ev, b.tip); else hideTip();
  };
  hit.addEventListener("pointermove", near);
  hit.addEventListener("pointerdown", near);
  hit.addEventListener("pointerleave", hideTip);
  host.appendChild(svg);
}

/* ============================================================ STAT TILES */
function tiles() {
  const t = [];
  const hist = (D.history && D.history.teams) || {};
  const anyWeeks = NAMES.some(n => (hist[n] && hist[n].weeks || []).length);
  if (anyWeeks) {
    NAMES.forEach(n => {
      const w = (hist[n] && hist[n].weeks) || [];
      if (!w.length) return;
      const last = w[w.length - 1];
      const d = last.rank_delta;
      t.push([n, num(last.total) + " pts",
        `GW${last.gw}: ${last.points} · average ${last.average ?? "–"}`]);
      t.push([n + " rank", num(last.overall_rank),
        d === null || d === undefined ? "overall"
          : `<span class="${d > 0 ? "up" : "down"}">${d > 0 ? "▲" : "▼"} ${num(Math.abs(d))}</span> this week`]);
    });
  } else {
    NAMES.forEach(n => {
      const b = D.builds[n];
      t.push([n, fmt(b.plan ? b.plan.total_xp : b.current_report.xp_total, 0) + " pts",
        `projected over GW${G0}–${GWS[GWS.length - 1]} · ${fmt(b.own_current, 0)}% average ownership`]);
    });
    const b0 = D.builds[NAMES[0]];
    if (b0) t.push(["Next deadline", dl ? dl.toUTCString().slice(5, 17) : "–",
      "season has not started, so no results yet"]);
  }
  $("#tiles").innerHTML = t.map(([k, v, n], i) =>
    `<div class="tile${i === 0 ? " hero" : ""}"><div class="k">${k}</div>` +
    `<div class="v">${v}</div><div class="n">${n}</div></div>`).join("");
}

/* ========================================================= SEASON CHARTS */
function seasonCharts() {
  const hist = (D.history && D.history.teams) || {};
  const colors = [css("--s1"), css("--s2")];
  const ptsSeries = [], rankSeries = [];
  let avgDone = false;
  NAMES.forEach((n, i) => {
    const w = (hist[n] && hist[n].weeks) || [];
    if (!w.length) return;
    ptsSeries.push({name: n, color: colors[i % 2],
      points: w.map(x => ({x: x.gw, y: x.net}))});
    rankSeries.push({name: n, color: colors[i % 2],
      points: w.map(x => ({x: x.gw, y: x.overall_rank}))});
    if (!avgDone) {
      ptsSeries.push({name: "Field average", color: css("--deemph"), dash: true,
        points: w.map(x => ({x: x.gw, y: x.average}))});
      avgDone = true;
    }
  });
  lineChart($("#ptsChart"), ptsSeries,
    {zero: true, xPrefix: "GW", empty: "Nothing to plot until gameweek 1 finishes."});
  lineChart($("#rankChart"), rankSeries,
    {invert: true, xPrefix: "GW", fmtY: v => v >= 1e6 ? (v / 1e6).toFixed(1) + "M"
      : v >= 1000 ? Math.round(v / 1000) + "k" : Math.round(v),
     empty: "Rank appears after your first gameweek."});
  $("#seasonNote").innerHTML = ptsSeries.length
    ? "Points are net of any hits. On the rank chart, up is better — the axis is inverted."
    : "Both charts fill in automatically from gameweek 1 onward. The bot stores every "
      + "projection before the deadline, so accuracy grading starts at the same time.";
}

/* ================================================================ PITCHES */
let curView = "target", curGw = G0;
$("#viewTabs").innerHTML =
  `<button data-v="target" aria-pressed="true">Recommended</button>
   <button data-v="current" aria-pressed="false">As it stands</button>`;
$("#gwTabs").innerHTML = GWS.map(g =>
  `<button data-g="${g}" aria-pressed="${g === curGw}">GW${g}</button>`).join("");
$("#viewTabs").onclick = e => { if (e.target.dataset.v) { curView = e.target.dataset.v; syncSquad(); } };
$("#gwTabs").onclick = e => { if (e.target.dataset.g) { curGw = +e.target.dataset.g; syncSquad(); renderCap(); } };
function syncSquad() {
  $("#viewTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.v === curView));
  $("#gwTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", +b.dataset.g === curGw));
  renderPitches();
}
/* green strip shown above a squad whose changes are applied but not yet
   public — it names the moves so "what happened to my transfer?" is answered */
function pendingBanner(pd) {
  const chip = (id, kind) => byId[id]
    ? `<span class="iochip ${kind}">${byId[id].name}</span>` : "";
  const inn = (pd.in || []).map(i => chip(i, "in")).join(" ");
  const out = (pd.out || []).map(i => chip(i, "out")).join(" ");
  const moves = (inn || out)
    ? `${out}${inn ? `${out ? " " : ""}<span class="hint">→</span> ${inn}` : ""}`
    : "lineup and captain updated";
  return `<div class="pending">
    <span class="st ok"><span class="dot"></span>GW${pd.gw} changes applied</span>
    ${moves}<span class="hint">FPL publishes the updated squad after the deadline —
    this view shows the last one it confirmed.</span></div>`;
}
function playerCard(p, gw, isCap, isVice) {
  const c = el("div", "pl" + (isCap ? " cap" : "") + (isVice ? " vice" : "")
    + (p.selected_by < DIFF_OWN ? " diff" : "") + (p.status !== "a" ? " flagged" : ""));
  c.style.setProperty("--club", clubOf(p.team));
  const fx = p["fx" + gw] || "";
  const fdr = p["fdr" + gw] || 3;
  c.innerHTML = `${isCap ? '<span class="badge">C</span>' : isVice ? '<span class="badge v">V</span>' : ""}
    <div class="nm">${p.name}</div>
    <div class="mt">${p.team} · £${fmt(p.price)}</div>
    <div class="fx" style="background:${cellColor(fdr)}">${fx}</div>
    <div class="xp">${fmt(p["xp" + gw], 1)}</div>`;
  tipify(c, `<b>${p.name}</b> — ${p.pos}, ${p.team}, £${fmt(p.price)}m<br>
    Owned ${fmt(p.selected_by, 1)}% · starts ${Math.round(p.start_share * 100)}% of the time<br>
    GW${gw} ${fx} — expected <b>${fmt(p["xp" + gw], 2)}</b>, ceiling ${fmt(p["cxp" + gw], 2)}<br>
    <span style="color:var(--muted)">appearance ${fmt(p.b_app, 2)} · goals ${fmt(p.b_goals, 2)} ·
    assists ${fmt(p.b_assists, 2)} · clean sheet ${fmt(p.b_cs, 2)} · saves ${fmt(p.b_saves, 2)} ·
    defensive ${fmt(p.b_dc, 2)} · bonus ${fmt(p.b_bonus, 2)}</span>
    ${p.news ? `<br><span style="color:var(--critical)">${p.news}</span>` : ""}`);
  return c;
}
function renderPitches() {
  const host = $("#pitches"); host.innerHTML = "";
  NAMES.forEach(n => {
    const b = D.builds[n];
    const rep = curView === "target" ? b.target_report : b.current_report;
    const box = el("div");
    const g = rep && rep.gws ? rep.gws[curGw] : null;
    box.innerHTML = `<div class="row" style="justify-content:space-between;margin-bottom:6px">
      <b>${n}</b><span class="hint">£${fmt(rep ? rep.cost : 0)}m ·
      ${fmt(curView === "target" ? b.own_target : b.own_current, 0)}% owned</span></div>`;
    const pd = curView === "current" ? pendingFor(n) : null;
    if (pd) box.insertAdjacentHTML("beforeend", pendingBanner(pd));
    if (!g) { box.innerHTML += `<div class="empty">No squad.</div>`; host.appendChild(box); return; }
    const pitch = el("div", "pitch");
    const lines = {GKP: [], DEF: [], MID: [], FWD: []};
    g.xi.forEach(i => byId[i] && lines[byId[i].pos].push(byId[i]));
    ["GKP", "DEF", "MID", "FWD"].forEach(k => {
      const row = el("div", "line");
      lines[k].sort((a, c) => c["xp" + curGw] - a["xp" + curGw])
        .forEach(p => row.appendChild(
          playerCard(p, curGw, p.id === g.captain, p.id === g.vice)));
      pitch.appendChild(row);
    });
    const bench = el("div", "line bench");
    g.bench.forEach(i => byId[i] && bench.appendChild(
      playerCard(byId[i], curGw, false, byId[i].id === g.vice)));
    pitch.appendChild(bench);
    box.appendChild(pitch);
    const form = ["DEF", "MID", "FWD"].map(k => lines[k].length).join("-");
    const cap = byId[g.captain];
    const foot = el("p", "note");
    const vc = byId[g.vice];
    foot.innerHTML = `<b>${form}</b> · ${fmt(g.xp, 1)} projected · captain
      <b>${cap ? cap.name : "–"}</b>, vice <b>${vc ? vc.name : "–"}</b> · ${b.blurb}`;
    box.appendChild(foot);
    host.appendChild(box);
  });
  host.querySelectorAll(".pl").forEach((n, i) => n.style.animationDelay = `${Math.min(i * 35, 500)}ms`);
  $("#squadSub").textContent = curView === "target"
    ? "What the optimiser would field, given each team's brief."
    : NAMES.some(n => pendingFor(n))
      ? "As FPL last published — the changes the bot applied appear here once the deadline passes."
      : "Your squads exactly as they stand right now.";
}

/* ================================================================== PLAN */
let curPlan = NAMES[0];
$("#planTabs").innerHTML = NAMES.map(n =>
  `<button data-n="${n}" aria-pressed="${n === curPlan}">${n}</button>`).join("");
$("#planTabs").onclick = e => {
  if (!e.target.dataset.n) return;
  curPlan = e.target.dataset.n;
  $("#planTabs").querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.n === curPlan));
  renderPlan();
};
function renderPlan() {
  const u = D.builds[curPlan];
  $("#planSub").textContent = u.blurb;
  if (!u.plan) { $("#planBody").innerHTML = `<div class="empty">No plan available.</div>`; return; }
  const hp = u.hit_policy || {};
  const chip = (id, kind) => byId[id]
    ? `<span class="iochip ${kind}">${byId[id].name}${kind === "in" ? ` <span class="hint">£${fmt(byId[id].price)}</span>` : ""}</span>`
    : id;
  const rows = u.plan.weeks.map(k => `<tr>
    <td class="l"><b>GW${k.gw}</b></td>
    <td class="l">${k.out.length ? k.out.map(i => chip(i, "out")).join("") : '<span class="iochip roll">roll</span>'}</td>
    <td class="l">${k.in.length ? k.in.map(i => chip(i, "in")).join("") : "–"}</td>
    <td class="l">${byId[k.captain] ? byId[k.captain].name : "–"}</td>
    <td class="l hide-s">${byId[k.vice] ? byId[k.vice].name : "–"}</td>
    <td class="hide-s">${k.free_transfers}</td>
    <td>${k.hits ? `<span class="down">−${k.hits * 4}</span>` : "0"}</td>
    <td class="hide-s">£${fmt(k.bank)}m</td>
    <td><b>${fmt(k.xp, 1)}</b></td></tr>`).join("");
  const chips = u.chips || [];
  const bestTc = chips.reduce((a, c) => (!a || c.triple_captain > a.triple_captain ? c : a), null);
  const bestBb = chips.reduce((a, c) => (!a || c.bench_boost > a.bench_boost ? c : a), null);
  $("#planBody").innerHTML = `<table>
    <thead><tr><th class="l">Week</th><th class="l">Out</th><th class="l">In</th>
      <th class="l">Captain</th><th class="l hide-s">Vice</th><th class="hide-s">FT left</th><th>Hit</th>
      <th class="hide-s">Bank</th><th>Points</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
  $("#planNote").innerHTML =
    `Starting from ${u.free_transfers} free transfer${u.free_transfers === 1 ? "" : "s"} and
     £${fmt(u.bank)}m. Free transfers bank up to five.
     ${hp.took_hits ? `A hit pays here — it gains ${hp.gain_over_no_hit} points against a
       ${hp.threshold}-point threshold.`
      : hp.rejected_hits ? `A hit was considered and rejected: it gained only
       ${hp.gain_over_no_hit} points against a ${hp.threshold}-point threshold.`
      : "No hit is worth taking in this window."}
     ${bestTc ? ` Best triple captain here: GW${bestTc.gw} on ${bestTc.captain}
       (+${fmt(bestTc.triple_captain, 1)}); best bench boost GW${bestBb.gw}
       (+${fmt(bestBb.bench_boost, 1)}).` : ""}`;
}

/* =============================================================== CAPTAIN */
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
  const b = D.builds[capMode] || {};
  const risk = b.role === "risk";
  const key = risk ? "cxp" : "xp";
  let c = (D.players || []).filter(p =>
    (p.pos === "MID" || p.pos === "FWD") && p.status === "a" && p.start_share > 0.5);
  if (risk) c = c.filter(p => p.selected_by < 25);
  c = c.sort((a, z) => z[key + curGw] - a[key + curGw]).slice(0, 8);
  if (!c.length) { $("#capChart").innerHTML = `<div class="empty">No candidates.</div>`; return; }
  const max = c[0][key + curGw];
  const mine = new Set(b.current || []);
  $("#capChart").innerHTML = `<table>${c.map(p => `
    <tr class="barrow"><td class="l" style="width:150px">${p.name}
      <span class="hint">${p.team} · ${fmt(p.selected_by, 0)}%</span>
      ${mine.has(p.id) ? "" : ' <span class="flag f-warn">not owned</span>'}</td>
    <td style="width:100%"><div class="bar${risk ? " alt" : ""}"
      style="width:${(p[key + curGw] / max * 100).toFixed(1)}%"></div></td>
    <td style="width:92px">${fmt(p["xp" + curGw], 2)} → <b>${fmt(p["xp" + curGw] * 2, 1)}</b></td></tr>`).join("")}</table>`;
  $("#capSub").textContent = risk
    ? "Ranked on ceiling and capped at 25% ownership — a captain everyone owns cannot win you rank."
    : "Ranked on expected points. For the main team the safe pick is usually the right pick.";
  $("#capNote").textContent = risk
    ? "Bar length is the ceiling score; the number is expected points, then doubled."
    : "Bar length and number are both expected points, then doubled. Triple captain trebles instead.";
}

/* ==================================================== TEMPLATE EXPOSURE */
function renderTemplate() {
  const owned = {};
  NAMES.forEach(n => (D.builds[n].current || []).forEach(i => {
    owned[i] = (owned[i] || []).concat(n);
  }));
  const top = (D.players || []).slice().sort((a, b) => b.selected_by - a.selected_by).slice(0, 12);
  if (!top.length) { $("#tmplBody").innerHTML = `<div class="empty">No ownership data.</div>`; return; }
  const max = top[0].selected_by;
  $("#tmplBody").innerHTML = `<table>${top.map(p => {
    const who = owned[p.id] || [];
    const tag = who.length === 2 ? "both"
      : who.length === 1 ? who[0].replace("Minoux_", "")
      : `<span class="down">neither</span>`;
    return `<tr class="barrow">
      <td class="l" style="width:132px">${p.name} <span class="hint">${p.team}</span></td>
      <td style="width:100%"><div class="bar" style="width:${(p.selected_by / max * 100).toFixed(1)}%;
        opacity:${who.length ? 1 : .4}"></div></td>
      <td style="width:52px">${fmt(p.selected_by, 0)}%</td>
      <td style="width:64px" class="l">${tag}</td></tr>`;
  }).join("")}</table>
  <p class="note">Ownership here is the whole game, not the top 10k. A player on 40%
    that you do not own costs you ground every time he hauls — that is the risk
    Minoux_41 is deliberately taking and Minoux_69 is deliberately avoiding.</p>`;
}

/* ================================================================= ELITE */
/** What the world's top-ranked managers hold for the upcoming deadline.
    D.elite is built by fplbot.elite each plan run; absent sample = quiet card. */
function renderElite() {
  const E = D.elite;
  const body = $("#eliteBody");
  if (!E || !(E.template || []).length) {
    $("#eliteSub").textContent = "No elite sample is available yet.";
    body.innerHTML = `<div class="empty">The plan job samples the top of the
      world ranking each run. The first usable sample has not landed, so this
      card stays empty rather than guessing.</div>`;
    for (const id of ["eliteCaps", "eliteIns", "eliteOuts"]) $(`#${id}`).innerHTML = "";
    return;
  }
  $("#eliteSub").textContent =
    `Ownership among the world's ${E.sampled} top-ranked managers, side by side ` +
    `with the whole game's. The elite move earlier — a gap between the two ` +
    `columns is usually where the template is going, not where it has been.`;
  $("#eliteMeta").textContent = `${E.league} · ${E.note || `squads for GW${E.gw}`}`;

  const owned = {};
  NAMES.forEach(n => (D.builds[n].current || []).forEach(i =>
    { owned[i] = (owned[i] || []).concat(n); }));
  const tag = i => { const w = owned[i] || [];
    return w.length === 2 ? `<span class="st ok"><span class="dot"></span>both</span>`
      : w.length === 1 ? `<span class="st warn"><span class="dot"></span>${w[0].replace("Minoux_", "")}</span>`
      : `<span class="down">neither</span>`; };

  body.innerHTML = `<table><thead><tr>
      <th class="l">Player</th><th>£</th><th>Elite</th><th>Game</th><th class="l">Held</th></tr></thead><tbody>${
    E.template.map(r => `
      <tr><td class="l"><b>${r.name}</b> <span class="hint">${r.pos} ${r.team}</span></td>
      <td>${fmt(r.price)}</td>
      <td class="${r.elite > r.field ? "up" : "down"}"><b>${fmt(r.elite, 0)}%</b></td>
      <td>${fmt(r.field, 0)}%</td>
      <td class="l">${tag(r.id)}</td></tr>`).join("")}</tbody></table>`;

  const capRow = c => `<tr><td class="l">${c.name} <span class="hint">${c.team}</span></td>
    <td><b>${fmt(c.elite, 0)}%</b></td></tr>`;
  $("#eliteCaps").innerHTML = `<table><tbody>${(E.captains || []).map(capRow).join("")}</tbody></table>`;
  const move = m => `<tr><td class="l">${m.name} <span class="hint">${m.team}</span></td>
    <td>${Math.round(m.elite / 100 * E.sampled)} managers</td></tr>`;
  $("#eliteIns").innerHTML = (E.moves_in || []).length
    ? `<table><tbody>${E.moves_in.map(move).join("")}</tbody></table>`
    : `<div class="empty">No moves recorded yet this week.</div>`;
  $("#eliteOuts").innerHTML = (E.moves_out || []).length
    ? `<table><tbody>${E.moves_out.map(move).join("")}</tbody></table>`
    : `<div class="empty">No moves recorded yet this week.</div>`;
  $("#eliteNote").textContent =
    "Squads are what the elite intend for the upcoming deadline, read mid-move " +
    "(some managers transfer at the last hour). The planner's elite-weighted " +
    "tilt for both teams is scored against this same sample.";
}

/* ================================================================= VALUE */
function renderScatter() {
  const pos = $("#scPos").value;
  const in69 = new Set(D.builds[NAMES[0]] ? D.builds[NAMES[0]].current : []);
  const in41 = new Set(NAMES[1] && D.builds[NAMES[1]] ? D.builds[NAMES[1]].current : []);
  const pts = (D.players || [])
    .filter(p => p.xp_total > 1 && (!pos || p.pos === pos))
    .map(p => ({
      x: p.price, y: p.xp_total,
      hl: in69.has(p.id) || in41.has(p.id),
      color: in69.has(p.id) ? css("--s1") : css("--s2"),
      tip: `<b>${p.name}</b> — ${p.pos}, ${p.team}<br>£${fmt(p.price)}m ·
        <b>${fmt(p.xp_total, 1)}</b> projected over ${GWS.length} gameweeks<br>
        ${fmt(p.value, 2)} points per £m · owned ${fmt(p.selected_by, 1)}%
        ${in69.has(p.id) ? "<br>in Minoux_69" : ""}${in41.has(p.id) ? "<br>in Minoux_41" : ""}`,
    }));
  scatterChart($("#scatter"), pts);
}
$("#scPos").onchange = renderScatter;

/* ============================================================== FIXTURES */
function cellColor(fdr) {
  if (fdr <= 2) return `color-mix(in oklab,var(--easy) ${fdr === 1 ? 76 : 52}%,var(--surface))`;
  if (fdr === 3) return "var(--neutral)";
  return `color-mix(in oklab,var(--hard) ${fdr === 5 ? 76 : 52}%,var(--surface))`;
}
function renderTicker() {
  const mode = $("#tickSort").value;
  const clubs = Object.keys(D.fixture_grid || {});
  const score = c => {
    const r = (D.fixture_grid[c] || []).filter(Boolean);
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
      (D.fixture_grid[c] || []).map((x, i) => {
        if (!x) return `<td><div class="cell" style="background:var(--neutral)">–</div></td>`;
        return `<td><div class="cell" style="background:${cellColor(x.fdr)}"
          data-tip="${c} ${x.home ? "vs" : "at"} ${x.opp} · GW${GWS[i]}|expected goals for ${x.xgf}, against ${x.xga}|clean sheet ${(Math.exp(-x.xga) * 100).toFixed(0)}%">
          <b>${x.opp}</b><span style="color:var(--ink2)">${x.home ? "H" : "A"} · ${x.fdr}</span></div></td>`;
      }).join("") + "</tr>").join("")}</tbody>`;
  $("#ticker").querySelectorAll("[data-tip]").forEach(n =>
    tipify(n, n.dataset.tip.split("|").join("<br>")));
}
$("#tickSort").onchange = renderTicker;

/** 38 thin columns, top three emphasised, deadline marked. */
function chipStrip(host, weeks, key, opts) {
  host.innerHTML = "";
  const vals = weeks.filter(w => w[key] !== null && w[key] !== undefined);
  const spread = vals.length ? Math.max(...vals.map(w => Math.abs(w[key]))) : 0;
  if (!vals.length || spread === 0) {
    host.innerHTML = `<div class="empty">${opts.empty || "No data."}</div>`;
    return;
  }
  const W = Math.max(300, host.clientWidth || 640), H = 96;
  const p = {t: 10, r: 8, b: 18, l: 40};
  // bars always grow from zero, so a negative week reads as negative
  const lo = Math.min(0, ...vals.map(w => w[key]));
  const hi = Math.max(0.0001, ...vals.map(w => w[key]));
  const gws = weeks.map(w => w.gw);
  const bw = Math.max(3, Math.min(14, (W - p.l - p.r) / gws.length - 2));
  const sx = g => p.l + (gws.indexOf(g) + 0.5) / gws.length * (W - p.l - p.r);
  const sy = v => H - p.b - (v - lo) / (hi - lo || 1) * (H - p.t - p.b);
  const top3 = new Set(vals.slice().sort((a, b) => b[key] - a[key]).slice(0, 3).map(w => w.gw));
  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, width: "100%", height: H,
                            role: "img", "aria-label": opts.label || key});
  svg.appendChild(svgEl("line", {x1: p.l, x2: W - p.r, y1: sy(0), y2: sy(0), class: "al"}));
  const split = opts.split || 19;
  if (gws.includes(split)) {
    const x = sx(split) - bw / 2 - 2;
    svg.appendChild(svgEl("line", {x1: x, x2: x, y1: p.t, y2: H - p.b, class: "al"}));
    const t = svgEl("text", {x: x + 3, y: p.t + 8, class: "axis"});
    t.textContent = "chip deadline"; svg.appendChild(t);
  }
  weeks.forEach(w => {
    const v = w[key];
    if (v === null || v === undefined) return;
    const y = sy(v), y0 = sy(0);
    const r = svgEl("rect", {x: sx(w.gw) - bw / 2, y: Math.min(y, y0),
      width: bw, height: Math.max(1.5, Math.abs(y0 - y)), rx: 2,
      fill: top3.has(w.gw) ? css("--s1") : css("--deemph"),
      opacity: top3.has(w.gw) ? 1 : .5});
    tipify(r, `<b>GW${w.gw}</b><br>${opts.label}: <b>${fmt(v, opts.dp === 0 ? 0 : 1)}</b>` +
      (w.tc_player && key === "triple_captain" ? `<br>on ${w.tc_player}` : ""));
    svg.appendChild(r);
  });
  [gws[0], gws[Math.floor(gws.length / 2)], gws[gws.length - 1]].forEach(g => {
    const t = svgEl("text", {x: sx(g), y: H - 5, class: "axis", "text-anchor": "middle"});
    t.textContent = "GW" + g; svg.appendChild(t);
  });
  [[hi, sy(hi)], lo < 0 ? [lo, sy(lo)] : null].filter(Boolean).forEach(([v, y]) => {
    const t = svgEl("text", {x: p.l - 6, y: y + 4, class: "axis", "text-anchor": "end"});
    t.textContent = fmt(v, opts.dp === 0 ? 0 : 1);
    svg.appendChild(t);
  });
  host.appendChild(svg);
}

/* ================================================================= CHIPS */
const CHIP_GW = (D.chip_calendar && D.chip_calendar.split) || 20;
function runs(from, to, len) {
  const out = [];
  Object.entries(D.season_grid || {}).forEach(([club, row]) => {
    for (let s = from - 1; s + len <= to; s++) {
      const flat = row.slice(s, s + len).flat().filter(Boolean);
      if (!flat.length) continue;
      out.push({club, gw: s + 1, len, fdr: flat.reduce((a, x) => a + x.fdr, 0) / flat.length});
    }
  });
  const best = {};
  out.forEach(r => { if (!best[r.club] || r.fdr < best[r.club].fdr) best[r.club] = r; });
  return Object.values(best).sort((a, b) => a.fdr - b.fdr).slice(0, 8);
}
function winTable(rows) {
  if (!rows.length) return `<div class="empty">No fixtures.</div>`;
  const max = Math.max(...rows.map(r => 5 - r.fdr));
  return `<table>${rows.map(r => `<tr class="barrow">
    <td class="l" style="width:48px"><b>${r.club}</b></td>
    <td class="l hint" style="width:88px">GW${r.gw}–${r.gw + r.len - 1}</td>
    <td style="width:100%"><div class="bar" style="width:${((5 - r.fdr) / max * 100).toFixed(1)}%"></div></td>
    <td style="width:70px">${fmt(r.fdr, 2)}</td></tr>`).join("")}</table>`;
}
function renderChips() {
  const cd = D.chip_deadline ? new Date(D.chip_deadline) : null;
  const win = (D.chip_calendar && D.chip_calendar.windows) || {};
  const w1 = (win.wildcard || [{}])[0] || {};
  $("#chipSub").innerHTML = `Eight chips, in two sets of four — Wildcard, Free Hit,
    Triple Captain, Bench Boost in each. <b>The first set runs through gameweek
    ${CHIP_GW - 1} and anything unused is lost</b>; the second set opens at gameweek
    ${CHIP_GW}. Wildcard and Free Hit cannot be played in gameweek
    ${(w1.start || 2) - 1} — transfers are already unlimited then.`;
  $("#chipCards").innerHTML = [
    ["Wildcard", "For a structural problem, not two injuries. Gameweeks 6–9 is when the season stops lying. Playable from GW2 to the end of its half, so the first one dies with gameweek " + (CHIP_GW - 1) + "."],
    ["Triple Captain", "A premium attacker, home, against a weak defence, ideally in a double gameweek. Play it when the captain list has a clear leader, not merely a first."],
    ["Bench Boost", "Needs all fifteen playing. Pair it with a wildcard the week before that deliberately builds a bench, and aim at a double."],
    ["Free Hit", "Blank-gameweek insurance. Doubles and blanks are not in the fixture list yet; they appear once the cup rounds are drawn."],
  ].map(([k, v]) => `<div class="chip"><b>${k}</b><span class="hint">${v}</span></div>`).join("");
  $("#win1").innerHTML = winTable(runs(1, CHIP_GW - 1, 3));
  $("#win2").innerHTML = winTable(runs(CHIP_GW, 38, 3));
  // engine 7: a chip the bot has armed for itself (owner-approved autoplay)
  const armed = Object.entries(D.builds || {})
    .filter(([, b]) => b.chip_play)
    .map(([name, b]) => `<div class="chip" style="border-color:var(--good)"><b>🃏 ${name}
      — ${b.chip_play.chip.toUpperCase()} armed for GW${b.chip_play.gw}</b>
      <span class="hint">Modelled gain +${(+b.chip_play.gain).toFixed(1)} points over
      GW${D.gws[0]}–${D.gws[D.gws.length - 1]}. The bot plays it at the deadline
      (${(b.chip_play.chip === "wildcard" ? "activates with the transfer batch — the moves are never sent un-chipped"
          : "rides on the lineup write")}).</span></div>`);
  $("#chipArmed").innerHTML = armed.join("");
  renderChipCalendar();

  const clubs = Object.keys(D.season_grid || {}).sort();
  const head = `<tr><td class="l"></td>` + Array.from({length: 38}, (_, i) =>
    (i === CHIP_GW - 1 ? `<th class="brk"></th>` : "") + `<th>${i + 1}</th>`).join("") + `</tr>`;
  $("#season").innerHTML = `<thead>${head}</thead><tbody>${clubs.map(c =>
    `<tr><td class="l">${c}</td>` + D.season_grid[c].map((cells, i) => {
      const brk = i === CHIP_GW - 1 ? `<td class="brk"></td>` : "";
      if (!cells || !cells.length)
        return brk + `<td><div class="scell" style="background:var(--neutral);color:var(--muted)">–</div></td>`;
      const avg = cells.reduce((a, x) => a + x.fdr, 0) / cells.length;
      const lbl = cells.length > 1 ? cells.length + "×" : cells[0].opp;
      return brk + `<td><div class="scell" style="background:${cellColor(Math.round(avg))}"
        data-tip="${c} · GW${i + 1}|${cells.map(x => (x.home ? "vs " : "at ") + x.opp + " (FDR " + x.fdr + ")").join("|")}">${lbl}</div></td>`;
    }).join("") + "</tr>").join("")}</tbody>`;
  $("#season").querySelectorAll("[data-tip]").forEach(n =>
    tipify(n, n.dataset.tip.split("|").join("<br>")));
}

/* ====================================================== CHIP CALENDAR */
let chipTeam = NAMES[0];
const CHIP_DEFS = [
  ["tc_expected", "Triple captain", "best captain that week, weighted by how often this gameweek has been a double"],
  ["bench_boost_expected", "Bench boost", "what your bench adds, weighted by the chance of a double"],
  ["wildcard_expected", "Wildcard", "squad gap vs your season median, plus expected points from loading a rebuilt squad onto likely doubles just ahead"],
  ["blank_risk", "Free hit", "blank exposure: fixtures already missing, or how often this week has blanked before"],
  ["p_double", "Doubles, historically", "share of the last four seasons where this gameweek contained a double"],
  ["p_blank", "Blanks, historically", "share of the last four seasons where this gameweek contained a blank"],
];
function renderChipTabs() {
  const cc = D.chip_calendar;
  if (!cc) return;
  $("#chipTabs").innerHTML = Object.keys(cc.teams).map(n =>
    `<button data-ct="${n}" aria-pressed="${n === chipTeam}">${n}</button>`).join("");
  $("#chipTabs").onclick = e => {
    if (!e.target.dataset.ct) return;
    chipTeam = e.target.dataset.ct;
    $("#chipTabs").querySelectorAll("button").forEach(b =>
      b.setAttribute("aria-pressed", b.dataset.ct === chipTeam));
    renderChipCalendar();
  };
}
function renderChipCalendar() {
  const cc = D.chip_calendar;
  if (!cc || !cc.teams[chipTeam]) {
    $("#chipPicks").innerHTML = `<div class="empty">Chip calendar unavailable.</div>`;
    $("#chipStrips").innerHTML = "";
    return;
  }
  const weeks = cc.teams[chipTeam];
  const picks = cc.picks[chipTeam] || {};
  const half = (h, lo, hi) => {
    const p = picks[h] || {};
    const row = (key, label) => {
      const list = p[key] || [];
      if (!list.length) return `<tr><td class="l">${label}</td>
        <td class="l hint" colspan="2">no clear window in this half</td></tr>`;
      return `<tr><td class="l">${label}</td>
        <td class="l"><b>GW${list[0].gw}</b>${list[0].player ? " on " + list[0].player : ""}</td>
        <td class="l hint">then ${list.slice(1).map(x => "GW" + x.gw).join(", ") || "–"}</td></tr>`;
    };
    return `<div><p class="hint">${h === "first" ? "First set — through GW" + (cc.split - 1)
      : "Second set — gameweek " + CHIP_GW + " onward"}</p><table><tbody>
      ${row("triple_captain", "Triple captain")}
      ${row("bench_boost", "Bench boost")}
      ${row("wildcard", "Wildcard")}
      ${row("free_hit", "Free hit")}
    </tbody></table></div>`;
  };
  $("#chipPicks").innerHTML = `<div class="split">${half("first")}${half("second")}</div>`;

  $("#chipStrips").innerHTML = CHIP_DEFS.map(([k, label, why]) =>
    `<div style="margin-bottom:12px"><div class="hint" style="margin-bottom:2px">
      <b style="color:var(--ink)">${label}</b> — ${why}</div>
      <div id="strip_${k}"></div></div>`).join("");
  CHIP_DEFS.forEach(([k, label]) => {
    chipStrip($("#strip_" + k), weeks, k,
      {label, split: cc.split, dp: 1,
       empty: k.startsWith("p_")
         ? "No historical pattern data shipped."
         : "Nothing to score here yet."});
  });
  const basis = (cc.basis || []).join(", ");
  $("#chipNote").innerHTML = `Highlighted columns are the three best weeks in each row.
    The bottom two rows are history, not forecast: how often each gameweek number
    actually contained a double or a blank across ${basis || "recent seasons"}. Doubles
    have clustered in GW25 and GW33–37, blanks around GW29 and GW34, driven by cup
    rounds and European midweeks. Bench boost and triple captain are weighted by that
    pattern, so a week that has usually doubled scores higher before the real fixtures
    are known. It is a prior and nothing more — the actual doubles depend on cup draws
    that have not happened, and every row re-scores itself the week they land. The
    wildcard row is a deviation from ${chipTeam}'s own season median plus the expected
    points from loading a rebuilt squad onto doubles in the following fortnight, so a
    tall column means that week is unusually good to rebuild — especially with doubles
    just ahead. It is a guide, not a points guarantee.`;
}

/* ============================================================ PRICE RADAR */
function renderPrice() {
  const preds = D.price_pred || [];
  const ev = D.price_eval;
  const tiles = [];
  tiles.push(`<div class="tile"><div class="k">Players watched</div>
    <div class="v">${preds.length || "–"}</div>
    <div class="n">${preds.length ? "with a directional projection" : "no predictions yet"}</div></div>`);
  if (ev) {
    tiles.push(`<div class="tile"><div class="k">Brier score</div>
      <div class="v">${fmt(ev.brier_mean, 3)}</div>
      <div class="n">${ev.scored} predictions graded, naive ${fmt(ev.brier_naive, 3)}</div></div>`);
    const skill = ev.brier_naive - ev.brier_mean;
    tiles.push(`<div class="tile"><div class="k">Edge vs naive</div>
      <div class="v" style="color:${skill > 0.02 ? css("--s1") : skill > 0 ? css("--warning") : css("--critical")}" >${skill >= 0 ? "+" : ""}${fmt(skill, 3)}</div>
      <div class="n">${skill > 0 ? "beats always-guessing the base rate" : "not yet better than the base rate"}</div></div>`);
  }
  const rise = preds.filter(p => p.p_rise >= 0.25).slice(0, 6);
  const fall = preds.filter(p => p.p_fall >= 0.25).slice(0, 6);
  const tbl = (rows, key) => {
    if (!rows.length) return `<div class="empty">Nobody credible.</div>`;
    return `<table><thead><tr><th class="l">Player</th><th class="l">Club</th><th class="l">Pos</th>
      <th>Price</th><th>Own %</th><th>p</th><th>Conf</th></tr></thead><tbody>${rows.map(p =>
      `<tr><td class="l">${p.name}</td><td class="l hint">${p.team}</td><td class="l hint">${p.pos}</td>
      <td>£${fmt(p.price, 1)}</td><td>${fmt(p.own, 1)}</td>
      <td class="${key === "rise" ? "up" : "down"}">${fmt(p[key === "rise" ? "p_rise" : "p_fall"], 2)}</td>
      <td>${Math.round(p.conf * 100)}%</td></tr>`).join("")}</tbody></table>`;
  };
  let body;
  if (!preds.length) {
    body = `<div class="empty">The engine is still learning. The watch job's hourly price log
      needs a few days of history before any prediction is trusted — until then the planner
      runs bit-identical without it.</div>`;
  } else {
    body = `<div class="split">
      <div><h3>May rise before the deadline</h3>${tbl(rise, "rise")}</div>
      <div><h3>May fall</h3>${tbl(fall, "fall")}</div>
    </div>
    <p class="note">p is the probability of a price change over the next ~3 days; conf is how
      much clean log history backs it (it grows toward 80%, never certainty). Ownership and price
      come from the latest snapshot.</p>`;
  }
  $("#priceBody").innerHTML = `<div class="tiles" style="margin-bottom:14px">${tiles.join("")}</div>${body}`;
}

/* ==================================================== ENGINE CHECKS */
function renderEngines() {
  const pe = D.price_eval, ne = D.news_eval;
  const badge = (ok, okText, badText) =>
    `<span class="flag ${ok ? "f-diff" : "f-warn"}">${ok ? okText : badText}</span>`;
  const rows = [];
  if (pe) {
    rows.push(`<tr><td class="l"><b>Price (engine 5)</b></td>
      <td>${fmt(pe.brier_mean, 3)} Brier vs ${fmt(pe.brier_naive, 3)} naive</td>
      <td>${pe.scored} graded</td>
      <td>${badge(pe.brier_mean < pe.brier_naive, "beats base rate", "not yet better")}</td></tr>`);
  }
  if (ne) {
    rows.push(`<tr><td class="l"><b>News (engine 6)</b></td>
      <td>${Math.round(ne.precision * 100)}% agree with FPL on ruled-out players</td>
      <td>${ne.signals} signals</td>
      <td>${badge(ne.pass, "override unlocked at 90%", "advisory only")}</td></tr>`);
  }
  rows.push(`<tr><td class="l"><b>Rank (engine 1)</b></td><td>Both arms beat the baseline
    on points and percentile in the 2025-26 replay</td><td>backtest</td>
    <td>${badge(true, "live", "")}</td></tr>`);
  rows.push(`<tr><td class="l"><b>Chips (engine 3)</b></td><td>TC once (GW2), BB once (GW3)
    in the replay with once-per-season enforcement</td><td>backtest</td>
    <td>${badge(true, "live", "")}</td></tr>`);
  rows.push(`<tr><td class="l"><b>Scenarios (engine 2)</b></td><td>risk_lambda 0.6 cost points,
    0.3 changed nothing — waiting on the tuning sweep</td><td>backtest</td>
    <td>${badge(false, "tuned", "off pending tune")}</td></tr>`);
  const empty = !pe && !ne
    ? `<p class="note">The price and news engines have not accumulated enough history to be
       graded yet — the watch job's logs are their exam papers.</p>` : "";
  $("#engineBody").innerHTML = `${empty}<table>
    <thead><tr><th class="l">Engine</th><th class="l">Latest evidence</th><th>Basis</th>
    <th>Status</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

/* ============================================================== LIVE GW */
/* live.json is a watcher snapshot, not a websocket: this page re-fetches it
   every 2 minutes and says on screen exactly how old it is. The per-player
   "live" total comes from FPL (autosubs already applied by them) while rows
   are computed from the picked XI, so an autosubbed-in player can show points
   the live total does not include - stated on the card, not hidden. */
let LIVE = null;
function liveAge() {
  if (!LIVE || !LIVE.generated) return "";
  const age = (Date.now() - new Date(LIVE.generated).getTime()) / 60000;
  if (!Number.isFinite(age)) return "";
  const stale = age > 90;
  $("#liveAge").textContent = `snapshot ${Math.round(age)} min old`;
  $("#liveAge").style.color = stale ? css("--warning") : "";
  // the strap's plan stamp only moves when the plan job reruns - keep a live
  // stamp next to it so the two clocks are never mistaken for each other
  const strapLive = $("#strapLive");
  if (strapLive) strapLive.textContent = ` · live ${fmtStamp(LIVE.generated)}`;
  const footLive = $("#footLive");
  if (footLive) footLive.textContent = fmtStamp(LIVE.generated);
  return age;
}
function chipBadge(c) {
  const name = {wc: "Wildcard", fh: "Free hit", tc: "Triple captain",
                bb: "Bench boost"}[String(c || "").toLowerCase()];
  return name ? `<span class="flag f-diff">${name} active</span>` : "";
}
function renderLivescore() {
  const body = $("#liveBody");
  if (!LIVE || !LIVE.status) {
    $("#liveSub").textContent = "Nothing in play right now. This tab comes alive once the " +
      "week's first fixture kicks off and the watcher stamps live.json.";
    $("#liveAge").textContent = "";
    const strapLive = $("#strapLive");
    if (strapLive) strapLive.textContent = "";
    body.innerHTML = "";
    return;
  }
  liveAge();
  const teams = LIVE.teams || {};
  $("#liveSub").textContent = `Gameweek ${LIVE.gw} — live as of the watcher's last run, ` +
    `re-fetched every 2 minutes.`;

  if (LIVE.status === "pre_deadline") {
    const fx = (LIVE.fixtures || []).map(f =>
      `<tr><td class="l">${teams[f.home] || f.home}</td><td class="hint">vs</td>
       <td class="l">${teams[f.away] || f.away}</td></tr>`).join("");
    body.innerHTML = `<p class="note">Deadline has passed but no fixture has kicked off yet —
      nothing to score. The week's fixtures:</p><table class="tight">${fx}</table>`;
    return;
  }

  /* fixtures */
  const fx = `<div class="tiles" style="margin-bottom:14px">` +
    (LIVE.fixtures || []).map(f => {
      const st = f.finished ? "finished" : f.started ? "in play" : "kick-off to come";
      const dim = f.started && !f.finished ? "" : " hint";
      return `<div class="tile"><div class="k">${teams[f.home] || f.home} — ${teams[f.away] || f.away}</div>
        <div class="v">${f.started ? `${f.hs ?? "–"} : ${f.as ?? "–"}` : "vs"}</div>
        <div class="n${dim}">${st}</div></div>`;
    }).join("") + `</div>`;

  /* one card per compared entry: live + projected + leagues, stated edges */
  const cards = (LIVE.entries || []).map(en => {
    const meta = en.meta || {};
    const mine = (LIVE.entry_ids || []).includes(en.entry_id);
    const dR = (meta.overall_rank && meta.prev_rank) ? meta.prev_rank - meta.overall_rank : null;
    const lgs = ((en.leagues || {}).classic || []).slice(0, 4).map(l =>
      `${l.name.slice(0, 26)}: ${num(l.rank)}/${num(l.size)}`).join(" · ");
    const cups = ((en.leagues || {}).cups || []).map(c =>
      `🏆 ${c.name.slice(0, 26)} — round ${c.round}, ${c.state || c.status}`).join(" · ");
    const rows = [...(en.players || [])].sort((a, b) =>
      (b.xi - a.xi) || (b.live - a.live));
    const tbl = `<table><thead><tr><th class="l">Player</th><th class="l">Club</th>
      <th class="l">Pos</th><th>Min</th><th>Live</th><th>Proj final</th><th></th></tr></thead>
      <tbody>${rows.map(p => {
        const gap = p.minutes > 0 ? p.live - p.proj_final : null;
        const cls = gap > 0.5 ? "up" : gap < -0.5 ? "down" : "";
        return `<tr${p.xi ? "" : ' class="hint"'}>
          <td class="l">${p.captain ? "© " : ""}${p.name}</td>
          <td class="l hint">${p.team}</td><td class="l hint">${p.pos}</td>
          <td>${p.xi ? num(p.minutes) : "bench"}</td>
          <td class="${cls}">${fmt(p.live, 0)}</td>
          <td>${fmt(p.proj_final, 1)}</td>
          <td class="hint">${p.xi ? "" : p.minutes > 0 ? "subbed on" : ""}</td></tr>`;
      }).join("")}</tbody></table>`;
    return `<div class="card" style="margin-top:14px">
      <header><div><h3>${en.name} ${chipBadge(en.chip)}</h3>
        <p class="sub">Live vs projected for this gameweek — the projection is the same
        model the deadline plans use, not a live-updating guess.</p></div>
        ${mine ? `<span class="flag f-diff">mine</span>` : ""}</header>
      <div class="tiles" style="margin-bottom:12px">
        <div class="tile"><div class="k">Live points</div><div class="v">${num(en.live_pts)}</div>
          <div class="n">FPL's total, autosubs applied</div></div>
        <div class="tile"><div class="k">Projected final</div><div class="v">${fmt(en.proj_final, 1)}</div>
          <div class="n">model projection, bench counted</div></div>
        <div class="tile"><div class="k">Overall rank</div><div class="v">${num(meta.overall_rank)}</div>
          <div class="n">${num(meta.overall_pts)} pts overall</div></div>
        <div class="tile"><div class="k">Rank move last gw</div>
          <div class="v" style="color:${dR == null ? "inherit" : dR > 0 ? css("--s1") : css("--critical")}">${dR == null ? "–" : (dR > 0 ? "▲ " : dR < 0 ? "▼ " : "— ") + num(Math.abs(dR))}</div>
          <div class="n">up means the rank fell toward 1</div></div>
      </div>
      ${lgs ? `<p class="sub" style="margin:0 0 4px"><b>Leagues:</b> ${lgs}</p>` : ""}
      ${cups ? `<p class="sub" style="margin:0 0 8px">${cups}</p>` : ""}
      ${tbl}
<p class="note">The live total is FPL's (autosubs already applied); rows are computed from
  the picked XI, so a bench player who autosubbed in can show points the live total does
  not include. "Proj final" counts yet-to-feature players at their model projection.</p>
    </div>`;
  }).join("");

  /* mini-league standings around the compared entries */
  const tbls = Object.values(LIVE.leagues || {}).filter(t => t && t.name && t.rows && t.rows.length)
    .map(t => {
      const mineRanks = t.rows.filter(r => r.mine).map(r => r.rank);
      const lo = mineRanks.length ? Math.min(...mineRanks) : null;
      const show = t.rows.filter(r => r.mine ||
        (lo != null && Math.abs(r.rank - lo) <= 2)).slice(0, 9);
      return `<div class="card" style="margin-top:14px"><h3>${t.name}</h3>
        <table><thead><tr><th>#</th><th class="l">Manager</th><th class="l">Team</th>
          <th>Pts</th><th>GW</th></tr></thead><tbody>${show.map(r =>
        `<tr${r.mine ? ' style="font-weight:700"' : ' class="hint"'}>
          <td>${num(r.rank)}</td><td class="l">${r.player || r.manager}</td>
          <td class="l hint">${r.manager}</td><td>${num(r.pts)}</td>
          <td>${fmt(r.last, 0)}</td></tr>`).join("")}</tbody></table>
        <p class="note">Your entries in bold, with rivals within two places for context.</p></div>`;
    }).join("");

  body.innerHTML = fx + cards + tbls;
}
async function fetchLive() {
  try {
    const r = await fetch("live.json", {cache: "no-store"});
    if (!r.ok) throw 0;
    LIVE = await r.json();
  } catch (e) { LIVE = LIVE || {}; }
  renderLivescore();
}
fetchLive();
setInterval(fetchLive, 120000);

/* ============================================================== ACCURACY */
function renderAccuracy() {
  const acc = (D.history && D.history.accuracy) || [];
  if (!acc.length) {
    $("#accBody").innerHTML = `<div class="empty">
      Nothing graded yet. The projection for each gameweek is saved before its deadline,
      and scored the moment the gameweek finishes — so this fills itself in from gameweek 1.
    </div>`;
    return;
  }
  const last = acc[acc.length - 1];
  const prov = (D.history && D.history.provisional) || [];
  const provNote = prov.includes(last.gw)
    ? `<div class="note">Gameweek ${last.gw} is graded on provisional bonus — the game has
       not written the final bonus points down yet, so a player here can still move by a
       point or two. It regrades itself on the next run after that lands.</div>` : "";
  const mae = acc.map(a => ({x: a.gw, y: a.mae}));
  const bias = acc.map(a => ({x: a.gw, y: a.bias}));
  const posRows = Object.entries(last.by_pos || {}).map(([p, v]) => `<tr>
    <td class="l">${p}</td><td>${v.n}</td><td>${fmt(v.proj, 2)}</td>
    <td>${fmt(v.actual, 2)}</td>
    <td>${v.bias >= 0 ? "+" : ""}${fmt(v.bias, 2)}</td>
    <td>${fmt(v.mae, 2)}</td></tr>`).join("");
  const miss = (last.worst_misses || []).map(m => `<tr>
    <td class="l">${m.name}</td><td class="l hint">${m.pos}</td>
    <td>${fmt(m.proj, 1)}</td><td>${m.actual}</td>
    <td class="down">${fmt(m.actual - m.proj, 1)}</td></tr>`).join("");
  const best = (last.best_calls || []).map(m => `<tr>
    <td class="l">${m.name}</td><td class="l hint">${m.pos}</td>
    <td>${fmt(m.proj, 1)}</td><td>${m.actual}</td>
    <td class="up">+${fmt(m.actual - m.proj, 1)}</td></tr>`).join("");

  $("#accBody").innerHTML = provNote + `
    <div class="tiles" style="margin-bottom:14px">
      <div class="tile"><div class="k">Average error, GW${last.gw}</div>
        <div class="v">${fmt(last.mae, 2)}</div><div class="n">points per player, ${last.n} players judged</div></div>
      <div class="tile"><div class="k">Bias</div>
        <div class="v">${last.bias >= 0 ? "+" : ""}${fmt(last.bias, 2)}</div>
        <div class="n">${last.bias >= 0 ? "under" : "over"}-projecting on average</div></div>
    </div>
    <div class="split">
      <div><h3>Error by gameweek</h3><div id="maeChart"></div></div>
      <div><h3>By position, GW${last.gw}</h3>
        <table><thead><tr><th class="l">Pos</th><th>n</th><th>Proj</th><th>Actual</th>
          <th>Bias</th><th>Error</th></tr></thead><tbody>${posRows}</tbody></table></div>
    </div>
    <div class="split">
      <div><h3>Worst misses</h3><table><thead><tr><th class="l">Player</th><th class="l"></th>
        <th>Proj</th><th>Actual</th><th>Diff</th></tr></thead><tbody>${miss}</tbody></table></div>
      <div><h3>Best calls</h3><table><thead><tr><th class="l">Player</th><th class="l"></th>
        <th>Proj</th><th>Actual</th><th>Diff</th></tr></thead><tbody>${best}</tbody></table></div>
    </div>
    <p class="note">Only players who featured, or were projected at 1.5 points or more, are
      judged — grading the model on the hundreds it correctly projected near zero would
      flatter it. A bias above zero means it is under-projecting.</p>`;
  lineChart($("#maeChart"), [
    {name: "Average error", color: css("--s1"), points: mae},
    {name: "Bias", color: css("--s2"), points: bias},
  ], {xPrefix: "GW", zero: true, fmtY: v => v.toFixed(1)});
}

/* =============================================================== PLAYERS */
const COLS = [
  ["name", "Player", "l", ""], ["pos", "Pos", "l", ""], ["team", "Club", "l", ""],
  ["price", "£", "", ""], ["selected_by", "Own %", "", ""],
  ["start_share", "Start %", "", "hide-s"],
  ["xp" + G0, "GW" + G0, "", ""], ["xp3", "3 GW", "", ""], ["xp_total", "5 GW", "", ""],
  ["ceiling3", "Ceil 3", "", "hide-s"], ["ceiling_total", "Ceil 5", "", "hide-s"],
  ["value", "Pts/£m", "", "hide-s"], ["hist_pts", "25/26", "", "hide-s"],
];
let sortKey = "xp_total", sortDir = -1;
[...new Set((D.players || []).map(p => p.team))].sort().forEach(t =>
  $("#fTeam").insertAdjacentHTML("beforeend", `<option>${t}</option>`));
function renderTable() {
  const pos = $("#fPos").value, team = $("#fTeam").value,
    maxP = +$("#fPrice").value, maxO = +($("#fOwnQuick").value || 101),
    q = $("#fSearch").value.toLowerCase();
  const rows = (D.players || []).filter(p =>
    (!pos || p.pos === pos) && (!team || p.team === team) &&
    p.price <= maxP && p.selected_by <= maxO &&
    (!q || p.name.toLowerCase().includes(q)));
  rows.sort((a, b) => (a[sortKey] > b[sortKey] ? 1 : a[sortKey] < b[sortKey] ? -1 : 0) * sortDir);
  $("#cnt").textContent = rows.length + " players";
  $("#tbl").innerHTML = `<thead><tr>${COLS.map(([k, l, c, h]) =>
    `<th class="${c} ${h}" data-k="${k}">${l}${sortKey === k ? (sortDir < 0 ? " ↓" : " ↑") : ""}</th>`).join("")}<th class="l">Flag</th></tr></thead>
    <tbody>${rows.slice(0, 350).map(p => `<tr>
      <td class="l">${p.name}</td><td class="l">${p.pos}</td><td class="l">${p.team}</td>
      <td>${fmt(p.price)}</td><td>${fmt(p.selected_by, 1)}</td>
      <td class="hide-s">${Math.round(p.start_share * 100)}</td>
      <td>${fmt(p["xp" + G0], 2)}</td><td>${fmt(p.xp3, 1)}</td><td>${fmt(p.xp_total, 1)}</td>
      <td class="hide-s">${fmt(p.ceiling3, 1)}</td><td class="hide-s">${fmt(p.ceiling_total, 1)}</td>
      <td class="hide-s">${fmt(p.value, 2)}</td><td class="hide-s">${p.hist_pts}</td>
      <td class="l">${p.status !== "a" ? '<span class="flag f-crit">doubt</span>'
        : p.start_share < 0.5 ? '<span class="flag f-warn">rotation</span>'
        : p.selected_by < DIFF_OWN ? '<span class="flag f-diff">diff</span>' : ""}</td>
      </tr>`).join("")}</tbody>`;
  $("#tbl").querySelectorAll("th[data-k]").forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = -1; }
    renderTable();
  });
}
["fPos", "fTeam", "fPrice", "fSearch", "fOwnQuick"].forEach(id =>
  $("#" + id).addEventListener("input", renderTable));

/* =============================================================== CHANGES */
function renderChanges() {
  const c = D.changes || {};
  if (c.first_run) {
    $("#changeBody").innerHTML = `<div class="empty">First run — nothing to compare against yet.</div>`;
    return;
  }
  const bits = [];
  if ((c.prices || []).length) bits.push(`<h3>Price moves</h3><table><tbody>${
    c.prices.map(p => `<tr><td class="l">${p.name} <span class="hint">${p.team}</span>
      ${p.owned ? '<span class="flag f-diff">owned</span>' : ""}</td>
      <td>£${fmt(p.from)} → <b>£${fmt(p.to)}</b></td>
      <td class="${p.to > p.from ? "up" : "down"}">${p.to > p.from ? "▲" : "▼"}</td></tr>`).join("")}</tbody></table>`);
  if ((c.news || []).length) bits.push(`<h3>Availability</h3><table><tbody>${
    c.news.map(p => `<tr><td class="l">${p.name} <span class="hint">${p.team}</span>
      ${p.owned ? '<span class="flag f-diff">owned</span>' : ""}</td>
      <td class="l">${p.note || p.status}</td></tr>`).join("")}</tbody></table>`);
  if ((c.plan || []).length) bits.push(`<h3>Plan changed</h3><table><tbody>${
    c.plan.map(p => `<tr><td class="l"><b>${p.team}</b></td>
      <td class="l">now buying ${p.added.map(i => byId[i] ? byId[i].name : i).join(", ") || "–"}</td>
      <td class="l hint">was ${p.dropped.map(i => byId[i] ? byId[i].name : i).join(", ") || "–"}</td></tr>`).join("")}</tbody></table>`);
  $("#changeBody").innerHTML = bits.length ? bits.join("")
    : `<div class="empty">Nothing moved since the last run.</div>`;
}

/* ================================================================ METHOD */
$("#method").innerHTML = `
  Every player gets a per-start rate for each scoring component — goals, assists, clean
  sheets, goals conceded, saves, defensive contribution, bonus and cards — estimated from
  their gameweek-by-gameweek record, blended with expected goals and expected assists so a
  hot or cold finishing run is not extrapolated, and shrunk toward what a player at that
  price normally returns. Minutes are modelled as the chance of being available multiplied
  by the chance of starting when available, so an injury-hit season does not permanently
  brand a now-fit player a rotation risk. Club attack and defence ratings come from goals
  and expected goals; newly promoted clubs get typical promoted-side ratings until they
  have played. Each fixture scales the attacking components by that match's expected goals
  and the clean-sheet components by a Poisson clean-sheet probability. The ceiling score
  reweights the explosive components upward, because a captain or a differential is bought
  for its upside rather than its median. Transfers are then chosen by one integer program
  across the whole horizon that also decides free transfers, banking and whether a −4 pays,
  with Minoux_69 locking Haaland in and leaning template, and Minoux_41 barring him,
  holding nine players under 8% ownership and optimising ceiling. Once real gameweeks are
  played the model folds them in automatically and grades itself above.`;

/* ================================================================== BOOT */
function redrawCharts() { seasonCharts(); renderScatter(); renderAccuracy(); renderChipCalendar(); }
let rt;
addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(redrawCharts, 180); });

tiles(); syncSquad(); renderPlan(); renderCap(); renderTemplate(); renderChipTabs();
renderTicker(); renderChips(); renderPrice(); renderElite(); renderEngines(); renderTable(); renderChanges(); redrawCharts();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print(build())
