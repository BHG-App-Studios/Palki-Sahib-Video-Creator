import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


# ---------------- CONFIG ----------------

RESPONSE_FILE = Path(
    r"C:\Users\Gurpreet\Downloads\Gurbani-AI\AI-Response\response.json"
)
VIDEO_FILE = Path(
    r"C:\Users\Gurpreet\Downloads\Gurbani-AI\30min-Clip\30min_clip.mp4"
)
SHABADS_FOLDER = Path(
    r"C:\Users\Gurpreet\Downloads\Gurbani-AI\Random-Shabads"
)
OUTPUT_FOLDER = Path(
    r"C:\Users\Gurpreet\Downloads\Gurbani-AI\Today-Short"
)

CLIP_DURATION_SECONDS = 59
BOTTOM_CROP_PIXELS = 133
OUTPUT_WIDTH = 960
OUTPUT_HEIGHT = 720

# ----------------------------------------


def read_start_time():
    if not RESPONSE_FILE.is_file():
        raise RuntimeError(f"AI response file not found: {RESPONSE_FILE}")

    response = json.loads(RESPONSE_FILE.read_text(encoding="utf-8"))
    if response.get("match_found") is not True:
        raise RuntimeError("AI response does not contain a reliable match.")

    frame_name = response.get("frame")
    if not isinstance(frame_name, str):
        raise RuntimeError("AI response does not contain a valid frame name.")

    match = re.fullmatch(
        r"(?P<minutes>\d+)_(?P<seconds>\d{2})_(?P<milliseconds>\d{2})\.png",
        frame_name,
    )
    if not match:
        raise RuntimeError(
            f"Invalid frame timestamp in AI response: {frame_name}"
        )

    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    milliseconds = int(match.group("milliseconds"))
    total_seconds = minutes * 60 + seconds + milliseconds / 100

    return total_seconds, frame_name


def find_today_shabad():
    day_number = datetime.now().day
    shabad_file = SHABADS_FOLDER / f"{day_number}.mp3"

    if not shabad_file.is_file():
        raise RuntimeError(
            f"Today's shabad was not found: {shabad_file}"
        )

    return shabad_file


def create_short(start_seconds, frame_name, shabad_file):
    if not VIDEO_FILE.is_file():
        raise RuntimeError(f"Source video not found: {VIDEO_FILE}")

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    date_text = datetime.now().strftime("%Y-%m-%d")
    output_file = OUTPUT_FOLDER / f"today_short_{date_text}.mp4"

    print(f"AI start frame: {frame_name}")
    print(f"Start time: {start_seconds:.2f} seconds")
    print(f"Today's shabad: {shabad_file.name}")
    print("Creating 59-second 960x720 short...")

    video_filter = (
        f"crop=iw:ih-{BOTTOM_CROP_PIXELS}:0:0,"
        "crop=trunc(ih*4/3/2)*2:ih,"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(start_seconds),
        "-i",
        str(VIDEO_FILE),
        "-stream_loop",
        "-1",
        "-i",
        str(shabad_file),
        "-t",
        str(CLIP_DURATION_SECONDS),
        "-filter:v",
        video_filter,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_file),
    ]

    subprocess.run(command, check=True)
    print(f"\nFinal short created successfully: {output_file}")
    return output_file


def main():
    start_seconds, frame_name = read_start_time()
    shabad_file = find_today_shabad()
    create_short(start_seconds, frame_name, shabad_file)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
