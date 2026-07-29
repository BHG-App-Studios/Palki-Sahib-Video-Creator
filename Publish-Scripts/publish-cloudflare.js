const fs = require('fs');
const path = require('path');
const admin = require('firebase-admin');

// Date is passed from create_video.js
const dateStr = process.argv[2] || 'unknown_date';

// Environment variables
const hlsSecret = process.env.HLS_SECRET;
const workerUrl = "https://gurbani-kirtan-darbar.iemgurpreets.workers.dev/hls/upload";

const projectId = process.env.FIREBASE_PROJECT_ID;
const clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
let privateKey = process.env.FIREBASE_PRIVATE_KEY;

if (!hlsSecret) {
    console.error("❌ HLS_SECRET environment variable is missing!");
    process.exit(1);
}

// Initialize Firebase with separate variables
try {
    if (!projectId || !clientEmail || !privateKey) {
        throw new Error("Firebase credentials missing in environment variables.");
    }

    // Fix formatting in case GitHub Secrets escapes newlines in the private key
    privateKey = privateKey.replace(/\\n/g, '\n');

    admin.initializeApp({
        credential: admin.credential.cert({
            projectId: projectId,
            clientEmail: clientEmail,
            privateKey: privateKey
        })
    });
} catch (e) {
    console.error("❌ Failed to initialize Firebase:", e.message);
    process.exit(1);
}

const db = admin.firestore();
const currentTimestamp = Date.now(); // Integer timestamp

// Keys mapped identical to bash script logic
const hlsPrefix = `hls/Hukamnama_${dateStr}`;
const baseKey = `Videos/Hukamnama_${currentTimestamp}_${dateStr}`;

async function uploadFileToCloudflare(filePath, uploadKey) {
    console.log(`☁️ Uploading: ${filePath} -> ${uploadKey}`);
    const fileData = fs.readFileSync(filePath);

    const response = await fetch(`${workerUrl}?key=${uploadKey}`, {
        method: 'POST',
        headers: { 'X-HLS-Secret': hlsSecret },
        body: fileData
    });

    if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Upload failed for ${uploadKey}. Status: ${response.status} - ${errText}`);
    }
}

async function publish() {
    try {
        // 1. Upload Thumbnail
        const thumbnailPath = `thumbnail_${dateStr}.jpg`;
        const thumbnailKey = `Videos-Thumbnail/hukamnama_${currentTimestamp}.jpg`;
        if (fs.existsSync(thumbnailPath)) {
            await uploadFileToCloudflare(thumbnailPath, thumbnailKey);
        }

        // 2. Upload Final Original MP4
        const finalVideoPath = `Final_Hukamnama_${dateStr}.mp4`;
        if (fs.existsSync(finalVideoPath)) {
            await uploadFileToCloudflare(finalVideoPath, `${baseKey}.mp4`);
        }

        // 3. Upload Branded MP4
        const brandedPath = path.join('output_mp4', `branded_${dateStr}.mp4`);
        if (fs.existsSync(brandedPath)) {
            await uploadFileToCloudflare(brandedPath, `${hlsPrefix}/branded/branded.mp4`);
        }

        // 4. Upload all HLS files
        const hlsDir = 'output_hls';
        if (fs.existsSync(hlsDir)) {
            const hlsFiles = fs.readdirSync(hlsDir);
            for (const file of hlsFiles) {
                await uploadFileToCloudflare(path.join(hlsDir, file), `${hlsPrefix}/${file}`);
            }
        }

        // 5. Update Firebase
        console.log("🔥 Updating Firestore database...");

        // Base domain used for viewing the videos
        const viewerBaseUrl = "https://gurbani-kirtan-darbar.iemgurpreets.workers.dev?filename=";

        // Generate a document reference FIRST so we can use its ID inside the document
        const postRef = db.collection('pending_posts').doc();

        const dateParts = dateStr.split('-');
        const prettyDate = `${dateParts[0]}/${dateParts[1]}/${dateParts[2]}`;
        const finalCaption = `✨ ${prettyDate} Amrit Vela Darshan | Sri Harmandir Sahib Ji 🌼`;

        // Exact schema matching the requested structure
        const postData = {
            brandedVideo: `${viewerBaseUrl}${hlsPrefix}/branded/branded.mp4`,
            caption: finalCaption,
            hlsUrl: `${viewerBaseUrl}${hlsPrefix}/index.m3u8`,
            imageUrl: `${viewerBaseUrl}${baseKey}.mp4`,
            likeCount: 0,
            mediaType: "Video",
            postId: postRef.id,
            postedBy: "XqgtuozXRDVD7PnW1q7G4BJLwTP2",
            publicHlsId: `${hlsPrefix}`,
            publicId: `${baseKey}.mp4`,
            publicThumbnailId: thumbnailKey,
            shareCount: 0,
            thumbnailUrl: `${viewerBaseUrl}${thumbnailKey}`,
            timestamp: currentTimestamp,
            userName: "hukamnama",
            userProfileImage: "https://gurbani-kirtan-darbar.iemgurpreets.workers.dev?filename=Profile-Images/profile_1NHCXkThytQH6YoCmTtBu9hvO3d2_1776082119293.jpg",
            videoResolution: "1080p"
        };

        await postRef.set(postData);

        console.log(`✅ Successfully added to Firestore! Document ID: ${postRef.id}`);
        process.exit(0);

    } catch (error) {
        console.error("❌ Publishing Error:", error);
        process.exit(1);
    }
}

publish();
