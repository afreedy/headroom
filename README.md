# Headroom

Usage limits, reset countdowns and banked reset expiries for multiple Codex accounts.

[Live dashboard](https://headroom-usage.vercel.app) (current Vercel deployment requires Vercel sign-in). Account credentials stay on your Mac.

## Setup on macOS

Install Codex and Python 3.10+, then install the connector as a login service:

```sh
python3 connector/install.py --origin https://headroom-usage.vercel.app
```

The service starts at login and restarts after crashes. It uses the bundled Codex binary or `codex` on PATH. Launch the dashboard paired once:

```sh
python3 connector/server.py --origin https://headroom-usage.vercel.app --open
```

If the installed service is already running, use the local pairing key in `~/Library/Application Support/Headroom/pairing-key` in the dashboard's Connector dialog instead of starting a second server. Never share this key.

Choose **Connect account** and sign into each account separately. Every account gets its own local Codex profile; switching the Codex desktop login does not change those connections. Legacy desktop-linked accounts show **Reconnect account** until signed in independently. Account names are browser-local.

## Automatic refresh and warmup

The connector refreshes all saved accounts at least once per minute while running. Each account's warmup follows the latest returned five-hour reset timestamp, with a 30-second grace period. Earlier deadlines shorten the worker's wait; late starts and wake-from-sleep checks do not wait for a daily wall-clock time. Closing the browser or Codex chat does not stop the login service. No Codex automation is used.

After a five-hour reset, the connector sends a minimal `hi` through that account's subscription and verifies completion. It skips active windows, exhausted weekly quotas, unknown quotas, failed refreshes and mismatched identities. Intent is saved before sending; failed or uncertain attempts are not resent for the same window. The dashboard shows warmup status and last completion. Exact quota-window anchoring is not documented by OpenAI; a completed hi does not guarantee a particular future reset timestamp. A warmup consumes a small amount of subscription usage. Banked resets are displayed only and are never redeemed; API-key billing is not used.

Old usage percentages and banked-reset counts are hidden when disconnected, stale or errored. Only fresh returned values are shown. Authentication can expire and may require reconnecting the affected account. The Mac must be awake, logged in and online; missed checks resume automatically when available. Windows startup packaging is not implemented.

To stop automatic operation:

```sh
launchctl bootout gui/$(id -u)/com.afreedy.headroom
# Remove ~/Library/LaunchAgents/com.afreedy.headroom.plist to stop future login starts.
```

For development without installing a service:

```sh
python3 -m http.server 4174 --bind 127.0.0.1 --directory public
python3 connector/server.py --origin http://127.0.0.1:4174 --open
```

## Privacy and checks

Credentials, account snapshots and the attempt ledger live under `~/Library/Application Support/Headroom/`, outside this repository. The connector binds to loopback and checks Host, allowed origin and pairing key. No credentials or personal records are hosted on Vercel. Do not publish the private data directory.

```sh
node --test tests/usage.test.mjs
python3 -m unittest discover -s tests -p 'test_*.py'
```

Design inspired by the supplied AI in Design Report reference; captured source assets are excluded. Uses system fonts and an original SVG mark.

## Warmup evidence

Expand **Warmup runs → View evidence** on an account. Headroom reads the local runtime-generated receipt history automatically; open histories refresh every five seconds. Each recorded attempt shows model, reasoning effort, exact prompt and captured answer, thread/turn IDs, timestamps, runtime completion status, token counts when returned, errors and before/after quota snapshots. Download the full JSON receipt, including the allowlisted completion events, from the same view.

Receipts are stored privately in `~/Library/Application Support/Headroom/warmup-runs/`. They are local evidence reported by the runtime, not a provider-signed audit record. Model routing events are retained if returned. Answer text is captured from completed agent-message events; authentication payloads and reasoning traces are not retained. Older ledger-only runs are explicitly labeled **Legacy · limited evidence** and never given fabricated prompts, replies or IDs. No old transcript can be reconstructed from a completion timestamp.

The run history records send attempts. The latest automatic check, reason for skipping and next scheduled check remain on the account card; routine minute-by-minute skipped checks do not create inference-run receipts. The one-time verification runs are labeled separately and do not bypass the automatic scheduler's duplicate guard.
