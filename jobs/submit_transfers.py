"""Auto-submit the planned lineup for both teams before the deadline.

Reads state/last_plan.json (written by the deadline plan job), logs in to FPL,
and writes the planned 15-player picks for each team. Without --apply it is a
pure dry run: login, read the live squad, print exactly what would change, exit.

Guards, in order — a submit job acting unattended must refuse rather than
guess:
  1. the plan must be for the gameweek whose deadline is actually next
  2. the plan must be fresh (deadline within the act window, default 36h)
  3. the plan's squads must have come from the API (never the config fallback)
  4. if the live squad already equals the plan, do nothing
Credentials come from FPL_EMAIL / FPL_PASSWORD environment variables.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import api, notify, pipeline                      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def live_picks_sig(mt):
    """Comparable signature of the squad as the game currently holds it."""
    return [(p["element"], bool(p["is_captain"]), bool(p["is_vice"]))
            for p in sorted(mt["picks"], key=lambda p: p["position"])]


def plan_sig(payload):
    return [(p["element"], p["is_captain"], p["is_vice"])
            for p in sorted(payload, key=lambda p: p["position"])]


def name_lookup(boot):
    """element id -> "Name (TEAM)" for readable diffs."""
    teams = {t["id"]: t["short_name"] for t in boot["teams"]}
    return {p["id"]: f"{p['web_name']} ({teams[p['team']]})"
            for p in boot["elements"]}


def diff_names(names, live, target):
    cur = {e for e, _, _ in live}
    new = {e for e, _, _ in target}
    out, inn = sorted(cur - new), sorted(new - cur)
    name = lambda i: names.get(i, str(i))          # noqa: E731
    cap = next((e for e, c, _ in target if c), None)
    return [f"OUT {', '.join(map(name, out))}" if out else "",
            f"IN  {', '.join(map(name, inn))}" if inn else "",
            f"Captain {name(cap)}" if cap else ""]


def credentials():
    """Collect (email, password) pairs from the environment.

    One or more FPL accounts: FPL_EMAIL/FPL_PASSWORD for the first, then
    FPL_EMAIL_2/FPL_PASSWORD_2, _3, … for further ones (FPL_EMAIL_1 also
    accepted). Two squads on two separate accounts means four secrets.
    """
    import os
    pairs = []
    first = (os.environ.get("FPL_EMAIL"), os.environ.get("FPL_PASSWORD"))
    if all(first):
        pairs.append(first)
    for i in range(1, 6):
        e, p = os.environ.get(f"FPL_EMAIL_{i}"), os.environ.get(f"FPL_PASSWORD_{i}")
        if e and p:
            pairs.append((e, p))
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually write the lineup; default is a dry run")
    ap.add_argument("--team", help="restrict to one configured team name")
    ap.add_argument("--force", action="store_true",
                    help="run even if the deadline is outside the act window")
    ap.add_argument("--untested", action="store_true",
                    help="allow --apply without a prior successful dry run "
                         "for this gameweek (local debugging only)")
    ap.add_argument("--window", type=float, default=36.0,
                    help="hours before deadline inside which submission is allowed")
    a = ap.parse_args()

    pairs = credentials()
    if not pairs:
        sys.exit("no FPL credentials set — FPL_EMAIL/FPL_PASSWORD (plus "
                 "FPL_EMAIL_2/FPL_PASSWORD_2 … for extra accounts)")

    cfg = pipeline.load_config()
    plan = pipeline.read_state("last_plan")
    if not plan or not plan.get("teams"):
        sys.exit("state/last_plan.json is missing or empty — run the plan first")

    boot = api.bootstrap()
    nxt = api.next_event(boot)
    gw, deadline = nxt["id"], nxt.get("deadline_time", "")
    if plan.get("gw") != gw:
        sys.exit(f"plan is for GW{plan.get('gw')} but the next deadline is "
                 f"GW{gw} — stale plan, refusing to act")
    if deadline:
        d = dt.datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        hrs = (d - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
        if hrs <= 0:
            sys.exit(f"GW{gw} deadline already passed ({deadline})")
        if not a.force and hrs > a.window:
            print(f"GW{gw} deadline {hrs:.1f}h away — outside the "
                  f"{a.window:.0f}h window, nothing to do")
            return
        print(f"GW{gw} deadline in {hrs:.1f}h")

    # only teams whose plan came from the live API squad are submittable
    teams = [a.team] if a.team else [n for n in cfg["teams"] if n in plan["teams"]]
    wanted, entries = {}, {}
    for n in teams:
        entry = plan["teams"].get(n)
        if not entry:
            print(f"[{n}] not in the plan — skipped")
            continue
        if entry.get("squad_source") != "api":
            print(f"[{n}] plan squad source is "
                  f"'{entry.get('squad_source')}' — refusing to submit a "
                  f"squad that did not come from the live API")
            continue
        wanted[n] = entry
        entries[n] = int(entry["entry"])
    if not wanted:
        sys.exit("no submittable teams in the plan")

    # log in to every account once; each entry is handled by the account
    # that actually manages it
    sessions = {}          # entry_id -> (session, my-team id)
    for email, password in pairs:
        s, account_teams = api.login(email, password)
        print(f"logged in ({email}); manages entries {sorted(account_teams)}")
        for entry_id, team_id in account_teams.items():
            sessions[entry_id] = (s, team_id)

    names = name_lookup(boot)

    # a real submission must be preceded by a successful dry run for this
    # gameweek: the first scheduled tick verifies login and prints the diff,
    # the next one (an hour later, still hours before the deadline) applies
    log = pipeline.read_state("auto_submit", {"gws": {}})
    prior = (log.get("gws", {}).get(str(gw)) or {})
    prior_ok = any(v.get("status") in ("dry-run", "applied", "already-applied")
                   for v in (prior.get("teams") or {}).values())
    if a.apply and not prior_ok and not a.untested:
        print(f"no successful dry run for GW{gw} yet — running dry first; "
              f"the next hourly run will apply")
        a.apply = False

    results = {}
    for name, entry in wanted.items():
        entry_id = entries[name]
        if entry_id not in sessions:
            results[name] = {"status": "skipped",
                             "note": f"entry {entry_id} is on none of the "
                                     f"logged-in accounts"}
            print(f"[{name}] skipped: entry {entry_id} not on any logged-in "
                  f"account — check FPL_EMAIL(_2) cover both squads")
            continue
        session, team_id = sessions[entry_id]
        mt = api.my_team(session, team_id)
        if live_picks_sig(mt) == plan_sig(entry["picks_payload"]):
            results[name] = {"status": "already-applied"}
            print(f"[{name}] live squad already matches the plan — nothing to do")
            continue
        print(f"[{name}] entry {entry_id} (my-team id {team_id})")
        for line in diff_names(names, live_picks_sig(mt),
                               plan_sig(entry["picks_payload"])):
            if line:
                print(f"  {line}")
        print(f"  planned hits {entry['hits']}, squad after submit: "
              f"{len(entry['picks_payload'])} players")
        if not a.apply:
            results[name] = {"status": "dry-run"}
            continue
        api.submit_picks(session, team_id, entry["picks_payload"])
        results[name] = {"status": "applied", "team_id": team_id,
                         "gw": gw, "in": entry["in"], "out": entry["out"],
                         "captain": entry["captain"]}
        print(f"  ✔ applied")

    log["gws"][str(gw)] = {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "deadline": deadline, "mode": "apply" if a.apply else "dry-run",
        "teams": results}
    pipeline.write_state("auto_submit", log)
    print(f"[submit] {'applied' if a.apply else 'dry run'} for GW{gw}: "
          + ", ".join(f"{k}={v['status']}" for k, v in results.items()))


if __name__ == "__main__":
    main()