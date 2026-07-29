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
Used by the AI script to inspect extracted video frames and detect the moment the Palki Sahib procession begins.
- **GEMINI_API_KEY** [Your free Gemini API Key]
- **GEMINI_API_KEY_PAID**: [Your paid Gemini API Key for fallback]
