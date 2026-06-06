# X Copytrade Monitor

This project watches a hand-picked list of X profiles, reads new posts, asks an LLM whether the post contains a real buy or sell view, checks whether other watched accounts discussed the same ticker or sector, and emits a report.

## What it does

- Polls the latest posts from configured X profiles.
- Uses OpenAI to classify whether a post contains a tradeable view.
- Extracts structured data such as action, ticker, company, sector, confidence, and rationale.
- Looks for corroborating or conflicting opinions from the rest of the watchlist.
- Writes JSON reports locally and prints a compact summary to the terminal.

## Important limitation

X does not provide simple unauthenticated notifications for arbitrary profiles. This implementation uses Playwright against a logged-in browser session and polls profile timelines. Operationally, that gives you "near-notification" behavior, but it is still scraping and may break if X changes its UI.

## Setup

1. Create a virtual environment and install the package:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
playwright install chromium
```

2. Copy the example files and fill them in:

```powershell
Copy-Item .env.example .env
Copy-Item profiles.example.json profiles.json
```

3. Set `OPENAI_API_KEY` in `.env`.
   Optionally change `OPENAI_MODEL`; the default is `gpt-4.1-mini`.
   Set `X_BROWSER_CHANNEL=msedge` or `X_BROWSER_CHANNEL=chrome` if X is picky about the browser used for login.
   If X is slow to load, increase `X_NAVIGATION_TIMEOUT_MS` from the default `45000` or `X_POST_LOAD_WAIT_MS` from the default `2500`.

4. Run a one-time interactive login so Playwright can reuse the browser state:

```powershell
copytrade-monitor login
```

This creates `playwright_state.json` locally. You can reuse that file on a server.

5. Start the monitor:

```powershell
copytrade-monitor run
```

## Profiles file

`profiles.json` is an array:

```json
[
  {
    "handle": "some_trader",
    "display_name": "Some Trader"
  }
]
```

## Output

- Reports are stored in `data/reports/`.
- Raw seen posts and extracted signals are cached in `data/cache.json`.
- Every analyzed post is appended to `data/analyses.jsonl`, including posts that failed AI analysis.
- The monitor prints a trade signal summary when it writes a report. Set `X_DEBUG=true` to print browser timeline diagnostics.

## Configuration

Runtime settings are read from environment variables first, then from `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Required for `copytrade-monitor run`. |
| `OPENAI_MODEL` | `gpt-4.1-mini` | OpenAI model used for post analysis. |
| `POLL_INTERVAL_SECONDS` | `45` | Delay between polling cycles. |
| `LOOKBACK_HOURS` | `72` | Window used to find same-ticker or same-sector opinions. |
| `HEADLESS` | `true` | Whether the monitor browser runs headless. Login always opens a visible browser. |
| `X_BROWSER_CHANNEL` | `msedge` | Browser channel for Playwright, such as `msedge` or `chrome`. |
| `X_NAVIGATION_TIMEOUT_MS` | `45000` | Maximum navigation wait for X pages. |
| `X_POST_LOAD_WAIT_MS` | `2500` | Extra wait after opening a profile before reading posts. |
| `X_DEBUG` | `false` | Print browser timeline diagnostics while scraping X. |
| `X_STORAGE_STATE_PATH` | `playwright_state.json` | Saved X login session path. |
| `PROFILES_PATH` | `profiles.json` | Watchlist file path. |
| `DATA_DIR` | `data` | Directory for cache, analysis log, and reports. |

## Deploy on a VPS

This is the recommended way to run the monitor 24/7.

1. Create an Ubuntu VPS.
2. Copy this repository to `/opt/copyTrading`.
3. Run the bootstrap script as root:

```bash
bash deploy/bootstrap_ubuntu.sh
```

4. Create the runtime files:

```bash
cp .env.example .env
cp profiles.example.json profiles.json
```

5. Edit `.env` and set `OPENAI_API_KEY`.

6. Create the X browser session on your own machine if you have not already:

```powershell
copytrade-monitor login
```

7. Copy `playwright_state.json` to the server into `/opt/copyTrading/playwright_state.json`.

8. Start and enable the service:

```bash
sudo systemctl enable --now copytrade-monitor
```

9. Check logs:

```bash
sudo journalctl -u copytrade-monitor -f
```

The included systemd unit is at `deploy/copytrade-monitor.service`.

## Design notes

- "Same stock" means exact ticker match.
- "Similar stock" means same extracted sector label.
- The monitor only reports posts where the AI says the message contains a directional trading view.
- Confidence is the model's self-reported confidence, not a backtested metric.
