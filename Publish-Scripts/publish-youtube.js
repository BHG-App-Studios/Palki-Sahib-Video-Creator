const fs = require('fs');
const path = require('path');
const { google } = require('googleapis');
const OAuth2 = google.auth.OAuth2;

// Date is passed from create_video.js
const dateStr = process.argv[2] || 'unknown_date';

// Environment variables for YouTube API
const clientId = process.env.YOUTUBE_CLIENT_ID;
const clientSecret = process.env.YOUTUBE_CLIENT_SECRET;
const refreshToken = process.env.YOUTUBE_REFRESH_TOKEN;

// Validation of environment variables
if (!clientId || !clientSecret || !refreshToken) {
    console.error("❌ YouTube API credentials missing in environment variables. Set them in your environment (e.g., GitHub Secrets).");
    process.exit(1);
}

// Set up the OAuth2 client
const oauth2Client = new OAuth2(
    clientId,
    clientSecret,
    "https://developers.google.com/oauthplayground" // Standard redirect URL for OAuthPlayground
);
oauth2Client.setCredentials({ refresh_token: refreshToken });

const youtube = google.youtube({
    version: 'v3',
    auth: oauth2Client,
});

// Path to the video to be uploaded
const videoPath = path.join('output_mp4', `branded_${dateStr}.mp4`);

async function uploadVideo() {
    // Check if the branded video actually exists before uploading
    if (!fs.existsSync(videoPath)) {
        console.error(`❌ Branded video not found at ${videoPath}, skipping YouTube upload. Did branding fail?`);
        process.exit(1);
    }

    console.log(`☁️ Starting YouTube upload: ${videoPath}`);

    // Create a user-friendly title and description from the date
    const dateParts = dateStr.split('-');
    const prettyDate = `${dateParts[0]}/${dateParts[1]}/${dateParts[2]}`;
    const longDate = new Intl.DateTimeFormat('en-GB', {
        day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata'
    }).format(new Date(`${dateParts[2]}-${dateParts[1]}-${dateParts[0]}T00:00:00Z`));
    const videoTitle = `✨ ${longDate} Amrit Vela Darshan | Sri Harmandir Sahib Ji | Golden Temple Amritsar 🌼`;
    const videoDescription = `✨ Today's Amrit Vela Palki Sahib Darshan from Sachkhand Sri Harmandir Sahib Ji (Golden Temple), Amritsar.

📅 Date: ${longDate}

Watch today's divine Amrit Vela Darshan and Palki Sahib Darshan from Sachkhand Sri Harmandir Sahib Ji (Golden Temple), Amritsar, Punjab. Experience the peaceful Gurbani atmosphere and begin your day with Waheguru Ji's blessings.

📍 Location:
Sachkhand Sri Harmandir Sahib Ji (Dhan Guru Ram Das Sahib Ji Darbar Sahib)
Amritsar, Punjab, India

🙏 Daily on this channel:
• Amrit Vela Darshan
• Palki Sahib Darshan
• Daily Hukamnama Sahib
• Gurbani Kirtan
• Sri Harmandir Sahib Darshan
• Sikh Spiritual Videos

🙏 Waheguru Ji Ka Khalsa
🙏 Waheguru Ji Ki Fateh

#AmritVela
#PalkiSahib
#SriHarmandirSahib
#GoldenTemple
#Gurbani
#Hukamnama
#Waheguru
#Kirtan
#Amritsar
#Sikh
#Shorts`;

    try {
        const res = await youtube.videos.insert({
            part: 'snippet,status',
            requestBody: {
                snippet: {
                    title: videoTitle,
                    description: videoDescription,
                    tags: ['Amrit Vela Darshan', 'Amrit Vela', 'Amrit Vela Kirtan', 'Morning Darshan', 'Daily Darshan', 'Palki Sahib', 'Palki Sahib Darshan', 'Palki Sahib Ceremony', 'Daily Hukamnama', 'Hukamnama Sahib', 'Today Hukamnama', 'Hukamnama Sahib Today', 'Sri Harmandir Sahib', 'Harmandir Sahib', 'Darbar Sahib', 'Golden Temple', 'Golden Temple Amritsar', 'Golden Temple Live', 'Gurbani', 'Gurbani Kirtan', 'Guru Ram Das Ji', 'Live Kirtan', 'Sikh Temple', 'Amritsar', 'Darshan Today', 'ਪਾਲਕੀ ਸਾਹਿਬ', 'ਹੁਕਮਨਾਮਾ', 'ਦਰਬਾਰ ਸਾਹਿਬ', 'ਹਰਿਮੰਦਰ ਸਾਹਿਬ'],
                    categoryId: '22', // Category: People & Blogs
                },
                status: {
                    privacyStatus: 'private', // Change to 'unlisted' for initial testing if needed
                    selfDeclaredMadeForKids: false,
                },
            },
            media: {
                body: fs.createReadStream(videoPath),
            },
        });

        console.log(`✅ Success! Video uploaded to YouTube: https://www.youtube.com/watch?v=${res.data.id}`);
        process.exit(0);
    } catch (error) {
        // Detailed error log for debugging
        if (error.response && error.response.data) {
            console.error('❌ YouTube Upload API Error:', error.response.data.error.message);
        } else {
            console.error('❌ YouTube Upload Error:', error);
        }
        process.exit(1);
    }
}

// Start the upload process
uploadVideo();
