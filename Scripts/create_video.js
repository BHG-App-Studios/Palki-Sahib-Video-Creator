const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const util = require('util');
const puppeteer = require('puppeteer');

const execPromise = util.promisify(exec);
const completionWorkerUrl = 'https://palki-sahib-video-creator-trigger.iemgurpreets.workers.dev';
const baseDir = path.join(__dirname, '..');
const designsDir = path.join(baseDir, 'Background-Videos');
const videosDir = path.join(baseDir, 'Today-Short');
const fontsDir = path.join(baseDir, 'Fonts');
const WIDTH = 1080;
const HEIGHT = 1600;
const VIDEO_DURATION = Number(process.env.VIDEO_DURATION_SECONDS || 59);

function getEventTimeIst() {
    const responsePath = path.join(baseDir, 'AI-Response', 'response.json');
    if (!fs.existsSync(responsePath)) {
        throw new Error(`Event-time data is missing: ${responsePath}`);
    }

    let response;
    try {
        response = JSON.parse(fs.readFileSync(responsePath, 'utf8'));
    } catch (error) {
        throw new Error(`Could not read event-time data: ${error.message}`);
    }
    if (typeof response.event_time_ist !== 'string' || !response.event_time_ist) {
        throw new Error('Calculated IST event time is missing from the Gemini response.');
    }
    return response.event_time_ist;
}

function getIndiaDateDetails(now = new Date()) {
    // Always extract calendar fields directly in India Standard Time (IST).
    // Do not parse a locale-formatted date string: parsing uses the runner's
    // timezone and can move the date/weekday around midnight on GitHub Actions.
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).formatToParts(now);
    const values = Object.fromEntries(
        parts
            .filter(({ type }) => type !== 'literal')
            .map(({ type, value }) => [type, value])
    );
    const isoDate = `${values.year}-${values.month}-${values.day}`;

    return {
        dayOfMonth: values.day,
        isoDate,
        formattedDate: `${values.day}-${values.month}-${values.year}`,
        englishDate: new Intl.DateTimeFormat('en-GB', {
            timeZone: 'Asia/Kolkata', day: 'numeric', month: 'long', year: 'numeric'
        }).format(now),
        weekday: new Intl.DateTimeFormat('en-GB', {
            timeZone: 'Asia/Kolkata', weekday: 'long'
        }).format(now),
        liveClock: new Intl.DateTimeFormat('en-IN', {
            timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit', hour12: true
        }).format(now).toUpperCase(),
    };
}

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[char]);
}

async function renderOverlay(filePath, body) {
    const fontPath = `file://${path.resolve(fontsDir, 'gur_normal.ttf').replace(/\\/g, '/')}`;
    const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--disable-setuid-sandbox', '--allow-file-access-from-files'] });
    try {
        const page = await browser.newPage();
        await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });
        await page.setContent(`<!doctype html><html><head><style>
            @font-face { font-family: Gurbani; src: url('${fontPath}') format('truetype'); }
            * { box-sizing: border-box; }
            html, body { margin: 0; width: ${WIDTH}px; height: ${HEIGHT}px; overflow: hidden; background: transparent; }
            body { color: #fff8df; font-family: Arial, 'Nirmala UI', sans-serif; }
            .gurbani { font-family: Gurbani, 'Noto Sans Gurmukhi', 'Nirmala UI', sans-serif; }
            ${body.css || ''}
        </style></head><body>${body.html}</body></html>`);
        await page.screenshot({ path: filePath, omitBackground: true });
    } finally {
        await browser.close();
    }
}

async function createOverlays(tempPaths, details) {
    const { punjabiTitle, englishTitle, dateLine, weekday, liveClock } = details;
    await renderOverlay(tempPaths.title, {
        css: `.title { position:absolute; top:124px; width:100%; text-align:center; text-shadow:0 0 10px rgba(255,211,112,.9), 0 5px 22px rgba(0,0,0,.92); }
              .punjabi { font-size:69px; line-height:1.25; letter-spacing:1px; } .english { margin-top:18px; font-weight:600; font-size:47px; letter-spacing:2px; color:#f6d37e; }
              .spark { color:#f7c64e; font-size:37px; padding:0 16px; vertical-align:middle; }`,
        html: `<div class="title"><div class="gurbani punjabi"><span class="spark">✦</span>${escapeHtml(punjabiTitle)}<span class="spark">✦</span></div><div class="english">${escapeHtml(englishTitle)}</div></div>`
    });
    await renderOverlay(tempPaths.info, {
        css: `.location { position:absolute; top:1254px; width:100%; text-align:center; font-size:29px; letter-spacing:1.4px; text-shadow:0 3px 12px #000; }
              .date { position:absolute; top:1304px; width:100%; text-align:center; font-size:46px; font-weight:600; color:#f7d77f; text-shadow:0 3px 12px #000; }
              .weekday { display:block; margin-top:12px; font-size:33px; color:#fff4d5; font-weight:400; letter-spacing:3px; }
              .live { position:absolute; top:320px; left:405px; width:270px; padding:0; font-size:23px; line-height:1.35; text-align:center; text-shadow:0 2px 8px #000; }
              .live strong { display:block; margin-top:0; color:#f4cf6b; font-size:32px; letter-spacing:1px; }`,
        html: `<div class="location">📍 Sachkhand Sri Harmandir Sahib Ji • Amritsar</div><div class="date">🗓️ ${escapeHtml(dateLine)}<span class="weekday">${escapeHtml(weekday)}</span></div><div class="live"><strong>🕒 ${escapeHtml(liveClock)}</strong></div>`
    });
    await renderOverlay(tempPaths.ikOnkar, {
        css: `.ik { position:absolute; top:618px; width:100%; text-align:center; color:#f5ce69; opacity:.09; font-size:285px; text-shadow:0 0 36px #f4ba36; }`,
        html: '<div class="gurbani ik">ੴ</div>'
    });
}

async function createVideo() {
    const { dayOfMonth, isoDate, formattedDate, englishDate, weekday } = getIndiaDateDetails();
    const liveClock = getEventTimeIst();
    const foregroundPath = path.join(videosDir, `today_short_${isoDate}.mp4`);
    const backgroundPath = path.join(designsDir, `${Number(dayOfMonth)}.mp4`);

    for (const [kind, candidate] of [['foreground', foregroundPath], ['plain background', backgroundPath]]) {
        if (!fs.existsSync(candidate)) throw new Error(`No ${kind} video found: ${candidate}`);
    }
    const outputPath = path.join(baseDir, `Final_Hukamnama_${formattedDate}.mp4`);
    const tempPaths = {
        title: path.join(baseDir, 'temp_title_overlay.png'), info: path.join(baseDir, 'temp_info_overlay.png'),
        ikOnkar: path.join(baseDir, 'temp_ik_onkar_overlay.png'),
        pingPong: path.join(baseDir, 'temp_pingpong_bg.mp4')
    };
    const cleanup = () => Object.values(tempPaths).forEach(file => { if (fs.existsSync(file)) fs.unlinkSync(file); });

    try {
        console.log(`Selected date background: ${path.basename(backgroundPath)}`);
        await createOverlays(tempPaths, {
            punjabiTitle: 'ਅੱਜ ਦੇ ਅੰਮ੍ਰਿਤ ਵੇਲੇ ਦੇ ਦਰਸ਼ਨ', englishTitle: "Today's Amrit Vela Darshan 🙏",
            dateLine: englishDate, weekday, liveClock
        });

        // Ping-pong looping avoids a noticeable jump when a short daily background repeats.
        await execPromise(`ffmpeg -y -i "${backgroundPath}" -filter_complex "[0:v]reverse[r];[0:v][r]concat=n=2:v=1:a=0,format=yuv420p[outv]" -map "[outv]" -an -c:v libx264 -preset ultrafast -crf 18 "${tempPaths.pingPong}"`);

        const filter = [
            `[0:v]scale=w='iw*(1.02+0.02*t/${VIDEO_DURATION})':h='ih*(1.02+0.02*t/${VIDEO_DURATION})':eval=frame,crop=${WIDTH}:${HEIGHT}:(in_w-out_w)/2:(in_h-out_h)/2,setsar=1[bg]`,
            `[1:v]scale=1050:786[fg]`,
            `[bg][4:v]overlay=x=0:y='10*sin(t/6)':eval=frame[withIk]`,
            `[withIk][fg]overlay=15:407[framed]`,
            `[framed]drawbox=x=0:y=392:w=1080:h=817:color=0xA87519@0.65:t=3,drawbox=x=6:y=398:w=1068:h=805:color=0xF6D36E@0.9:t=2,drawbox=x='6+mod(t*42\\,978)':y=396:w=90:h=5:color=white@0.9:t=fill,drawbox=x='984-mod(t*42\\,978)':y=1200:w=90:h=5:color=white@0.8:t=fill,drawbox=x=4:y='402+mod(t*35\\,690)':w=5:h=76:color=white@0.75:t=fill,drawbox=x=1073:y='1125-mod(t*35\\,690)':w=5:h=76:color=white@0.75:t=fill[bordered]`,
            `[2:v]split=2[thumbnailTitle][animatedTitle]`,
            `[animatedTitle]scale=w='iw*(1.015-0.015*min(t/1.4\\,1))':h='ih*(1.015-0.015*min(t/1.4\\,1))':eval=frame,fade=t=in:st=0:d=1.4:alpha=1[title]`,
            `[bordered][thumbnailTitle]overlay=0:0:enable='eq(n\\,0)'[thumbnailReady]`,
            `[thumbnailReady][title]overlay=x=(W-w)/2:y=(H-h)/2:eval=frame[titled]`,
            `color=c=white@0.10:s=29x92:r=30,format=rgba[shineGlow]`,
            `[titled][shineGlow]overlay=x='56+t*752':y=122:eval=frame:enable='lt(t\\,1.25)'[glowed]`,
            `color=c=white@0.42:s=8x92:r=30,format=rgba[shineCore]`,
            `[glowed][shineCore]overlay=x='67+t*752':y=122:eval=frame:enable='lt(t\\,1.25)'[shined]`,
            `[shined][3:v]overlay=0:0[info]`,
            `[1:a]showwaves=s=210x24:mode=cline:colors=0xEAC65E@0.95,format=rgba[wave]`,
            `[info][wave]overlay=435:1440[outv]`
        ].join(';');
        const command = `ffmpeg -y -stream_loop -1 -i "${tempPaths.pingPong}" -i "${foregroundPath}" -loop 1 -i "${tempPaths.title}" -loop 1 -i "${tempPaths.info}" -loop 1 -i "${tempPaths.ikOnkar}" -filter_complex "${filter}" -map "[outv]" -map 1:a? -t ${VIDEO_DURATION} -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart "${outputPath}"`;
        await execPromise(command, { maxBuffer: 1024 * 1024 * 10 });
        console.log(`Success: ${outputPath}`);
        await processPostVideo(outputPath, formattedDate);
    } finally {
        cleanup();
    }
}

async function processPostVideo(videoPath, dateStr) {
    console.log('Starting production post-processing (HLS, branded MP4, thumbnail)...');

    const hlsDir = path.join(baseDir, 'output_hls');
    const mp4Dir = path.join(baseDir, 'output_mp4');
    if (!fs.existsSync(hlsDir)) fs.mkdirSync(hlsDir, { recursive: true });
    if (!fs.existsSync(mp4Dir)) fs.mkdirSync(mp4Dir, { recursive: true });

    const thumbnailPath = path.join(baseDir, `thumbnail_${dateStr}.jpg`);
    const brandedPath = path.join(mp4Dir, `branded_${dateStr}.mp4`);
    const logoPath = path.join(baseDir, 'logo.png');
    const hlsPrefix = `hls/Hukamnama_${dateStr}`;
    const baseUrl = `https://gurbani-kirtan-darbar.iemgurpreets.workers.dev?filename=${hlsPrefix}`;

    console.log('Extracting thumbnail...');
    await execPromise(`ffmpeg -y -i "${videoPath}" -vframes 1 -q:v 3 "${thumbnailPath}"`);

    console.log('Converting to HLS...');
    const hlsOutput = path.join(hlsDir, 'index.m3u8').replace(/\\/g, '/');
    const hlsSegment = path.join(hlsDir, 'index%03d.ts').replace(/\\/g, '/');
    await execPromise(`ffmpeg -y -i "${videoPath}" -vf "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(ih,iw),min(1280,ih),-2)',fps=30" -c:v libx264 -preset veryfast -crf 23 -g 180 -keyint_min 180 -sc_threshold 0 -c:a aac -b:a 128k -hls_time 6 -hls_playlist_type vod -hls_list_size 0 -hls_segment_filename "${hlsSegment}" "${hlsOutput}"`);
    fs.writeFileSync(hlsOutput, fs.readFileSync(hlsOutput, 'utf8').replace(/index/g, `${baseUrl}/index`));

    if (fs.existsSync(logoPath)) {
        console.log('Creating branded MP4...');
        await execPromise(`ffmpeg -y -i "${videoPath}" -i "${logoPath}" -filter_complex "[0:v]scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(ih,iw),min(1280,ih),-2)'[v]; [1:v]scale=iw*0.17:-1[logo]; [v][logo]overlay=x=W-w-(W*0.03):y=H*0.03" -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -movflags +faststart "${brandedPath}"`);
    } else {
        console.log("logo.png not found; branded MP4 creation skipped.");
    }

    if (!process.env.RUN_COMPLETION_SECRET) throw new Error('RUN_COMPLETION_SECRET is missing.');
    const headers = { Authorization: `Bearer ${process.env.RUN_COMPLETION_SECRET}` };
    const statusResponse = await fetch(`${completionWorkerUrl}/checkRunStatus`, { method: 'POST', headers });
    if (!statusResponse.ok) throw new Error(`Run status check failed (${statusResponse.status}): ${await statusResponse.text()}`);
    if ((await statusResponse.json()).completed === true) {
        console.log("Today's video is already complete. Skipping publish scripts.");
        return;
    }

    console.log('Uploading media to Cloudflare...');
    const cloudflareResult = await execPromise(`node Publish-Scripts/publish-cloudflare.js "${dateStr}"`);
    process.stdout.write(cloudflareResult.stdout);
    process.stderr.write(cloudflareResult.stderr);

    console.log('Uploading branded video to YouTube...');
    const youtubeResult = await execPromise(`node Publish-Scripts/publish-youtube.js "${dateStr}"`);
    process.stdout.write(youtubeResult.stdout);
    process.stderr.write(youtubeResult.stderr);

    const completionResponse = await fetch(`${completionWorkerUrl}/complete`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ date: dateStr.split('-').reverse().join('-'), status: 'success' }),
    });
    if (!completionResponse.ok) throw new Error(`Completion acknowledgment failed (${completionResponse.status}): ${await completionResponse.text()}`);
    console.log('Recorded successful completion for today in Cloudflare KV.');
}

createVideo().catch(error => { console.error(`Video creation failed: ${error.message}`); process.exitCode = 1; });
