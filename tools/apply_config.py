"""Add the one-decision-per-week settings to config.yml, preserving comments.

    python3 tools/apply_config.py

Edits the file as text rather than round-tripping it through the YAML dumper,
because config.yml is heavily commented and those comments are the only
documentation of why each engine is tuned the way it is. Only writes what is
missing, so it is safe to run twice.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config.yml"

CAPS = {"Minoux_69": 2, "Minoux_41": 3}

TAIL = """
# ---------------------------------------------------------------- the brief --
# One transfer decision per gameweek, published once, late enough that the team
# news is real. The plan workflow fires hourly; the job picks the last slot that
# is still min_lead_minutes clear of the deadline, so the message lands between
# roughly one and two hours out. Every other hour exits in seconds.
brief:
  min_lead_minutes: 60      # never closer than this to the deadline
  max_lead_minutes: 150     # never earlier than this
  refresh_hours_utc: [7, 13, 19]   # hours that rebuild the dashboard quietly
  cron_minute_utc: 5        # must match the cron in .github/workflows/plan.yml
  lock_margin: 1.5          # xP a new move must beat the committed one by

# --------------------------------------------------------------- submission --
submit:
  # The bot may spend free transfers on its own. It may not spend POINTS on its
  # own: a plan that costs a hit is sent to Telegram for a human to approve.
  auto_hits: false
"""


def main():
    text = CFG.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    changed = []

    lines = text.splitlines()
    for team, cap in CAPS.items():
        node = (cfg.get("teams") or {}).get(team)
        if node is None:
            print(f"  ! no team called {team} in config.yml, skipped")
            continue
        if "max_transfers_per_gw" in (node or {}):
            continue
        # Walk the file rather than pattern-match it: find this team's key, then
        # the first hit_threshold line that still belongs to it, and insert at
        # that line's own indentation. A regex here kept sliding across team
        # blocks and writing the setting into the wrong squad.
        at = next((i for i, ln in enumerate(lines)
                   if ln.strip() == f"{team}:"), None)
        if at is None:
            print(f"  ! could not find the {team} block, skipped")
            continue
        depth = len(lines[at]) - len(lines[at].lstrip())
        put = None
        for i in range(at + 1, len(lines)):
            ln = lines[i]
            if ln.strip() and (len(ln) - len(ln.lstrip())) <= depth:
                break                     # next team, or back out of the block
            if ln.lstrip().startswith("hit_threshold:"):
                put = i
                break
        if put is None:
            print(f"  ! no hit_threshold line inside {team}, skipped")
            continue
        indent = " " * (len(lines[put]) - len(lines[put].lstrip()))
        lines.insert(put + 1, f"{indent}max_transfers_per_gw: {cap}"
                              f"   # hard ceiling on moves in one gameweek")
        changed.append(f"teams.{team}.max_transfers_per_gw = {cap}")
    text = "\n".join(lines) + "\n"

    if "brief" not in cfg:
        text = text.rstrip("\n") + "\n" + TAIL
        changed.append("brief block")
    elif "submit" not in cfg:
        text = text.rstrip("\n") + "\n" + TAIL.split("# ---------------------------------------------------------------- submission --")[0]
        changed.append("submit block")

    if not changed:
        print("config.yml already has everything — nothing to do")
        return 0
    yaml.safe_load(text)          # refuse to write anything that will not parse
    CFG.write_text(text, encoding="utf-8")
    print("config.yml updated (comments preserved):")
    for c in changed:
        print("  +", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
