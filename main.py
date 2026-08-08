import os
import subprocess
import time
import sys
import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Configure logging for production-ready output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Base directories
BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "Scripts"
PLAN_FILE = BASE_DIR / "Clip-Plan" / "clip_plan.json"
RESPONSE_FILE = BASE_DIR / "AI-Response" / "response.json"

# 01 downloads once (covering every candidate window and writing the clip plan).
DOWNLOAD_SCRIPT = "01_download_stream.py"

# These run once per candidate window: cut that window, extract its frames, and
# ask Gemini.  A clean "no match" (not an error) re-runs them on the next window.
DETECTION_SCRIPTS = [
    "02_cut_video.py",
    "03_extract_images.py",
    "04_detect_palki_gemini.py",
]

# These run once, only after a window matched, to build and publish the short.
FINALIZE_SCRIPTS = [
    "05_create_today_short.py",
    "06_calculate_event_time.py",
    "create_video.js",
]

FOLDERS_TO_EMPTY = [
    "Extracted-Frames",
    "30min-Clip",
    "Original-Video",
    "AI-Response",
    "Today-Short",
    "Clip-Plan"
]

RETRY_DELAY_SECONDS = 15  # Delay before retrying a failed script
MAX_SCRIPT_ATTEMPTS = 5
IST = timezone(timedelta(hours=5, minutes=30))

def run_script_with_retries(script_name, extra_env=None):
    """
    Runs a script and automatically retries it upon failure.
    """
    script_path = SCRIPTS_DIR / script_name

    if not script_path.is_file():
        logging.error(f"Critical Error: Script not found at {script_path}")
        sys.exit(1)

    if script_path.suffix == '.py':
        cmd = [sys.executable, str(script_path)]
    elif script_path.suffix == '.js':
        cmd = ["node", str(script_path)]
    else:
        logging.error(f"Critical Error: Unsupported script extension for {script_name}")
        sys.exit(1)

    run_env = None
    if extra_env:
        run_env = os.environ.copy()
        run_env.update({key: str(value) for key, value in extra_env.items()})

    for attempt in range(1, MAX_SCRIPT_ATTEMPTS + 1):
        logging.info(f"========== Starting {script_name} (Attempt {attempt}) ==========")
        try:
            # Execute the script
            # Output is automatically streamed to the console
            subprocess.run(
                cmd,
                cwd=str(BASE_DIR),
                check=True,
                env=run_env,
            )
            logging.info(f"========== SUCCESS: {script_name} completed successfully ==========\n")
            return

        except subprocess.CalledProcessError as e:
            logging.error(f"========== ERROR: {script_name} failed with exit code {e.returncode} ==========")
        except Exception as e:
            # Catch other unexpected exceptions (e.g. permission issues)
            logging.error(f"========== UNEXPECTED ERROR: {script_name} failed: {e} ==========")

        if attempt == MAX_SCRIPT_ATTEMPTS:
            raise RuntimeError(
                f"{script_name} failed after {MAX_SCRIPT_ATTEMPTS} attempts."
            )

        logging.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...\n")
        time.sleep(RETRY_DELAY_SECONDS)

def empty_directories():
    logging.info("Cleaning up specified directories...")
    for folder_name in FOLDERS_TO_EMPTY:
        folder_path = BASE_DIR / folder_name
        if folder_path.exists():
            logging.info(f"Emptying folder: {folder_name}")
            try:
                for item in folder_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            except Exception as e:
                logging.error(f"Failed to clear {folder_name}: {e}")
        else:
            logging.info(f"Folder {folder_name} does not exist. Creating it...")
            folder_path.mkdir(parents=True, exist_ok=True)
    logging.info("Cleanup complete.\n")

def count_plan_attempts():
    """How many candidate clip windows 01 produced for this stream."""
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    attempts = plan.get("attempts") or []
    if not attempts:
        raise RuntimeError("Clip plan produced no candidate windows.")
    return attempts


def gemini_found_match():
    """True only if 04 wrote a reliable match into response.json."""
    if not RESPONSE_FILE.is_file():
        return False
    try:
        response = json.loads(RESPONSE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return response.get("match_found") is True


def run_detection_with_fallback(attempts):
    """Cut+extract+detect for each candidate window until Gemini matches.

    Windows are tried in the order 01 recorded: current month, then previous,
    then next.  Every window differs by only a few minutes and is already inside
    the single download, so a fallback just re-cuts the same file -- there is no
    extra download.  A clean "no match" advances to the next window; a genuine
    script error still burns the per-script retries and fails the run.  If no
    window matches, the run fails so the admin-failure notifier fires.
    """
    total = len(attempts)
    for index, attempt in enumerate(attempts):
        logging.info(
            f"########## Detection window {index + 1}/{total}: "
            f"{attempt['order']} month {attempt['punjabi_month']} "
            f"(Palki {attempt['scheduled_palki_time_ist']}, "
            f"clip {attempt['clip_start_ist']} to {attempt['clip_end_ist']}) "
            "##########"
        )
        attempt_env = {"PALKI_ATTEMPT_INDEX": index}
        for script in DETECTION_SCRIPTS:
            run_script_with_retries(script, extra_env=attempt_env)

        if gemini_found_match():
            logging.info(
                f"Palki Sahib matched in the {attempt['order']} window "
                f"({attempt['punjabi_month']}). Proceeding to publish."
            )
            return index

        if index + 1 < total:
            logging.warning(
                f"No match in the {attempt['order']} window "
                f"({attempt['punjabi_month']}). Falling back to the next "
                "candidate window (re-cutting the same download)..."
            )

    raise RuntimeError(
        f"Palki Sahib was not found in any of the {total} candidate window(s). "
        "The stream may not contain the procession; failing so the admin is "
        "notified instead of retrying indefinitely."
    )


def main():
    # Keep every stage on the same India calendar date, even if a long run
    # crosses midnight while Gemini/FFmpeg/publishing are still running.
    os.environ["PIPELINE_DATE"] = datetime.now(IST).strftime("%Y-%m-%d")
    logging.info(f"Pinned pipeline date (IST): {os.environ['PIPELINE_DATE']}")
    logging.info("Starting the Gurbani AI master automation pipeline...\n")

    empty_directories()

    # 1) Download once, covering every candidate clip window.
    run_script_with_retries(DOWNLOAD_SCRIPT)
    attempts = count_plan_attempts()
    logging.info(
        f"Plan has {len(attempts)} candidate window(s): "
        + ", ".join(
            f"{a['order']}={a['punjabi_month']}@{a['scheduled_palki_time_ist']}"
            for a in attempts
        )
    )

    # 2) Try each window until Gemini finds the procession (or all windows fail).
    matched_index = run_detection_with_fallback(attempts)
    os.environ["PALKI_ATTEMPT_INDEX"] = str(matched_index)

    # 3) Build and publish the short from the winning window.
    for script in FINALIZE_SCRIPTS:
        run_script_with_retries(script, extra_env={"PALKI_ATTEMPT_INDEX": matched_index})

    logging.info("ALL SCRIPTS EXECUTED SUCCESSFULLY! Master pipeline is complete.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        logging.warning("Pipeline execution interrupted by user. Exiting safely.")
        sys.exit(1)
