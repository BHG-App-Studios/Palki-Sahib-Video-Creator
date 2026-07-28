import os
import subprocess
import glob

# ---------------- CONFIG ----------------

INPUT_FOLDER = r"C:\Users\Gurpreet\Downloads\Gurbani-AI\Original-Video"

OUTPUT_FOLDER = r"C:\Users\Gurpreet\Downloads\Gurbani-AI\30min-Clip"

START_TIME = "01:00:00"
DURATION = "00:30:00"

# ----------------------------------------

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Find downloaded video
video_extensions = ("*.mp4", "*.mkv", "*.webm")

video_file = None

for ext in video_extensions:
    files = glob.glob(os.path.join(INPUT_FOLDER, ext))
    if files:
        video_file = files[0]
        break

if not video_file:
    print("No downloaded video found.")
    exit()

output_file = os.path.join(OUTPUT_FOLDER, "30min_clip.mp4")

command = [
    "ffmpeg",
    "-y",
    "-ss", START_TIME,
    "-i", video_file,
    "-t", DURATION,
    "-c", "copy",
    output_file
]

print("Cutting video...")

subprocess.run(command)

print("Done!")
print(output_file)