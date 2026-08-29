"""Chip-routing rehearsal for the submit job, fully stubbed offline.

No login, no network, no writes to FPL: api.refresh_tokens / me / my_team /
transfers / picks / entry_history are replaced, and the run is judged on which
endpoint each chip travelled on. A wildcard must activate WITH its transfer
batch on /transfers/; a triple captain must ride ON the /my-team/ picks write
and never touch transfers.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "jobs"))

os.environ.setdefault("FPL_REFRESH_TOKEN", "tok1")
os.environ.setdefault("FPL_REFRESH_TOKEN_2", "tok2")

from fplbot import api, notify                      # noqa: E402
import jobs.submit_transfers as st                  # noqa: E402

plan = json.loads((ROOT / "state" / "last_plan.json").read_text(encoding="utf-8"))
e41 = plan["teams"]["Minoux_41"]
e69 = plan["teams"]["Minoux_69"]
calls = []


def refresh2(rt):
    return {"access_token": "s" + rt, "refresh_token": rt}


def me(_s):
    return {int(e41["entry"]): 441, int(e69["entry"]): 669}


def my_team(_s, team_id):
    src = e41 if team_id == 441 else e69
    if team_id == 441:                       # _41 still on the pre-wildcard squad
        return {"picks": [{"element": p, "position": i + 1,
                           "is_captain": False, "is_vice_captain": False,
                           "selling_price": 100}
                          for i, p in enumerate(src["squad"])]}
    # _69: same squad but the captain not yet set, so the run exercises the
    # triple-captain riding on the picks write
    return {"picks": [{"element": p["element"], "position": p["position"],
                       "is_captain": False, "is_vice_captain": p["is_vice"],
                       "selling_price": 100}
                      for p in src["picks_payload"]]}


def transfers(_s, entry_id, _gw, tr, chip=None):
    calls.append(("transfers", entry_id, len(tr), chip))
    return {}


def picks(_s, team_id, pl, chip=None):
    calls.append(("picks", team_id, len(pl), chip))
    return {}


def history(_eid):
    return {"chips": []}


def send(text, **_kw):
    print("[notify]", " / ".join(text.splitlines()[:3]))
    return True


api.refresh_tokens = refresh2
api.me = me
api.my_team = my_team
api.make_transfers = transfers
api.submit_picks = picks
api.entry_history = history
st.notify.send = send
notify.send = send

sys.argv = ["rehearse", "--force", "--untested", "--apply"]
st.main()

print("CALLS:", calls)
tc = [c for c in calls if c[0] == "transfers"]
pk = [c for c in calls if c[0] == "picks"]
assert any(c[3] == "wildcard" for c in tc), "wildcard must ride on transfers"
assert any(c[3] == "3xc" for c in pk), "3xc must ride on the picks write"
assert all(c[3] != "wildcard" for c in pk), "picks write never carries wildcard"
assert all(c[3] != "3xc" for c in tc), "transfers call never carries 3xc"
print("chip routing OK")