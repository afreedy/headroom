# Headroom

A dashboard for multiple Codex accounts: remaining usage, reset countdowns and banked reset expiry dates.

**Live website:** [headroom-usage.vercel.app](https://headroom-usage.vercel.app). The current Vercel deployment requires Vercel sign-in. Live account readings require the local connector on the same Mac; no credentials are hosted on Vercel.

## Run locally

Requirements: macOS, Python 3.10+ and a signed-in Codex desktop app or CLI. The connector uses the desktop bundled binary when available, or `codex` on PATH. Set `CODEX_BIN` to an absolute binary path if needed.

```sh
python3 -m http.server 4174 --bind 127.0.0.1 --directory public
# In a second terminal:
python3 connector/server.py --origin http://127.0.0.1:4174 --open
```

For the hosted dashboard, run `python3 connector/server.py --origin https://headroom-usage.vercel.app --open`, or open `Start Headroom.command`. Keep the connector running and allow the browser's local-device permission. Connect each account through the UI for independent saved logins. Desktop login changes do not replace independently connected accounts.

## Privacy and limits

OAuth credentials and account snapshots are stored under `~/Library/Application Support/Headroom/` with restricted file permissions. The server binds to loopback only, validates the Host, exact allowed origin and pairing key, and returns quota metadata to the paired browser. Browser-local account labels and readings are not synced across browsers. Do not publish the private data directory, pairing key, browser storage or auth files. This source export includes none of them.

The five-hour and weekly labels come from returned window durations. Unknown values remain unknown. A reset passing does not fabricate refreshed capacity. Banked resets are displayed only; the dashboard does not redeem them. Windows packaging and clean-machine setup are unverified.

## Optional warmup helper

`connector/warmup.py` is an opt-in local helper that sends one tiny `hi` after a reported five-hour reset, checks fixed account identities, skips exhausted weekly quotas and persists attempts before sending. It uses ephemeral read-only Codex turns and no API-key billing. Exact window anchoring is undocumented. Running the helper consumes a small amount of subscription usage.

The personal scheduler and account configuration are deliberately excluded. To configure your own helper, populate `warmup-targets.json` in the private Headroom directory with objects containing your account `id` from the connector snapshot and the absolute `home` of its dedicated Codex profile. A `null` home follows the desktop login and stops working for that account if you switch logins. Review the helper before enabling an OS scheduler. Do not copy another person's credentials.

## Check

```sh
node --test tests/usage.test.mjs
python3 -m unittest discover -s tests -p 'test_*.py'
```

Desktop/mobile rendering and two-account use were checked on the developer's Mac. This is a source release, not a signed installer.

Design is inspired by the supplied AI in Design Report reference; original typography assets and captures are not included. Uses system fonts and an original SVG mark.
