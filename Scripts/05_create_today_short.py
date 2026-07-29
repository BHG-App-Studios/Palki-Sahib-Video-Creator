import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ---------------- CONFIG ----------------

BASE_DIR = Path(__file__).resolve().parents[1]
START_RESPONSE_FILE = BASE_DIR / "AI-Response" / "start_frame.json"
END_RESPONSE_FILE = BASE_DIR / "AI-Response" / "end_frame.json"
VIDEO_FILE = BASE_DIR / "30min-Clip" / "30min_clip.mp4"
SHABADS_FOLDER = BASE_DIR / "Random-Shabads"
OUTPUT_FOLDER = BASE_DIR / "Today-Short"
APP_TIMEZONE = timezone(timedelta(hours=5, minutes=30))

CLIP_DURATION_SECONDS = 59
BOTTOM_CROP_PIXELS = 133
OUTPUT_WIDTH = 960
OUTPUT_HEIGHT = 720

# ----------------------------------------


def frame_to_seconds(frame_name, field_name):
    if not isinstance(frame_name, str):
        raise RuntimeError(
            f"AI response does not contain a valid {field_name}."
        )

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
    return minutes * 60 + seconds + milliseconds / 100


def read_event_window():
    if not START_RESPONSE_FILE.is_file():
        raise RuntimeError(
            f"AI start response file not found: {START_RESPONSE_FILE}"
        )
    if not END_RESPONSE_FILE.is_file():
        raise RuntimeError(
            f"AI end response file not found: {END_RESPONSE_FILE}"
        )

    start_response = json.loads(
        START_RESPONSE_FILE.read_text(encoding="utf-8")
    )
    end_response = json.loads(
        END_RESPONSE_FILE.read_text(encoding="utf-8")
    )
    if start_response.get("start_match_found") is not True:
        raise RuntimeError("AI response does not contain a reliable start frame.")
    if end_response.get("end_match_found") is not True:
        raise RuntimeError("AI response does not contain a reliable end frame.")

    start_frame = start_response.get("start_frame")
    end_frame = end_response.get("end_frame")
    start_seconds = frame_to_seconds(start_frame, "start frame")
    end_seconds = frame_to_seconds(end_frame, "end frame")

    if end_seconds <= start_seconds:
        raise RuntimeError(
            "AI end frame must occur after the AI start frame."
        )

    event_duration = end_seconds - start_seconds
    clip_duration = min(event_duration, CLIP_DURATION_SECONDS)

    return start_seconds, end_seconds, clip_duration, start_frame, end_frame


def find_today_shabad():
    day_number = datetime.now(APP_TIMEZONE).day
    shabad_file = SHABADS_FOLDER / f"{day_number}.mp3"

    if not shabad_file.is_file():
        raise RuntimeError(
            f"Today's shabad was not found: {shabad_file}"
        )

    return shabad_file


def create_short(
    start_seconds,
    end_seconds,
    clip_duration,
    start_frame,
    end_frame,
    shabad_file,
):
    if not VIDEO_FILE.is_file():
        raise RuntimeError(f"Source video not found: {VIDEO_FILE}")

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    date_text = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d")
    output_file = OUTPUT_FOLDER / f"today_short_{date_text}.mp4"

    print(f"AI start frame: {start_frame}")
    print(f"Start time: {start_seconds:.2f} seconds")
    print(f"AI end frame: {end_frame}")
    print(f"End time: {end_seconds:.2f} seconds")
    print(f"Final duration: {clip_duration:.2f} seconds")
    print(f"Today's shabad: {shabad_file.name}")
    print("Creating event-based 960x720 short...")

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
        "-i",
        str(shabad_file),
        "-t",
        str(clip_duration),
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
    (
        start_seconds,
        end_seconds,
        clip_duration,
        start_frame,
        end_frame,
    ) = read_event_window()
    shabad_file = find_today_shabad()
    create_short(
        start_seconds,
        end_seconds,
        clip_duration,
        start_frame,
        end_frame,
        shabad_file,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
