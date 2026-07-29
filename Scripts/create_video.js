const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const util = require('util');
const puppeteer = require('puppeteer'); 

const execPromise = util.promisify(exec); // Allows us to use async/await with FFmpeg commands

// --- DYNAMIC DIRECTORY SETUP ---
const baseDir = path.join(__dirname, '..'); 
const designsDir = path.join(baseDir, 'Background-Videos'); 
const videosDir = path.join(baseDir, 'Today-Short'); 
const fontsDir = path.join(baseDir, 'Fonts');

// --- TEXT OVERLAY CONTROLS ---
const yPosTopTitle = 260; 
const fontSize = 90;
const fontColor = '#eeeeee'; 

// --- DATE OVERLAY CONTROLS ---
const yPosBottomDate = 200; 
const dateFontSize = 110;
const dateFontColor = '#eeeeee';

const absoluteFontPath = path.resolve(fontsDir, 'gur_normal.ttf');
const chromeFontPath = 'file://' + absoluteFontPath.replace(/\\/g, '/'); 

async function createVideo() {
    // --- FORCE IST TIMEZONE ---
    const now = new Date();
    const istString = now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' });
    const d = new Date(istString);
    // --------------------------

    const todayDate = d.getDate(); 
    
    const daysOfWeekPunjabi = ['ਐਤਵਾਰ', 'ਸੋਮਵਾਰ', 'ਮੰਗਲਵਾਰ', 'ਬੁੱਧਵਾਰ', 'ਵੀਰਵਾਰ', 'ਸ਼ੁੱਕਰਵਾਰ', 'ਸ਼ਨੀਵਾਰ'];
    const topTitleText = daysOfWeekPunjabi[d.getDay()];
    
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0'); 
    const year = d.getFullYear();
    const formattedDate = `${day}-${month}-${year}`;

    const fgFiles = fs.readdirSync(videosDir).filter(f => f.toLowerCase().endsWith('.mp4'));
    if (fgFiles.length === 0) {
        console.error(`❌ Error: No video found in ${videosDir}`);
        process.exit(1);
    }
    const fgFileName = fgFiles[0];
    const fgFilePath = path.join(videosDir, fgFileName);

    const bgFileName = `${todayDate}.mp4`;
    const bgFilePath = path.join(designsDir, bgFileName);

    if (!fs.existsSync(bgFilePath)) {
        console.error(`❌ Error: Background video for today (${bgFileName}) not found in ${designsDir}`);
        process.exit(1);
    }

    // Temporary path for uncompressed creation
    const rawOutputFileName = `Raw_Final_Hukamnama_${formattedDate}.mp4`;
    const rawOutputFilePath = path.join(baseDir, rawOutputFileName);

    // Final compressed output path
    const outputFileName = `Final_Hukamnama_${formattedDate}.mp4`;
    const outputFilePath = path.join(baseDir, outputFileName);
    
    const tempOverlayPath = path.join(baseDir, 'temp_text_overlay.png'); 
    const tempPingPongBgPath = path.join(baseDir, 'temp_pingpong_bg.mp4'); 

    console.log(`✅ Selected Background: ${bgFileName}`);
    console.log(`✅ Selected Foreground: ${fgFileName}`);
    console.log(`📸 Generating transparent text overlay using Chrome Engine...`);

    const browser = await puppeteer.launch({ 
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--allow-file-access-from-files'] 
    });
    const page = await browser.newPage();
    await page.setViewport({ width: 1080, height: 1600 }); 

    const htmlContent = `
    <html>
        <head>
            <style>
                @font-face {
                    font-family: 'CustomPunjabiFont';
                    src: url('${chromeFontPath}') format('truetype');
                }
                body {
                    margin: 0; padding: 0; background-color: transparent; 
                    width: 1080px; height: 1600px; position: relative;
                    font-family: 'CustomPunjabiFont', 'Noto Sans Gurmukhi', 'Gargi', 'Nirmala UI', sans-serif;
                }
                .title {
                    position: absolute; top: ${yPosTopTitle}px; width: 100%; text-align: center;
                    color: ${fontColor}; font-size: ${fontSize}px;
                    text-shadow: 2px 2px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000, 0px 12px 25px rgba(0,0,0,0.85); 
                }
                .date-text {
                    position: absolute; bottom: ${yPosBottomDate}px; width: 100%; text-align: center;
                    color: ${dateFontColor}; font-size: ${dateFontSize}px;
                    text-shadow: 2px 2px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000, 0px 12px 25px rgba(0,0,0,0.85);
                }
            </style>
        </head>
        <body>
            <div class="title">${topTitleText}</div>
            <div class="date-text">${formattedDate}</div>
        </body>
    </html>
    `;

    await page.setContent(htmlContent);
    await page.screenshot({ path: tempOverlayPath, omitBackground: true });
    await browser.close();
    
    console.log(`✅ Text overlay generated.`);
    console.log(`🔄 Creating seamless ping-pong loop...`);
    
    try {
        await execPromise(`ffmpeg -y -i "${bgFilePath}" -filter_complex "[0:v]reverse[r];[0:v][r]concat=n=2:v=1:a=0[outv]" -map "[outv]" -c:v libx264 -preset ultrafast -crf 18 "${tempPingPongBgPath}"`);
        
        console.log(`⏳ Processing RAW initial video with FFmpeg...`);
        const filterComplex = `[0:v]scale=1080:1600[bg];[1:v]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2[vidWithFg];[2:v]format=rgba,fade=t=in:st=0:d=2:alpha=1[textFaded];[vidWithFg][textFaded]overlay=0:0[outv]`;
        await execPromise(`ffmpeg -y -stream_loop -1 -i "${tempPingPongBgPath}" -i "${fgFilePath}" -loop 1 -i "${tempOverlayPath}" -filter_complex "${filterComplex}" -map "[outv]" -map 1:a? -c:v libx264 -preset fast -crf 23 -c:a aac -b:a 128k -shortest "${rawOutputFilePath}"`);

        console.log(`🗜️ Compressing the main video...`);
        // Compressing the RAW file using a higher CRF (28) to compress it to a smaller size
        await execPromise(`ffmpeg -y -i "${rawOutputFilePath}" -c:v libx264 -preset veryfast -crf 28 -c:a aac -b:a 128k "${outputFilePath}"`);

        console.log(`\n🎉 Success! Compressed Video created successfully: ${outputFilePath}`);

        // Clean up temp files & raw uncompressed video
        if (fs.existsSync(tempOverlayPath)) fs.unlinkSync(tempOverlayPath); 
        if (fs.existsSync(tempPingPongBgPath)) fs.unlinkSync(tempPingPongBgPath);
        if (fs.existsSync(rawOutputFilePath)) fs.unlinkSync(rawOutputFilePath);

        // --- RUN POST-PROCESSING USING COMPRESSED VIDEO ---
        await processPostVideo(outputFilePath, formattedDate);

    } catch (err) {
        console.error(`\n❌ FFmpeg Error:\n${err.message}`);
        if (fs.existsSync(tempOverlayPath)) fs.unlinkSync(tempOverlayPath); 
        if (fs.existsSync(tempPingPongBgPath)) fs.unlinkSync(tempPingPongBgPath);
        if (fs.existsSync(rawOutputFilePath)) fs.unlinkSync(rawOutputFilePath);
        process.exitCode = 1;
    }
}

async function processPostVideo(videoPath, dateStr) {
    console.log(`\n⚙️ Starting post-processing on compressed video (HLS, Branded MP4, Thumbnail)...`);
    
    const hlsDir = path.join(baseDir, 'output_hls');
    const mp4Dir = path.join(baseDir, 'output_mp4');
    if (!fs.existsSync(hlsDir)) fs.mkdirSync(hlsDir, { recursive: true });
    if (!fs.existsSync(mp4Dir)) fs.mkdirSync(mp4Dir, { recursive: true });

    const thumbnailPath = path.join(baseDir, `thumbnail_${dateStr}.jpg`);
    const brandedPath = path.join(mp4Dir, `branded_${dateStr}.mp4`);
    const logoPath = path.join(baseDir, 'logo.png'); // IMPORTANT: Ensure logo.png is in your root folder

    const hlsPrefix = `hls/Hukamnama_${dateStr}`;
    const baseUrl = `https://gurbani-kirtan-darbar.iemgurpreets.workers.dev?filename=${hlsPrefix}`;

    try {
        console.log(`🖼️ Extracting Thumbnail...`);
        await execPromise(`ffmpeg -y -i "${videoPath}" -vframes 1 -q:v 3 "${thumbnailPath}"`);

        console.log(`📺 Converting to HLS...`);
        // Using cross-platform path handling for FFmpeg output string
        const hlsOutput = path.join(hlsDir, 'index.m3u8').replace(/\\/g, '/');
        const hlsSegment = path.join(hlsDir, 'index%03d.ts').replace(/\\/g, '/');
        const hlsCmd = `ffmpeg -y -i "${videoPath}" -vf "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(ih,iw),min(1280,ih),-2)',fps=30" -c:v libx264 -preset veryfast -crf 23 -g 180 -keyint_min 180 -sc_threshold 0 -c:a aac -b:a 128k -hls_time 6 -hls_playlist_type vod -hls_list_size 0 -hls_segment_filename "${hlsSegment}" "${hlsOutput}"`;
        await execPromise(hlsCmd);

        // Modify m3u8 base URL directly using Node instead of bash 'sed'
        let m3u8Content = fs.readFileSync(hlsOutput, 'utf8');
        m3u8Content = m3u8Content.replace(/index/g, `${baseUrl}/index`);
        fs.writeFileSync(hlsOutput, m3u8Content);

        console.log(`🎬 Creating Branded MP4...`);
        if (fs.existsSync(logoPath)) {
            const brandCmd = `ffmpeg -y -i "${videoPath}" -i "${logoPath}" -filter_complex "[0:v]scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(ih,iw),min(1280,ih),-2)'[v]; [1:v]scale=iw*0.17:-1[logo]; [v][logo]overlay=x=W-w-(W*0.03):y=H*0.03" -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -movflags +faststart "${brandedPath}"`;
            await execPromise(brandCmd);

        } else {
            console.log(`⚠️ 'logo.png' not found in root, skipping branded video creation.`);
        }

        console.log(`☁️ Uploading media and updating Firestore...`);
        const cloudflareResult = await execPromise(
            `node Publish-Scripts/publish-cloudflare.js "${dateStr}"`
        );
        process.stdout.write(cloudflareResult.stdout);
        process.stderr.write(cloudflareResult.stderr);

        console.log(`📺 Uploading branded video to YouTube...`);
        const youtubeResult = await execPromise(
            `node Publish-Scripts/publish-youtube.js "${dateStr}"`
        );
        process.stdout.write(youtubeResult.stdout);
        process.stderr.write(youtubeResult.stderr);

    } catch (err) {
        console.error(`❌ Post-processing Error:`, err.message);
        throw err;
    }
}

createVideo();
