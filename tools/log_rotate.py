"""
Compact the price log so it cannot outgrow the repository.

state/price_log.jsonl grows every hour, and the first line of each UTC day is a
full ~700-element snapshot. Everything older than --keep-days (default 60) is
collapsed to one line per day — the day's last full snapshot if there is one,
otherwise its last delta line — which keeps daily price levels and the day's
final transfer counts without the hourly churn.

Usage:  python tools/log_rotate.py [--keep-days 60] [--log state/price_log.jsonl]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def rotate(path: Path, keep_days: int):
    if not path.exists():
        print(f"[log-rotate] {path.name} does not exist yet — nothing to do")
        return
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)
    lines = [json.loads(x) for x in
             path.read_text(encoding="utf-8").splitlines() if x.strip()]

    keep, compact = [], {}
    for rec in lines:
        ts = dt.datetime.fromisoformat(rec["ts"][:19]).replace(tzinfo=dt.timezone.utc)
        if ts >= cutoff:
            keep.append(rec)
            continue
        # prefer the day's full snapshot; otherwise remember the latest delta
        if rec["ts"][:10] not in compact or rec.get("full"):
            compact[rec["ts"][:10]] = rec
    out = list(compact.values()) + keep
    out.sort(key=lambda r: r["ts"])

    before, after = len(lines), len(out)
    if after < before:
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
        tmp.replace(path)
    print(f"[log-rotate] {before} -> {after} lines "
          f"(compacted {before - after} older than {keep_days} days)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep-days", type=int, default=60)
    ap.add_argument("--log", type=Path, default=ROOT / "state" / "price_log.jsonl")
    a = ap.parse_args()
    rotate(a.log, a.keep_days)


if __name__ == "__main__":
    main()