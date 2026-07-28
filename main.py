import subprocess
import time
import sys
import logging
import shutil
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
BASE_DIR = Path(r"C:\Users\Gurpreet\Downloads\Gurbani-AI")
SCRIPTS_DIR = BASE_DIR / "Scripts"

# The exact sequence of scripts to run
SCRIPTS_TO_RUN = [
    "01_download_stream.py",
    "02_cut_video.py",
    "03_extract_images.py",
    "04_detect_palki_gemini.py",
    "05_create_today_short.py"
]

FOLDERS_TO_EMPTY = [
    "Extracted-Frames",
    "30min-Clip",
    "Original-Video",
    "AI-Response",
    "Today-Short"
]

RETRY_DELAY_SECONDS = 15  # Delay before retrying a failed script

def run_script_with_retries(script_name):
    """
    Runs a python script and automatically retries it upon failure.
    """
    script_path = SCRIPTS_DIR / script_name
    
    if not script_path.is_file():
        logging.error(f"Critical Error: Script not found at {script_path}")
        sys.exit(1)

    attempt = 1
    while True:
        logging.info(f"========== Starting {script_name} (Attempt {attempt}) ==========")
        try:
            # Execute the script using the current python interpreter
            # Output is automatically streamed to the console
            subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(BASE_DIR),
                check=True
            )
            logging.info(f"========== SUCCESS: {script_name} completed successfully ==========\n")
            break  # Exit the retry loop on success
            
        except subprocess.CalledProcessError as e:
            logging.error(f"========== ERROR: {script_name} failed with exit code {e.returncode} ==========")
            logging.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...\n")
            time.sleep(RETRY_DELAY_SECONDS)
            attempt += 1
        except Exception as e:
            # Catch other unexpected exceptions (e.g. permission issues)
            logging.error(f"========== UNEXPECTED ERROR: {script_name} failed: {e} ==========")
            logging.info(f"Retrying in {RETRY_DELAY_SECONDS} seconds...\n")
            time.sleep(RETRY_DELAY_SECONDS)
            attempt += 1

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

def main():
    logging.info("Starting the Gurbani AI master automation pipeline...\n")
    
    empty_directories()
    
    for script in SCRIPTS_TO_RUN:
        run_script_with_retries(script)
        
    logging.info("ALL SCRIPTS EXECUTED SUCCESSFULLY! Master pipeline is complete.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        logging.warning("Pipeline execution interrupted by user. Exiting safely.")
        sys.exit(1)
