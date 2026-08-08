"""Shared Palki Sahib scheduling logic.

The livestream can start at any time (typically 3:00-3:55 AM IST), but the
"Departure of Palki Sahib from Sri Akal Takhat Sahib" happens at a fixed clock
time that only depends on the Punjabi month (roughly 4:00-5:00 AM IST).

Instead of cutting a fixed video *offset* (which drifts off the event whenever
the stream starts late), the pipeline anchors everything to real clock time:

    clip window = [target - 15 min, target + 15 min]   (30 minutes total)

where ``target`` is the scheduled Palki Sahib time for the day, and offsets are
measured from the stream's ``actualStartTime`` (== offset 0 in the download).

This module is the single source of truth, imported by 01 (download), 02 (cut)
and 06 (event time).  Scripts run with their own directory on ``sys.path``, so a
plain ``import palki_schedule`` resolves for every sibling script.
"""

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parents[1]
PLAN_FOLDER = BASE_DIR / "Clip-Plan"
PLAN_FILE = PLAN_FOLDER / "clip_plan.json"

IST = timezone(timedelta(hours=5, minutes=30))

# --- Tunable window configuration ---------------------------------------------
# Keep the clip at exactly 30 minutes so the downstream frame extractor (03) and
# Gemini detector (04) keep their current 360-frame / 36-batch cost unchanged.
CLIP_PRE_SECONDS = 15 * 60          # start the clip 15 min before the event
CLIP_POST_SECONDS = 15 * 60         # end the clip 15 min after the event
CLIP_DURATION_SECONDS = CLIP_PRE_SECONDS + CLIP_POST_SECONDS  # 1800 (30 min)
DOWNLOAD_TAIL_SECONDS = 5 * 60      # download a little past clip end for a safe trim

# --- Monthly Palki Sahib schedule ---------------------------------------------
# "Departure of Palki Sahib from Sri Akal Takhat Sahib" (morning), per Punjabi
# month.  Each entry: (period_start_month, period_start_day, name, hour, minute).
# Times are IST.
#
# Sources (both official SGPC), cross-checked:
#   - Departure time  : sgpc.net/daily-routine  ("ਪਾਲਕੀ ਸਾਹਿਬ ... ਚੱਲਣ ਦਾ ਸਮਾਂ")
#         Jeth+Harh 4:00, Vaisakh+Sawan 4:15, Chet+Bhadon 4:30,
#         Phaggan+Assu 4:45, Kattak+Maggar+Poh+Magh 5:00.
#   - Month start/end dates : SGPC Punjabi-month (Bikrami) calendar table.
#
# The times are symmetric around the summer solstice (Jeth/Harh = earliest 4:00,
# rising to 5:00 through the winter months).
PALKI_SCHEDULE = [
    (3, 14, "Chet", 4, 30),       # 14 Mar - 13 Apr
    (4, 14, "Vaisakh", 4, 15),    # 14 Apr - 14 May
    (5, 15, "Jeth", 4, 0),        # 15 May - 14 Jun
    (6, 15, "Harh", 4, 0),        # 15 Jun - 15 Jul
    (7, 16, "Sawan", 4, 15),      # 16 Jul - 15 Aug
    (8, 16, "Bhadon", 4, 30),     # 16 Aug - 14 Sep
    (9, 15, "Assu", 4, 45),       # 15 Sep - 14 Oct
    (10, 15, "Kattak", 5, 0),     # 15 Oct - 13 Nov
    (11, 14, "Maggar", 5, 0),     # 14 Nov - 13 Dec
    (12, 14, "Poh", 5, 0),        # 14 Dec - 12 Jan
    (1, 13, "Magh", 5, 0),        # 13 Jan - 11 Feb
    (2, 12, "Phaggan", 4, 45),    # 12 Feb - 13 Mar
]


def _ordinal(month, day):
    return month * 100 + day


def palki_schedule_for(date):
    """Return (month_name, hour, minute) for the given date.

    Picks the period whose start is the latest one on or before the date.
    Dates in early January (before Magh on 14 Jan) wrap to Poh (16 Dec).
    """
    date_ord = _ordinal(date.month, date.day)

    best = None  # (start_ord, name, hour, minute)
    for month, day, name, hour, minute in PALKI_SCHEDULE:
        start_ord = _ordinal(month, day)
        if start_ord <= date_ord and (best is None or start_ord > best[0]):
            best = (start_ord, name, hour, minute)

    if best is None:
        # Date is before the earliest period start of the year -> wrap to the
        # period with the largest start ordinal (Poh, 16 Dec).
        best = max(
            (
                (_ordinal(month, day), name, hour, minute)
                for month, day, name, hour, minute in PALKI_SCHEDULE
            ),
            key=lambda entry: entry[0],
        )

    return best[1], best[2], best[3]


def fetch_actual_start_time(video_id, api_key):
    """Return the livestream's actualStartTime as an aware UTC datetime."""
    if not api_key:
        raise RuntimeError("YT_API_KEY is missing.")

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={
            "part": "liveStreamingDetails",
            "id": video_id,
            "key": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        raise RuntimeError(f"YouTube Data API returned no video for ID: {video_id}")

    actual_start = items[0].get("liveStreamingDetails", {}).get("actualStartTime")
    if not actual_start:
        raise RuntimeError(
            "YouTube Data API did not return liveStreamingDetails.actualStartTime."
        )

    try:
        parsed = datetime.fromisoformat(actual_start.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(f"Invalid YouTube actualStartTime: {actual_start}") from error

    return parsed.astimezone(timezone.utc)


def compute_plan(actual_start_utc, video_id, video_url):
    """Build the clock-time-anchored clip plan for a given stream start."""
    start_ist = actual_start_utc.astimezone(IST)
    event_date = start_ist.date()

    month_name, hour, minute = palki_schedule_for(event_date)
    target_ist = datetime(
        event_date.year, event_date.month, event_date.day, hour, minute, 0, tzinfo=IST
    )

    target_offset = (target_ist - start_ist).total_seconds()
    if target_offset <= 0:
        raise RuntimeError(
            "Livestream started at or after the scheduled Palki Sahib time "
            f"({month_name} {hour:02d}:{minute:02d} IST); the event cannot be "
            f"captured from the stream start ({start_ist.isoformat()})."
        )

    clip_start_offset = max(0, int(round(target_offset - CLIP_PRE_SECONDS)))
    clip_duration = CLIP_DURATION_SECONDS
    download_seconds = int(
        math.ceil(clip_start_offset + clip_duration + DOWNLOAD_TAIL_SECONDS)
    )

    clip_start_ist = start_ist + timedelta(seconds=clip_start_offset)
    clip_end_ist = clip_start_ist + timedelta(seconds=clip_duration)

    return {
        "video_id": video_id,
        "video_url": video_url,
        "punjabi_month": month_name,
        "scheduled_palki_time_ist": f"{hour:02d}:{minute:02d}",
        "actual_start_utc": actual_start_utc.isoformat().replace("+00:00", "Z"),
        "actual_start_ist": start_ist.isoformat(),
        "target_ist": target_ist.isoformat(),
        "target_offset_seconds": int(round(target_offset)),
        "clip_start_offset_seconds": clip_start_offset,
        "clip_duration_seconds": clip_duration,
        "download_seconds": download_seconds,
        "clip_start_ist": clip_start_ist.isoformat(),
        "clip_end_ist": clip_end_ist.isoformat(),
    }


def write_plan(plan):
    PLAN_FOLDER.mkdir(parents=True, exist_ok=True)
    PLAN_FILE.write_text(json.dumps(plan, indent=4) + "\n", encoding="utf-8")
    return PLAN_FILE


def read_plan():
    if not PLAN_FILE.is_file():
        raise RuntimeError(
            f"Clip plan not found: {PLAN_FILE}. Run 01_download_stream.py first."
        )
    return json.loads(PLAN_FILE.read_text(encoding="utf-8"))
