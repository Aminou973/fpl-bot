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
  5. a chip in the plan (engine 7's wildcard) must be unspent in the live
     entry history and must activate together with its transfer batch — if
     the activation is refused, the moves are NOT sent as paid transfers
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
from fplbot.notify import esc                                 # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# chips that ride ON the lineup write rather than the transfers endpoint ——
# triple captain and bench boost do not change the squad, so they activate
# with the picks (a wildcard activates WITH its transfer batch instead)
PICK_CHIPS = ("3xc", "bboost")


def live_picks_sig(mt):
    """Comparable signature of the squad as the game currently holds it."""
    return [(p["element"], bool(p.get("is_captain")),
             bool(p.get("is_vice_captain", p.get("is_vice"))))
            for p in sorted(mt["picks"], key=lambda p: p.get("position", 0))]


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
    """Collect refresh tokens from the environment, as (secret_name, token).

    One per FPL account: FPL_REFRESH_TOKEN (or FPL_REFRESH_TOKEN_1) for the
    first, FPL_REFRESH_TOKEN_2, _3, … for further ones. Two squads on two
    separate accounts means two secrets. Tokens come from the one-time
    browser login in jobs/fpl_login.py.
    """
    import os
    out = []
    first = os.environ.get("FPL_REFRESH_TOKEN") or os.environ.get("FPL_REFRESH_TOKEN_1")
    if first:
        out.append(("FPL_REFRESH_TOKEN", first))
    for i in range(2, 6):
        rt = os.environ.get(f"FPL_REFRESH_TOKEN_{i}")
        if rt:
            out.append((f"FPL_REFRESH_TOKEN_{i}", rt))
    return out


def store_secret(name: str, value: str) -> bool:
    """Write a rotated refresh token back to its repo secret.

    FPL rotates (and invalidates) refresh tokens on every exchange, so the
    new token must be persisted where the next run finds it. This works from
    Actions when GH_TOKEN is a PAT with the Secrets write permission
    (FPL_PAT); locally it uses the logged-in gh CLI. Returns True on success.
    """
    import os
    import subprocess
    try:
        subprocess.run(["gh", "secret", "set", name, "--body", value],
                       check=True, capture_output=True)
        return True
    except Exception:                                        # noqa: BLE001
        return False


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

    tokens = credentials()
    if not tokens:
        sys.exit("no FPL refresh tokens set — run jobs/fpl_login.py once per "
                 "account and store the tokens as FPL_REFRESH_TOKEN / "
                 "FPL_REFRESH_TOKEN_2 repo secrets")

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

    # authenticate every account once via its refresh token; each entry is
    # handled by the account that actually manages it. A dead token only
    # takes out its own account — the run continues with the rest. Each
    # failure rings once (tracked in state) and the silence resets the
    # moment that account works again, so a fresh failure rings again.
    sessions = {}          # entry_id -> (session, my-team id)
    auth_state = pipeline.read_state("auth_alerts", {"dead": [], "unstored": []})
    dead = set(auth_state.get("dead", []))
    unstored = set(auth_state.get("unstored", []))
    for i, (secret_name, rt) in enumerate(tokens, 1):
        try:
            tok = api.refresh_tokens(rt)
        except RuntimeError as e:
            print(f"[auth] token {i} ({secret_name}) refresh FAILED: {e} — "
                  f"re-run jobs/fpl_login.py for that account")
            if secret_name not in dead:
                notify.send(
                    f"🔐 <b>FPL login failed — {esc(secret_name)}</b>\n\n"
                    f"The stored login was rejected ({esc(str(e)[:100])}).\n"
                    f"Run <code>python jobs/fpl_login.py --account {i} "
                    f"--set-secret</code> and log in with that account. "
                    f"Its squads are skipped until then.", kind="alert")
            dead.add(secret_name)
            continue
        dead.discard(secret_name)
        new_rt = tok.get("refresh_token")
        if new_rt and new_rt != rt:
            # FPL rotates (and invalidates) refresh tokens on every exchange:
            # persist the new one or the account dead-ends after this run
            if store_secret(secret_name, new_rt):
                print(f"[auth] refresh token rotated for {secret_name} — "
                      f"secret updated")
                unstored.discard(secret_name)
            else:
                print(f"[auth] WARNING: refresh token rotated for "
                      f"{secret_name} but the secret could NOT be updated "
                      f"(needs FPL_PAT with Secrets write permission) — "
                      f"this account will stop working after this run; "
                      f"re-run jobs/fpl_login.py for it")
                if secret_name not in unstored:
                    notify.send(
                        f"⚠️ <b>Token not saved — {esc(secret_name)}</b>\n\n"
                        f"FPL rotated the login but the repo secret could not "
                        f"be updated (FPL_PAT missing or lacking Secrets "
                        f"write). This account dies after this run — "
                        f"re-set FPL_PAT, then re-run jobs/fpl_login.py.",
                        kind="alert")
                unstored.add(secret_name)
        s = api.api_session(tok["access_token"])
        account_teams = api.me(s)
        print(f"authenticated (token {i}); manages entries "
              f"{sorted(account_teams)}")
        for entry_id, team_id in account_teams.items():
            sessions[entry_id] = (s, team_id)
    pipeline.write_state("auth_alerts", {"dead": sorted(dead),
                                         "unstored": sorted(unstored)})

    names = name_lookup(boot)
    boot_el_cost = {p["id"]: p["now_cost"] for p in boot["elements"]}

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
                  f"account — re-arm that account with jobs/fpl_login.py")
            continue
        session, team_id = sessions[entry_id]
        mt = api.my_team(session, team_id)
        if live_picks_sig(mt) == plan_sig(entry["picks_payload"]):
            results[name] = {"status": "already-applied", "gw": gw}
            print(f"[{name}] live squad already matches the plan — nothing to do")
            continue
        print(f"[{name}] entry {entry_id} (my-team id {team_id})")
        for line in diff_names(names, live_picks_sig(mt),
                               plan_sig(entry["picks_payload"])):
            if line:
                print(f"  {line}")
        print(f"  planned hits {entry['hits']}, squad after submit: "
              f"{len(entry['picks_payload'])} players")
        chip = entry.get("chip")
        if chip:
            how = ("rides on the lineup write"
                   if chip in PICK_CHIPS else "activates with the transfers")
            print(f"  🃏 chip {chip.upper()} in the plan — {how}"
                  + (f" (modelled gain +{entry.get('chip_gain')} xp)"
                     if entry.get("chip_gain") is not None else ""))
            used = {c.get("name")
                    for c in (api.entry_history(entry_id).get("chips") or [])}
            if chip in used:
                results[name] = {"status": "refused", "gw": gw,
                                 "note": f"chip {chip} is already spent — "
                                         f"not arming it again"}
                print(f"  ✘ refusing: {chip} already spent")
                continue
        if not a.apply:
            results[name] = {"status": "dry-run"}
            continue
        # the my-team endpoint only writes a lineup from players already in
        # the squad — transfers go through /transfers/ first, priced with the
        # in-player's current cost and the out-player's selling price
        owned = {p["element"]: p for p in mt["picks"]}
        legs = []
        for el_in, el_out in zip(entry["in"], entry["out"]):
            if el_in in owned:
                print(f"  transfer {names.get(el_in, el_in)} already owned — skipped")
                continue
            if el_out not in owned:
                print(f"  cannot sell {names.get(el_out, el_out)} — not owned "
                      f"(already sold?) — skipped")
                continue
            legs.append({"element_in": el_in, "element_out": el_out,
                         "purchase_price": boot_el_cost[el_in],
                         "selling_price": owned[el_out].get("selling_price", 0)})
        if legs or chip:
            if chip and chip not in PICK_CHIPS:
                # wildcard (and a future free hit): the chip and its whole
                # transfer batch go in ONE call, so the game can never take
                # the moves without the chip. If the activation is refused,
                # stop dead: un-chipping a wildcard's moves means paying a
                # fortune in points for them.
                try:
                    api.make_transfers(session, entry_id, gw, legs, chip=chip)
                except Exception as e:                       # noqa: BLE001
                    msg = (f"chip {chip} activation failed — transfers NOT "
                           f"sent as paid moves: {e}")
                    notify.send(
                        f"🚨 <b>{esc(name)} — {esc(chip.upper())} FAILED</b>\n\n"
                        f"{esc(str(e)[:300])}\n\nThe moves were not paid for. "
                        f"Play the chip manually or re-arm after fixing.",
                        kind="alert")
                    results[name] = {"status": "chip-failed", "gw": gw,
                                     "chip": chip, "note": msg}
                    print(f"  ✘ {msg}")
                    continue
                print(f"  ✔ {chip} activated with {len(legs)} moves")
            elif legs:
                api.make_transfers(session, entry_id, gw, legs)
                print(f"  ✔ transfers made: "
                      + ", ".join(f"{names.get(l['element_in'])} in for "
                                  f"{names.get(l['element_out'])}" for l in legs))
        else:
            print("  no transfers to make — lineup only")
        # a triple captain or bench boost rides ON the lineup write (it does
        # not touch transfers); a wildcard was already activated above
        api.submit_picks(session, team_id, entry["picks_payload"],
                         chip=chip if chip in PICK_CHIPS else None)
        results[name] = {"status": "applied", "team_id": team_id,
                         "gw": gw, "in": entry["in"], "out": entry["out"],
                         "captain": entry["captain"]}
        if chip:
            results[name]["chip"] = chip
        print(f"  ✔ applied")

    log["gws"][str(gw)] = {
        "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "deadline": deadline, "mode": "apply" if a.apply else "dry-run",
        "teams": results}
    pipeline.write_state("auto_submit", log)
    print(f"[submit] {'applied' if a.apply else 'dry run'} for GW{gw}: "
          + ", ".join(f"{k}={v['status']}" for k, v in results.items()))

    # audible alert when the bot actually acted (or could not)
    if results:
        marks = {"applied": "✅", "already-applied": "✔", "skipped": "⚠️",
                 "dry-run": "•", "chip-failed": "🚨", "refused": "🚫"}
        body = "\n".join(f"{marks.get(v['status'], '•')} <b>{esc(k)}</b> — "
                         f"{esc(v.get('note') or v['status'])}"
                         for k, v in results.items())
        notify.send(f"🤖 <b>GW{gw} {'lineup applied' if a.apply else 'dry run'}</b>\n\n"
                    + body, kind="alert")
    played = {k: v["chip"] for k, v in results.items()
              if v.get("status") == "applied" and v.get("chip")}
    if played and a.apply:
        # chips are once-a-season: a played one is worth its own alert, not a
        # line inside a routine summary
        notify.send(
            "🃏 <b>CHIP PLAYED</b>\n\n" + "\n".join(
                f"<b>{esc(k)}</b> — {esc(v.upper())} played for GW{gw}"
                + (f" (modelled gain +{esc(str(wanted[k].get('chip_gain')))} xp)"
                   if wanted[k].get("chip_gain") else "")
                for k, v in played.items()), kind="alert")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                              # noqa: BLE001
        notify.send(f"🚨 <b>Submit failed</b>\n\n{esc(str(e))}", kind="alert")
        raise