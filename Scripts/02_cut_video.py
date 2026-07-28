import subprocess
from pathlib import Path

# ---------------- CONFIG ----------------

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_FOLDER = BASE_DIR / "Original-Video"
OUTPUT_FOLDER = BASE_DIR / "30min-Clip"

START_TIME = "01:00:00"
DURATION = "00:30:00"

# ----------------------------------------

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

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
    "-ss", START_TIME,
    "-i", str(video_file),
    "-t", DURATION,
    "-c", "copy",
    str(output_file)
]

print("Cutting video...")

subprocess.run(command, check=True)

print("Done!")
print(output_file)
