"""FPL login split in two steps, for shells without an interactive stdin.

jobs/fpl_login.py needs a live input() prompt, which a `!` command in this
session cannot provide (it runs with stdin closed - EOFError at the first
prompt). This tool splits the same flow:

    python tools/login_handoff.py start --account 1
        prints the authorize URL and keeps the PKCE verifier in a temp file

    python tools/login_handoff.py finish --account 1 --set-secret "<URL>"
        exchanges the pasted redirect URL for tokens, verifies the squad,
        stores the refresh token with `gh secret set`, removes the temp file

The verifier never reaches stdout - the temp file lives in the system temp
directory and is deleted once used.
"""
from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jobs"))

from fpl_login import code_from_pasted, pkce                    # noqa: E402
from fplbot import api                                          # noqa: E402


def handoff_path(account: int) -> Path:
    return Path(tempfile.gettempdir()) / f"fpl_login_{account}.json"


def start(account: int) -> None:
    secret = "FPL_REFRESH_TOKEN" if account == 1 else "FPL_REFRESH_TOKEN_2"
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    handoff_path(account).write_text(json.dumps(
        {"verifier": verifier, "state": state}), encoding="utf-8")
    print(f"Starting FPL login for account {account} (secret: {secret})")
    print(f"\nOpen this URL, sign in to the account for THIS squad:\n")
    print(api.authorize_url(state, challenge))
    print(f"\nAfter sign-in you land on fantasy.premierleague.com - the "
          f"address bar now contains ?code=... Copy that FULL URL and paste "
          f"it back in the chat.")


def finish(account: int, redirect: str, set_secret: bool) -> None:
    secret = "FPL_REFRESH_TOKEN" if account == 1 else "FPL_REFRESH_TOKEN_2"
    saved = json.loads(handoff_path(account).read_text(encoding="utf-8"))
    code = code_from_pasted(redirect, saved["state"])
    print("Exchanging the code for tokens ...")
    tokens = api.exchange_code(code, saved["verifier"])

    session = api.api_session(tokens["access_token"])
    entries = api.me(session)
    print(f"Verified: this account manages entry "
          f"{', '.join(str(e) for e in sorted(entries))}")

    rt = tokens.get("refresh_token")
    if not rt:
        print("login succeeded but no refresh token came back "
              "(offline_access was not granted) - nothing to automate with")
        return
    if set_secret:
        subprocess.run(["gh", "secret", "set", secret, "--body", rt],
                       check=True)
        print(f"OK - refresh token stored as repo secret {secret}.")
    else:
        print(f"Login OK - store it with: gh secret set {secret} "
              f"--body \"{rt}\"")
    handoff_path(account).unlink(missing_ok=True)
    print("Then trigger a dry run to verify:  gh workflow run submit")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("start", "finish"))
    ap.add_argument("--account", type=int, choices=(1, 2), default=1)
    ap.add_argument("redirect", nargs="?",
                    help="the pasted redirect URL (finish only)")
    ap.add_argument("--set-secret", action="store_true")
    a = ap.parse_args()
    if a.step == "start":
        start(a.account)
    else:
        if not a.redirect:
            ap.error("finish needs the pasted redirect URL")
        finish(a.account, a.redirect, a.set_secret)


if __name__ == "__main__":
    main()