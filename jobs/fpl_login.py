"""One-time FPL login via the OAuth2 device flow.

FPL retired the old email/password login endpoint. A one-time browser
approval here yields a long-lived refresh token; the automated submit job
then exchanges it for access tokens with no further interaction.

Usage (once per account):

    python jobs/fpl_login.py            # first account
    python jobs/fpl_login.py --account 2

Open the printed URL, approve the code shown, and the script prints the
refresh token plus the exact `gh secret set` command for the matching
secret. Tokens are printed to stdout only and are never written to disk.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import api                                         # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=int, choices=(1, 2), default=1,
                    help="which squad's account this is (1 or 2), for the "
                         "suggested secret name")
    a = ap.parse_args()

    secret = "FPL_REFRESH_TOKEN" if a.account == 1 else "FPL_REFRESH_TOKEN_2"
    print(f"Starting FPL login for account {a.account} "
          f"(secret: {secret})")

    d = api.device_authorization()
    uri, user_code = d["verification_uri"], d["user_code"]
    print(f"\n  1. Open this URL in a browser and sign in to FPL:")
    print(f"     {uri}")
    print(f"  2. Enter this code when asked:  {user_code}\n")
    try:
        import webbrowser
        webbrowser.open(uri)
    except Exception:                                        # noqa: BLE001
        pass

    tokens = api.poll_device_token(d["device_code"],
                                   interval=float(d.get("interval", 5)))
    rt = tokens.get("refresh_token")
    if not rt:
        print("login succeeded but no refresh token came back "
              "(offline_access was not granted) — nothing to automate with")
        return
    print(f"Login OK. Now set the secret (this is the only output with the "
          f"token — copy it now):\n")
    print(f"  gh secret set {secret} --body \"{rt}\"\n")
    print("Then trigger a dry run to verify:  gh workflow run submit")


if __name__ == "__main__":
    main()