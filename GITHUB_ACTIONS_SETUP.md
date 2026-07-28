# GitHub Actions Setup

Open the repository on GitHub, then go to:

`Settings > Secrets and variables > Actions > New repository secret`

Add these secrets:

| Secret | Required | Value |
| --- | --- | --- |
| `GOOGLE_EMAIL` | Yes | Google account email entered into Opera |
| `GOOGLE_PASSWORD` | Yes | Google account password entered into Opera |
| `YOUTUBE_API_KEY` | Yes | YouTube Data API v3 key |
| `GEMINI_API_KEY` | Yes, unless the paid key is used | Gemini API key |
| `GEMINI_API_KEY_PAID` | Optional | Paid/fallback Gemini API key |

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

Keep this repository private because the bundled Opera profile contains browser
profile databases.
