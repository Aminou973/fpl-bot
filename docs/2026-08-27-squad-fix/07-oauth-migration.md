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
- Token endpoint supports the **device_code** grant — built for CLI tools

## New arm procedure (one-time per account, ~1 minute each)

```bash
python jobs/fpl_login.py            # first account  → secret FPL_REFRESH_TOKEN
python jobs/fpl_login.py --account 2  # second account → secret FPL_REFRESH_TOKEN_2
```

Each run prints a URL and a code: open the URL, sign in to FPL, approve the
code. The script then prints the **refresh token** and the exact
`gh secret set` command. Paste the token into the secret. No email/password
secrets are used anywhere anymore (the old `FPL_EMAIL`/`FPL_PASSWORD` secrets
can be deleted).

Then verify headless auth works:

```bash
gh workflow run submit   # dispatch = dry run, reads squads, no submission
```

## How it runs afterwards

- Each run: refresh token → access token (`POST /as/token`,
  `grant_type=refresh_token`) → `Authorization: Bearer` on
  `/api/me/`, `/api/my-team/{id}/` (read) and (only when applying)
  the picks write.
- **Rotation caveat**: if FPL rotates refresh tokens, the printed note
  appears. The stored secret normally keeps working; if a later run ever
  fails with `refresh failed`, re-run `jobs/fpl_login.py` and update the
  secret.
- Revocation: approving a device flow signs you in like any other session;
  you can end it from your FPL account's active sessions at any time.

## Files

- `fplbot/api.py` — `device_authorization`, `poll_device_token`,
  `refresh_tokens`, `api_session`, `me` (old `login()` removed)
- `jobs/fpl_login.py` — **new** one-time device-flow helper
- `jobs/submit_transfers.py` — token-based authentication
- `.github/workflows/submit.yml` — `FPL_REFRESH_TOKEN(_2)` env