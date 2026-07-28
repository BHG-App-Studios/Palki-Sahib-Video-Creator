# GitHub Actions Setup

Open the repository on GitHub, then go to:

`Settings > Secrets and variables > Actions > New repository secret`

Add these secrets:

| Secret | Required | Value |
| --- | --- | --- |
| `GOOGLE_EMAIL` | Yes | Google account email entered into Opera |
| `GOOGLE_PASSWORD` | Yes | Google account password entered into Opera |
| `YT_API_KEY` | Yes | YouTube Data API v3 key |
| `GEMINI_API_KEY` | Yes, unless the paid key is used | Gemini API key |
| `GEMINI_API_KEY_PAID` | Optional | Paid/fallback Gemini API key |
| `CLOUDFLARE_WORKER_API_KEY` | Yes | API key for that screenshot-upload worker |

## Run The Pipeline

1. Open the repository's `Actions` tab.
2. Select `Run Gurbani AI`.
3. Select `Run workflow`.
4. Download `gurbani-ai-final-video` from the completed workflow run.

The workflow uses a Windows runner and uploads the final MP4 for 14 days.
AI response and extracted-frame diagnostics are retained for 7 days.

Before installing the Python dependencies, the workflow restores the bundled
Opera profile, installs Opera, signs into Google, opens the YouTube livestream
for 30 seconds, and closes Opera. The downloader then reads the refreshed
cookies directly with `yt-dlp --cookies-from-browser opera`.

The workflow also installs and starts the matching YouTube PO-token provider
before `main.py` runs. yt-dlp uses this local provider at
`http://127.0.0.1:4416` when YouTube requires a proof-of-origin token.

Before Opera closes, the workflow captures the visible runner screen using the
existing `capture-and-upload.ps1` script. The image is uploaded through the
hardcoded Cloudflare Worker endpoint and retained as a workflow diagnostic
artifact.

Keep this repository private because the bundled Opera profile contains browser
profile databases.
