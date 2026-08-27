"""One-time FPL login (Authorization Code + PKCE).

FPL retired the old email/password login endpoint. One interactive browser
login here yields a long-lived refresh token; the automated submit job then
exchanges it for access tokens with no further interaction.

Usage (once per account):

    python jobs/fpl_login.py              # first account
    python jobs/fpl_login.py --account 2  # second account

The script opens the FPL sign-in page in your browser; after signing in you
are redirected to fantasy.premierleague.com with ?code=... in the address
bar — copy that full URL and paste it back here. The refresh token is then
stored with `gh secret set` (with --set-secret) or printed for manual use.
Tokens are never written to disk.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import secrets
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fplbot import api                                         # noqa: E402


def pkce():
    """(code_verifier, code_challenge) pair for the S256 PKCE method."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def code_from_pasted(url_or_code: str, expected_state: str) -> str:
    """Extract ?code= (and check state) from the pasted redirect URL."""
    if "://" not in url_or_code:               # user pasted the code itself
        return url_or_code.strip().strip("'\"")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url_or_code.strip()).query)
    if q.get("state", [""])[0] != expected_state:
        raise RuntimeError("the pasted URL's state does not match this "
                           "session — start the login again")
    if "error" in q:
        raise RuntimeError(f"login failed in the browser: "
                           f"{q.get('error_description', q['error'])[0]}")
    if "code" not in q:
        raise RuntimeError("no ?code= found in the pasted URL — copy the "
                           "full address-bar URL right after sign-in "
                           "(it should start with https://fantasy.)")
    return q["code"][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", type=int, choices=(1, 2), default=1,
                    help="which squad's account this is (1 or 2), for the "
                         "secret name")
    ap.add_argument("--set-secret", action="store_true",
                    help="store the token directly with `gh secret set` "
                         "instead of printing the command")
    a = ap.parse_args()

    secret = "FPL_REFRESH_TOKEN" if a.account == 1 else "FPL_REFRESH_TOKEN_2"
    print(f"Starting FPL login for account {a.account} (secret: {secret})")

    verifier, challenge = pkce()
    state = secrets.token_urlsafe(16)
    url = api.authorize_url(state, challenge)

    print(f"""
  1. A browser window is opening on the FPL sign-in page.
     (If it does not open, paste this URL manually:)
     {url}
  2. Sign in to the FPL account for THIS squad.
  3. After sign-in you land on fantasy.premierleague.com — the address bar
     now contains ?code=... Copy that FULL URL and paste it below.
""")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:                                        # noqa: BLE001
        pass

    pasted = input("Paste the redirected URL here> ").strip()
    code = code_from_pasted(pasted, state)
    print("Exchanging the code for tokens ...")
    tokens = api.exchange_code(code, verifier)

    # verify the token actually reaches this account's squad before storing
    session = api.api_session(tokens["access_token"])
    entries = api.me(session)
    print(f"Verified: this account manages entry "
          f"{', '.join(str(e) for e in sorted(entries))}")

    rt = tokens.get("refresh_token")
    if not rt:
        print("login succeeded but no refresh token came back "
              "(offline_access was not granted) — nothing to automate with")
        return

    if a.set_secret:
        try:
            subprocess.run(["gh", "secret", "set", secret, "--body", rt],
                           check=True)
            print(f"OK — refresh token stored as repo secret {secret}.")
        except FileNotFoundError:
            print("gh CLI not found — store it manually with:")
            print(f"  gh secret set {secret} --body \"{rt}\"")
        except subprocess.CalledProcessError as e:
            print(f"gh secret set failed (exit {e.returncode}) — run manually:")
            print(f"  gh secret set {secret} --body \"{rt}\"")
    else:
        print(f"Login OK. Store the token (copy it now — this is the only "
              f"output with the token):\n")
        print(f"  gh secret set {secret} --body \"{rt}\"\n")
    print("Then trigger a dry run to verify:  gh workflow run submit")


if __name__ == "__main__":
    main()