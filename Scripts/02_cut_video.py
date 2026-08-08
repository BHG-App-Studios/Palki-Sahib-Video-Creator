import subprocess
from pathlib import Path

from palki_schedule import active_attempt, read_plan

# ---------------- CONFIG ----------------

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_FOLDER = BASE_DIR / "Original-Video"
OUTPUT_FOLDER = BASE_DIR / "30min-Clip"

# ----------------------------------------

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

# The clip window is anchored to the scheduled Palki Sahib clock time (computed
# in 01_download_stream.py), not a fixed video offset, so a late-starting stream
# still lands the event in the middle of the clip.  PALKI_ATTEMPT_INDEX selects
# which candidate window (current / previous / next month) to cut this pass; the
# whole download already covers every window, so this only changes the -ss/-t.
plan = read_plan()
attempt_index, attempt = active_attempt(plan)
start_seconds = attempt["clip_start_offset_seconds"]
duration_seconds = plan["clip_duration_seconds"]

# Find downloaded video
video_extensions = ("*.mp4", "*.mkv", "*.webm")

video_file = None

for ext in video_extensions:
    files = list(INPUT_FOLDER.glob(ext))
    if files:
        video_file = files[0]
        break

if not video_file:
    print("No downloaded video found.")
    raise SystemExit(1)

output_file = OUTPUT_FOLDER / "30min_clip.mp4"

command = [
    "ffmpeg",
    "-y",
    "-ss", str(start_seconds),
    "-i", str(video_file),
    "-t", str(duration_seconds),
    "-c", "copy",
    str(output_file)
]

print(
    f"[attempt {attempt_index}: {attempt['order']}] "
    f"Cutting {attempt['clip_start_ist']} to {attempt['clip_end_ist']} "
    f"({attempt['punjabi_month']}, Palki at {attempt['scheduled_palki_time_ist']})..."
)

subprocess.run(command, check=True)

print("Done!")
print(output_file)
