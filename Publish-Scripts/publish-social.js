// ==========================================================
// Publishes the BRANDED Amrit Vela Darshan video to Facebook Page + Instagram
// Reels. Meta fetches the video from a PUBLIC url, so this must run AFTER
// publish-cloudflare.js has uploaded branded.mp4 to Cloudflare R2.
//
// Best-effort by design: this script may exit non-zero, but the caller in
// create_video.js swallows the failure so the pipeline is never retried
// (a retry would duplicate the Cloudflare/YouTube/Firestore posts).
//
// Args:  process.argv[2] = dateStr (DD-MM-YYYY)   [required]
//        process.argv[3] = brandedVideoUrl        [optional override]
// Env:   FACEBOOK_ACCESS_TOKEN, FACEBOOK_PAGE_ID, INSTAGRAM_PROFILE_ID
// ==========================================================

const dateStr = process.argv[2] || 'unknown_date';
const brandedUrlArg = process.argv[3];

const TOKEN = process.env.FACEBOOK_ACCESS_TOKEN;
const PAGE_ID = process.env.FACEBOOK_PAGE_ID;
const IG_ID = process.env.INSTAGRAM_PROFILE_ID;

const GRAPH = 'https://graph.facebook.com/v21.0';

// Same public branded url that publish-cloudflare.js stores as `brandedVideo`.
const hlsPrefix = `hls/Hukamnama_${dateStr}`;
const viewerBaseUrl = 'https://gurbani-kirtan-darbar.iemgurpreets.workers.dev?filename=';
const brandedVideoUrl = brandedUrlArg || `${viewerBaseUrl}${hlsPrefix}/branded/branded.mp4`;

if (!TOKEN || !PAGE_ID || !IG_ID) {
    console.error('❌ Missing Meta credentials (FACEBOOK_ACCESS_TOKEN / FACEBOOK_PAGE_ID / INSTAGRAM_PROFILE_ID). Skipping social publish.');
    process.exit(1);
}

// ---------------- Titles / Captions (production) ----------------
// dateStr is DD-MM-YYYY -> "7 August 2026" (worded month, no leading zero),
// matching the format used by publish-cloudflare.js and publish-youtube.js.
const dp = dateStr.split('-');
const longDate = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Kolkata'
}).format(new Date(`${dp[2]}-${dp[1]}-${dp[0]}T00:00:00Z`));

// Shared title line (also used as the Facebook video title).
const socialTitle = `✨ ${longDate} Amrit Vela Darshan | Sri Harmandir Sahib Ji | Golden Temple Amritsar`;

// Facebook Page post description.
const facebookDescription = `✨ Today's Amrit Vela Darshan 🙏

📅 ${longDate}

Watch today's divine Amrit Vela Darshan & Palki Sahib Darshan from Sachkhand Sri Harmandir Sahib Ji (Golden Temple), Amritsar. May Guru Sahib Ji bless you and your family with peace, wisdom, and happiness.

🙏 Begin your day with the peaceful Gurbani atmosphere and Waheguru Ji's blessings.

📍 Sachkhand Sri Harmandir Sahib Ji (Darbar Sahib)
Amritsar, Punjab, India

💛 If this Darshan inspires you, please Like, Share, and Follow our page so more Sangat can receive Guru Sahib Ji's blessings every day.

🙏 Waheguru Ji Ka Khalsa
🙏 Waheguru Ji Ki Fateh

#AmritVela #PalkiSahib #SriHarmandirSahib #GoldenTemple #DarbarSahib #Gurbani #Waheguru #Amritsar #Sikh #Sikhism`;

// Instagram Reel caption.
const instagramCaption = `✨ Today's Amrit Vela Darshan 🙏

📅 ${longDate}

Watch today's divine Amrit Vela Darshan & Palki Sahib Darshan from Sachkhand Sri Harmandir Sahib Ji (Golden Temple), Amritsar.

May Guru Sahib Ji bless everyone with peace, wisdom, and Chardi Kala. 🙏

💛 Save this post for today's Darshan.
🤍 Share it with your family and friends.
📲 Follow for Daily Amrit Vela Darshan, Palki Sahib Darshan, Hukamnama Sahib, and Gurbani Kirtan.

🙏 Waheguru Ji Ka Khalsa
🙏 Waheguru Ji Ki Fateh

#AmritVela #PalkiSahib #TodayDarshan #SriHarmandirSahib #GoldenTemple #DarbarSahib #Gurbani #Waheguru #Amritsar #Sikh #Sikhism #GuruGranthSahib #Punjab #Khalsa #Spirituality #Faith #Blessings #GurbaniKirtan #Darshan #Reels`;
// ---------------- Graph API helpers ----------------
async function graphPost(pathPart, params) {
    const body = new URLSearchParams({ ...params, access_token: TOKEN });
    const res = await fetch(`${GRAPH}/${pathPart}`, { method: 'POST', body });
    const json = await res.json();
    if (!res.ok || json.error) {
        throw new Error(JSON.stringify(json.error || json));
    }
    return json;
}

async function graphGet(pathPart, params = {}) {
    const qs = new URLSearchParams({ ...params, access_token: TOKEN });
    const res = await fetch(`${GRAPH}/${pathPart}?${qs}`);
    const json = await res.json();
    if (!res.ok || json.error) {
        throw new Error(JSON.stringify(json.error || json));
    }
    return json;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------- Facebook Page video ----------------
async function publishFacebook() {
    console.log('1️⃣  Uploading to Facebook Page...');
    const res = await graphPost(`${PAGE_ID}/videos`, {
        file_url: brandedVideoUrl,
        title: socialTitle,
        description: facebookDescription,
    });
    console.log(`   ✅ Facebook video created. id: ${res.id}`);
}

// ---------------- Instagram Reel ----------------
async function publishInstagram() {
    console.log('2️⃣  Creating Instagram Reel container...');
    const container = await graphPost(`${IG_ID}/media`, {
        media_type: 'REELS',
        video_url: brandedVideoUrl,
        caption: instagramCaption,
        share_to_feed: 'true',
    });
    const containerId = container.id;
    console.log(`   Container created: ${containerId}. Waiting for Meta to process the video...`);

    // Poll the container until Meta finishes processing (up to ~4 min).
    const maxTries = 24;
    for (let i = 1; i <= maxTries; i++) {
        await sleep(10000);
        const status = await graphGet(containerId, { fields: 'status_code,status' });
        console.log(`   [${i}/${maxTries}] status_code: ${status.status_code}`);
        if (status.status_code === 'FINISHED') break;
        if (status.status_code === 'ERROR' || status.status_code === 'EXPIRED') {
            throw new Error(`Instagram container failed: ${JSON.stringify(status)}`);
        }
        if (i === maxTries) {
            throw new Error('Instagram container did not finish processing in time.');
        }
    }

    console.log('   Publishing Instagram container...');
    const published = await graphPost(`${IG_ID}/media_publish`, {
        creation_id: containerId,
    });
    console.log(`   ✅ Instagram Reel published. id: ${published.id}`);
}

// ---------------- Main ----------------
(async () => {
    console.log(`📣 Social publish for ${dateStr}`);
    console.log(`   Branded video URL: ${brandedVideoUrl}\n`);

    let failed = false;

    try {
        await publishFacebook();
    } catch (e) {
        failed = true;
        console.error('   ❌ Facebook publish failed:', e.message);
    }

    try {
        await publishInstagram();
    } catch (e) {
        failed = true;
        console.error('   ❌ Instagram publish failed:', e.message);
    }

    if (failed) {
        console.error('\n⚠️ Social publish finished with errors.');
        process.exit(1);
    }
    console.log('\n🎉 Social publish complete (Facebook + Instagram).');
    process.exit(0);
})();
