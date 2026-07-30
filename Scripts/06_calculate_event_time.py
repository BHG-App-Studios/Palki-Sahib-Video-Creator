import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
RESPONSE_FILE = BASE_DIR / "AI-Response" / "response.json"
ORIGINAL_VIDEO_FOLDER = BASE_DIR / "Original-Video"
YT_API_KEY = os.getenv("YT_API_KEY")
IST = timezone(timedelta(hours=5, minutes=30))

# These values must match Scripts/02_cut_video.py.  The AI examines the
# 30-minute section from 01:00:00 through 01:30:00 of the livestream.
CUT_START_OFFSET = timedelta(hours=1)
CUT_DURATION = timedelta(minutes=30)
FRAME_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<minutes>\d+)_(?P<seconds>\d{2})_(?P<hundredths>\d{2})\.png$"
)
VIDEO_ID_PATTERN = re.compile(r"^(?P<video_id>.+)_first_\d+_minutes\.(?:mp4|mkv|webm)$")


def get_video_id():
    candidates = []
    for extension in ("*.mp4", "*.mkv", "*.webm"):
        candidates.extend(ORIGINAL_VIDEO_FOLDER.glob(extension))

    for candidate in sorted(candidates):
        match = VIDEO_ID_PATTERN.match(candidate.name)
        if match:
            return match.group("video_id")

    raise RuntimeError("Could not identify the downloaded YouTube video ID.")


def get_actual_start_time(video_id):
    if not YT_API_KEY:
        raise RuntimeError("YT_API_KEY is missing.")

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={
            "part": "liveStreamingDetails",
            "id": video_id,
            "key": YT_API_KEY,
        },
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        raise RuntimeError(f"YouTube Data API returned no video for ID: {video_id}")

    actual_start = items[0].get("liveStreamingDetails", {}).get("actualStartTime")
    if not actual_start:
        raise RuntimeError("YouTube Data API did not return liveStreamingDetails.actualStartTime.")

    try:
        return datetime.fromisoformat(actual_start.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(f"Invalid YouTube actualStartTime: {actual_start}") from error


def frame_offset(frame_name):
    match = FRAME_TIMESTAMP_PATTERN.fullmatch(frame_name or "")
    if not match:
        raise RuntimeError(f"Invalid Gemini frame timestamp: {frame_name!r}")

    return timedelta(
        minutes=int(match.group("minutes")),
        seconds=int(match.group("seconds")),
        milliseconds=int(match.group("hundredths")) * 10,
    )


def format_ist_time(value):
    hour = value.hour % 12 or 12
    period = "AM" if value.hour < 12 else "PM"
    return f"{hour:02d}:{value.minute:02d} {period}"


def main():
    if not RESPONSE_FILE.is_file():
        raise RuntimeError(f"Gemini response file was not found: {RESPONSE_FILE}")

    response_data = json.loads(RESPONSE_FILE.read_text(encoding="utf-8"))
    if response_data.get("match_found") is not True:
        raise RuntimeError("Gemini did not find a reliable Palki Sahib start frame.")

    detected_offset = frame_offset(response_data.get("frame"))
    if detected_offset > CUT_DURATION:
        raise RuntimeError("Gemini frame timestamp is outside the 30-minute clip.")

    video_id = get_video_id()
    actual_start_utc = get_actual_start_time(video_id).astimezone(timezone.utc)
    clip_start_utc = actual_start_utc + CUT_START_OFFSET
    event_time_utc = clip_start_utc + detected_offset
    event_time_ist = event_time_utc.astimezone(IST)

    response_data["youtube_video_id"] = video_id
    response_data["livestream_actual_start_utc"] = actual_start_utc.isoformat().replace("+00:00", "Z")
    response_data["clip_start_ist"] = clip_start_utc.astimezone(IST).isoformat()
    response_data["clip_end_ist"] = (clip_start_utc + CUT_DURATION).astimezone(IST).isoformat()
    response_data["event_time_ist"] = format_ist_time(event_time_ist)
    response_data["event_timestamp_ist"] = event_time_ist.isoformat()
    RESPONSE_FILE.write_text(json.dumps(response_data, indent=4) + "\n", encoding="utf-8")

    print(f"YouTube livestream started: {actual_start_utc.isoformat()} UTC")
    print(f"AI clip window: {response_data['clip_start_ist']} to {response_data['clip_end_ist']}")
    print(f"Palki Sahib event time: {response_data['event_time_ist']}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, requests.RequestException) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
