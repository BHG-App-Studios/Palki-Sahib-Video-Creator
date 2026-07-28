import glob
import os
import subprocess
from pathlib import Path


# ---------------- CONFIG ----------------

BASE_DIR = Path(__file__).resolve().parents[1]
INPUT_FOLDER = BASE_DIR / "30min-Clip"
OUTPUT_FOLDER = BASE_DIR / "Extracted-Frames"

CLIP_DURATION_SECONDS = 30 * 60
FRAME_INTERVAL_SECONDS = 5

# ----------------------------------------

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)


def timestamp_filename(total_seconds):
    minutes, seconds = divmod(total_seconds, 60)
    milliseconds = 0

    # Colons are invalid in Windows filenames, so use underscores.
    return f"{minutes:02d}_{seconds:02d}_{milliseconds:02d}.png"


video_extensions = ("*.mp4", "*.mkv", "*.webm")
video_file = None

for extension in video_extensions:
    files = list(INPUT_FOLDER.glob(extension))
    if files:
        video_file = files[0]
        break

if not video_file:
    print("No 30-minute clip found.")
    raise SystemExit(1)


print(f"Extracting frames from: {video_file}")

regular_frame_count = (
    CLIP_DURATION_SECONDS // FRAME_INTERVAL_SECONDS
) - 1
temporary_pattern = str(OUTPUT_FOLDER / "_frame_%03d.png")

for temporary_file in glob.glob(
    str(OUTPUT_FOLDER / "_frame_*.png")
):
    os.remove(temporary_file)

print(
    f"Extracting {regular_frame_count} frames in one fast FFmpeg pass..."
)

command = [
    "ffmpeg",
    "-y",
    "-hide_banner",
    "-loglevel",
    "error",
    "-stats",
    "-ss",
    str(FRAME_INTERVAL_SECONDS),
    "-i",
    video_file,
    "-vf",
    f"fps=1/{FRAME_INTERVAL_SECONDS}:start_time=0",
    "-frames:v",
    str(regular_frame_count),
    "-q:v",
    "2",
    temporary_pattern,
]

subprocess.run(command, check=True)

temporary_files = sorted(
    glob.glob(str(OUTPUT_FOLDER / "_frame_*.png"))
)
if len(temporary_files) != regular_frame_count:
    raise RuntimeError(
        f"Expected {regular_frame_count} frames, "
        f"but FFmpeg created {len(temporary_files)}."
    )

for frame_number, temporary_file in enumerate(temporary_files, start=1):
    timestamp = frame_number * FRAME_INTERVAL_SECONDS
    output_file = OUTPUT_FOLDER / timestamp_filename(timestamp)
    os.replace(temporary_file, output_file)

# Extract the last available frame and name it as the 30-minute endpoint.
final_output_file = OUTPUT_FOLDER / timestamp_filename(CLIP_DURATION_SECONDS)
subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-sseof",
        "-0.1",
        "-i",
        str(video_file),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(final_output_file),
    ],
    check=True,
)

print(
    f"\nDone! 360 frames saved in: {OUTPUT_FOLDER}"
)
