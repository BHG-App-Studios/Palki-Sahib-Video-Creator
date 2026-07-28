import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from urllib.parse import parse_qs, urlparse

import requests


# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parents[1]
API_KEY = os.getenv("YT_API_KEY")
CHANNEL_ID = "UCc8bMFsrYs-aHr_ls7CThPg"
DOWNLOAD_DIR = BASE_DIR / "Original-Video"
DOWNLOADER = "yt-dlp"
DOWNLOAD_SECONDS = 100 * 60
FRAGMENT_SECONDS = 5
FRAGMENT_WORKERS = 8
LIVE_EDGE_RETRY_SECONDS = 2
DURATION_PROBE_MEDIA_FRAGMENTS = 64
FINAL_DURATION_BUFFER_SECONDS = 5
FORMAT_SELECTOR = (
    "bestvideo[vcodec^=avc1][height<=720]"
    "/bestvideo[height<=720]"
)


def get_live_video_url():
    if not API_KEY:
        raise RuntimeError(
            "YT_API_KEY environment variable not found. "
            "Configure it before running the pipeline."
        )

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "channelId": CHANNEL_ID,
            "eventType": "live",
            "type": "video",
            "key": API_KEY,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"YouTube API error: {data['error']['message']}")

    for item in data.get("items", []):
        title = item["snippet"]["title"]
        video_id = item["id"]["videoId"]
        print(f"Found live video: {title} (ID: {video_id})")

        if any(
            phrase.lower() in title.lower()
            for phrase in ("Official SGPC LIVE", "Gurbani Kirtan")
        ):
            return f"https://www.youtube.com/watch?v={video_id}"

    return None


def get_video_stream_url(video_url):
    command = [
        DOWNLOADER,
        "--ignore-config",
        "--verbose",
        "--cookies-from-browser",
        "opera",
        "--js-runtimes",
        "node",
        "--extractor-args",
        "youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416",
        "--extractor-args",
        "youtube:player_client=mweb",
        "--live-from-start",
        "-f",
        FORMAT_SELECTOR,
        "--get-url",
        video_url,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"yt-dlp could not resolve the live stream:\n{details}")

    urls = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith(("http://", "https://"))
    ]

    if len(urls) != 1:
        raise RuntimeError(
            "Expected one video URL from yt-dlp, "
            f"but received {len(urls)} URL(s)."
        )

    return urls[0]


def download_fragment(base_url, sequence, live_edge_reached):
    separator = "&" if "?" in base_url else "?"
    fragment_url = f"{base_url}{separator}sq={sequence}"

    while True:
        try:
            response = requests.get(
                fragment_url,
                timeout=(15, 90),
            )
        except requests.Timeout:
            response = None

        if (
            response is None
            or response.status_code in (204, 404)
            or not response.content
        ):
            if not live_edge_reached.is_set():
                live_edge_reached.set()
                print(
                    "\nCaught up to the live stream. Waiting for new video "
                    f"until {DOWNLOAD_SECONDS // 60} minutes are available..."
                )
            time.sleep(LIVE_EDGE_RETRY_SECONDS)
            continue

        response.raise_for_status()

        returned_sequence = response.headers.get("X-Sequence-Num")
        if returned_sequence is not None and returned_sequence != str(sequence):
            raise RuntimeError(
                f"Requested fragment {sequence}, but YouTube returned "
                f"fragment {returned_sequence}."
            )

        return sequence, response.content


def probe_media_duration(media_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"FFprobe could not detect fragment duration:\n{details}")

    try:
        return float(result.stdout.strip())
    except ValueError as error:
        raise RuntimeError(
            f"FFprobe returned an invalid duration: {result.stdout.strip()}"
        ) from error


def download_fragments(base_url, output_path, label):
    # sq=0 contains initialization data. A few extra media fragments ensure
    # FFmpeg has enough content available for an exact final trim.
    media_fragment_count = math.ceil(DOWNLOAD_SECONDS / FRAGMENT_SECONDS) + 3
    live_edge_reached = Event()
    next_sequence = 0
    duration_detected = False

    print(f"Downloading {label} from the beginning...")
    while True:
        while next_sequence <= media_fragment_count:
            batch_end = min(
                next_sequence + FRAGMENT_WORKERS,
                media_fragment_count + 1,
            )
            batch = list(range(next_sequence, batch_end))

            with output_path.open(
                "wb" if next_sequence == 0 else "ab"
            ) as output_file:
                with ThreadPoolExecutor(max_workers=FRAGMENT_WORKERS) as executor:
                    futures = [
                        executor.submit(
                            download_fragment,
                            base_url,
                            sequence,
                            live_edge_reached,
                        )
                        for sequence in batch
                    ]
                    fragments = {
                        sequence: content
                        for sequence, content in (
                            future.result() for future in as_completed(futures)
                        )
                    }

                for sequence in batch:
                    output_file.write(fragments[sequence])

            next_sequence = batch[-1] + 1
            downloaded_media_fragments = next_sequence - 1

            if (
                not duration_detected
                and downloaded_media_fragments
                >= DURATION_PROBE_MEDIA_FRAGMENTS
            ):
                downloaded_duration = probe_media_duration(output_path)
                measured_fragment_seconds = (
                    downloaded_duration / downloaded_media_fragments
                )
                if measured_fragment_seconds <= 0:
                    raise RuntimeError(
                        "Detected fragment duration was not positive."
                    )

                media_fragment_count = max(
                    batch[-1],
                    math.ceil(
                        (DOWNLOAD_SECONDS + FINAL_DURATION_BUFFER_SECONDS)
                        / measured_fragment_seconds
                    )
                    + 3,
                )
                duration_detected = True
                print(
                    f"Detected {measured_fragment_seconds:.3f}-second "
                    f"fragments; {media_fragment_count} fragments are needed."
                )

            completed = min(batch[-1], media_fragment_count)
            print(
                f"\rDownloading {label}: "
                f"{completed}/{media_fragment_count} fragments",
                end="",
                flush=True,
            )

        downloaded_duration = probe_media_duration(output_path)
        required_duration = DOWNLOAD_SECONDS + FINAL_DURATION_BUFFER_SECONDS
        if downloaded_duration >= required_duration:
            break

        downloaded_media_fragments = next_sequence - 1
        measured_fragment_seconds = (
            downloaded_duration / downloaded_media_fragments
        )
        missing_duration = required_duration - downloaded_duration
        additional_fragments = max(
            FRAGMENT_WORKERS,
            math.ceil(missing_duration / measured_fragment_seconds) + 3,
        )
        media_fragment_count += additional_fragments
        print()
        print(
            f"Downloaded media is {downloaded_duration / 60:.2f} minutes; "
            f"fetching {additional_fragments} more fragments..."
        )
    print()


def video_id_from_url(video_url):
    return parse_qs(urlparse(video_url).query).get("v", ["live_stream"])[0]


def download_video(video_url):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    video_id = video_id_from_url(video_url)
    duration_minutes = DOWNLOAD_SECONDS // 60
    output_path = DOWNLOAD_DIR / f"{video_id}_first_{duration_minutes}_minutes.mkv"
    temporary_output = (
        DOWNLOAD_DIR / f"{video_id}_first_{duration_minutes}_minutes.tmp.mkv"
    )
    video_part = DOWNLOAD_DIR / f".{video_id}.video.part"

    print(
        f"\nFast-downloading the FIRST {DOWNLOAD_SECONDS // 60} minutes "
        f"of the stream: {video_url}"
    )

    try:
        video_stream_url = get_video_stream_url(video_url)
        download_fragments(video_stream_url, video_part, "video")

        print(f"Trimming video to exactly {duration_minutes} minutes...")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_part),
                "-t",
                str(DOWNLOAD_SECONDS),
                "-map",
                "0:v:0",
                "-an",
                "-c",
                "copy",
                str(temporary_output),
            ],
            check=True,
        )
        os.replace(temporary_output, output_path)
    finally:
        video_part.unlink(missing_ok=True)
        temporary_output.unlink(missing_ok=True)

    print(f"\nDownload completed successfully: {output_path}")
    return output_path


def main():
    print("Checking for live stream...")
    video_url = get_live_video_url()

    if not video_url:
        print("Target live stream is not live yet. Try again later.")
        return 1

    download_video(video_url)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (requests.RequestException, subprocess.CalledProcessError, RuntimeError) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
