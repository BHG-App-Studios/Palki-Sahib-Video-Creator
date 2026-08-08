import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from palki_schedule import IST, read_plan


BASE_DIR = Path(__file__).resolve().parents[1]
RESPONSE_FILE = BASE_DIR / "AI-Response" / "response.json"

# The clip window is anchored to real clock time by 01_download_stream.py and
# recorded in Clip-Plan/clip_plan.json.  This script only maps the Gemini frame
# offset onto that window to recover the real-world event time.
FRAME_TIMESTAMP_PATTERN = re.compile(
    r"^(?P<minutes>\d+)_(?P<seconds>\d{2})_(?P<hundredths>\d{2})\.png$"
)


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

    plan = read_plan()
    clip_duration = timedelta(seconds=plan["clip_duration_seconds"])
    clip_start_offset = timedelta(seconds=plan["clip_start_offset_seconds"])

    detected_offset = frame_offset(response_data.get("frame"))
    if detected_offset > clip_duration:
        raise RuntimeError("Gemini frame timestamp is outside the clip.")

    actual_start_utc = datetime.fromisoformat(
        plan["actual_start_utc"].replace("Z", "+00:00")
    ).astimezone(timezone.utc)
    clip_start_utc = actual_start_utc + clip_start_offset
    event_time_utc = clip_start_utc + detected_offset
    event_time_ist = event_time_utc.astimezone(IST)

    response_data["youtube_video_id"] = plan["video_id"]
    response_data["punjabi_month"] = plan["punjabi_month"]
    response_data["scheduled_palki_time_ist"] = plan["scheduled_palki_time_ist"]
    response_data["livestream_actual_start_utc"] = plan["actual_start_utc"]
    response_data["clip_start_ist"] = clip_start_utc.astimezone(IST).isoformat()
    response_data["clip_end_ist"] = (clip_start_utc + clip_duration).astimezone(IST).isoformat()
    response_data["event_time_ist"] = format_ist_time(event_time_ist)
    response_data["event_timestamp_ist"] = event_time_ist.isoformat()
    RESPONSE_FILE.write_text(json.dumps(response_data, indent=4) + "\n", encoding="utf-8")

    print(f"YouTube livestream started: {actual_start_utc.isoformat()} UTC")
    print(f"AI clip window: {response_data['clip_start_ist']} to {response_data['clip_end_ist']}")
    print(f"Palki Sahib event time: {response_data['event_time_ist']}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
