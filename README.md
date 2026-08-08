# Gurbani AI Automation

## Environment Variables

When setting up this project (e.g., in GitHub Actions or locally), you will need to configure the following environment secrets for all the scripts to function properly:

### Firebase Configuration
Used for uploading and publishing the final videos to Cloudflare/Firebase.
- **FIREBASE_CLIENT_EMAIL**: `jskson9209@gmail.com`
- **FIREBASE_PROJECT_ID**: [Your Firebase Project ID]
- **FIREBASE_PRIVATE_KEY**: [Your Firebase Private Key]
- **HLS_SECRET**: [Your Cloudflare Worker HLS Secret]

### YouTube Publishing
Used for automating the video upload to your YouTube channel.
- **YOUTUBE_CLIENT_ID**: [Your YouTube OAuth Client ID]
- **YOUTUBE_CLIENT_SECRET**: [Your YouTube OAuth Client Secret]
- **YOUTUBE_REFRESH_TOKEN**: [Your YouTube OAuth Refresh Token]

### YouTube Downloading
Used by yt-dlp to download the official SGPC Harmandir Sahib livestream.
- **YT_API_KEY**: [Your YouTube Data API Key]

### Gemini AI Vision
Used by the AI script to inspect extracted video frames and detect the moment the Palki Sahib procession begins. Provide up to four **free** Gemini API keys (one per free Google Cloud project). The script tries every model on key 1 first, and only moves on to the next key once all models are exhausted on the current one (e.g. rate limited). At least `GEMINI_API_KEY_1` is required; the rest are optional but recommended for more free daily headroom.
- **GEMINI_API_KEY_1**: [Free Gemini API key from project 1 — required]
- **GEMINI_API_KEY_2**: [Free Gemini API key from project 2 — optional]
- **GEMINI_API_KEY_3**: [Free Gemini API key from project 3 — optional]
- **GEMINI_API_KEY_4**: [Free Gemini API key from project 4 — optional]
