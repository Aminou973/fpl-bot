# Step 7 — FPL login migration: OAuth2 device flow + refresh tokens

Date: 2026-08-27 (evening)

## Why the email/password login died

The first Actions dry run failed with a DNS error:
**`users.premierleague.com` no longer exists**. FPL retired the old
form-login endpoint and moved to OAuth2/OIDC (verified from the official
site's own JS bundle and its discovery document):

- Authorization server: `https://account.premierleague.com/as`
- Client id: `bfcbaf69-aade-4c1b-8f00-c1cb8a193030` (the official web app's)
- Flow: Authorization Code + **PKCE**, Bearer tokens on API calls
  (`Authorization: Bearer …` and `X-API-Authorization: Bearer …`)
- Scopes include **`offline_access`** → refresh tokens
- The client allows only the **Authorization Code + PKCE** grant — the
  device-code grant is rejected (`unauthorized_client: missing DEVICE_CODE`),
  and the only registered redirect is the web app's own origin
  (`https://fantasy.premierleague.com/`), so a local loopback redirect is
  rejected too.

## New arm procedure (one-time per account, ~1 minute each)

```bash
python jobs/fpl_login.py              # first account  → secret FPL_REFRESH_TOKEN
python jobs/fpl_login.py --account 2  # second account → secret FPL_REFRESH_TOKEN_2
```

Or everything in one go (also triggers the verification dry run):

```bat
arm_fpl_login.bat
```

Each run opens the FPL sign-in page in your browser; sign in to that squad's
account and you land on `fantasy.premierleague.com/?code=...` — copy the full
address-bar URL and paste it back. The script exchanges the code (PKCE) for
tokens and stores the **refresh token** with `gh secret set`. No email/password
secrets are used anywhere anymore (the old `FPL_EMAIL`/`FPL_PASSWORD` secrets
can be deleted).

Then verify headless auth works:

```bash
gh workflow run submit   # dispatch = dry run, reads squads, no submission
```

## How it runs afterwards

- Each run: refresh token → access token (`POST /as/token`,
  `grant_type=refresh_token`) → `Authorization: Bearer` on
  `/api/me/` (shape: `player.entry` — the app calls `my-team/{entry}/`
  with that same id), `/api/my-team/{id}/` (read) and (only when
  applying) the picks write.
- **Rotation is real and must be handled**: FPL issues a NEW refresh token
  with every refresh-token grant and invalidates the old one immediately.
  The submit job therefore writes the rotated token back to its secret
  after every run. For that it needs one more secret:
  **`FPL_PAT`** — a fine-grained PAT limited to this repo with the
  *Secrets: read and write* permission
  (github.com/settings/personal-access-tokens/new → Only select
  repositories → Aminou973/fpl-bot → Repository permissions →
  Secrets: Read and write). Without it, each run burns its refresh token
  and the accounts need re-arming.
- If a run ever logs `refresh FAILED` for an account, re-run
  `jobs/fpl_login.py` (or the bat) for that account.
- Revocation: the browser login is a normal sign-in session; you can end
  it from your FPL account's active sessions, and the PAT can be revoked
  from your GitHub settings at any time.

## Files

- `fplbot/api.py` — `authorize_url`, `exchange_code` (PKCE),
  `refresh_tokens`, `api_session`, `me` (old `login()` removed)
- `jobs/fpl_login.py` — **new** one-time browser-login helper
- `arm_fpl_login.bat` — both logins + secret storage + dry run, one click
- `jobs/submit_transfers.py` — token-based authentication
- `.github/workflows/submit.yml` — `FPL_REFRESH_TOKEN(_2)` env