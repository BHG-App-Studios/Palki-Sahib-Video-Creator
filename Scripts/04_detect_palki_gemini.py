import io
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from google import genai
    from google.genai import types
    from PIL import Image
    from pydantic import BaseModel
except ImportError:
    print(
        "Missing packages. Install them with:\n"
        "pip install google-genai pillow pydantic",
        file=sys.stderr,
    )
    raise SystemExit(1)


# ---------------- CONFIG ----------------

BASE_DIR = Path(__file__).resolve().parents[1]
FRAMES_FOLDER = BASE_DIR / "Extracted-Frames"
SAMPLES_FOLDER = BASE_DIR / "Samples"
RESPONSE_FOLDER = BASE_DIR / "AI-Response"
RESPONSE_FILE = RESPONSE_FOLDER / "response.json"

GEMINI_API_KEY_FREE = (
    os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
)
GEMINI_API_KEY_PAID = os.getenv("GEMINI_API_KEY_PAID")
GEMINI_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
)

BATCH_SIZE = 10
MINIMUM_CONFIDENCE = 95
MAX_IMAGE_SIZE = (1024, 1024)
JPEG_QUALITY = 85
MODEL_RETRY_DELAY_SECONDS = 2
ALL_MODELS_RETRY_DELAY_SECONDS = 30

# ----------------------------------------

PROMPT = """You are an expert computer vision assistant.

Your job is to inspect a sequence of extracted video frames from the official SGPC Harmandir Sahib livestream.

=========================================================
GOAL
=========================================================

Find the FIRST frame where the Palki Sahib procession begins.

Specifically detect the moment when:

• Baba Ji is carrying Sri Guru Granth Sahib Ji on the decorated Palki Sahib.
• The Palki Sahib is clearly visible.
• The ceremonial procession has started.
• This is the beginning of the procession, not the middle or end.

Return ONLY the earliest matching frame.

=========================================================
INPUT
=========================================================

Frames Folder

Extracted-Frames

Sample Images

Samples

The Samples folder contains positive examples of exactly what must be detected.

Study those images first.

Understand what the target event looks like.

Then inspect every frame inside Extracted-Frames in chronological order.

=========================================================
VERY IMPORTANT
=========================================================

Frames are named by timestamp.

Examples

00_00_00.png

00_05_00.png

00_10_00.png

...

29_55_00.png

Read them in chronological order.

Never sort alphabetically.

=========================================================
DETECTION RULES
=========================================================

Positive Match:

✔ Baba Ji carrying Sri Guru Granth Sahib Ji

✔ Decorated Palki Sahib visible

✔ Sikh ceremonial procession

✔ Procession has STARTED

Negative Match:

✘ Empty Darbar Sahib

✘ Sangat sitting

✘ Kirtan only

✘ Camera moving

✘ Before procession

✘ After procession

✘ Partial visibility with low confidence

=========================================================
CONFIDENCE
=========================================================

For every possible match calculate confidence.

Choose ONLY the earliest frame with confidence above 95%.

If confidence is lower than 95%

Return

NO RELIABLE MATCH

=========================================================
OUTPUT
=========================================================

Return ONLY this JSON.

{
    "match_found": true,
    "frame": "04_40_00.png",
    "confidence": 99,
    "reason": "First frame where Baba Ji is visibly carrying Sri Guru Granth Sahib Ji on the decorated Palki Sahib and the procession has begun."
}

If nothing is found

{
    "match_found": false
}

Do not return any other text."""


class MatchResult(BaseModel):
    match_found: bool
    frame: str | None = None
    confidence: int | None = None
    reason: str | None = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TIMESTAMP_PATTERN = re.compile(
    r"^(?P<minutes>\d+)_(?P<seconds>\d{2})_(?P<milliseconds>\d{2})"
)


def chronological_key(image_path):
    match = TIMESTAMP_PATTERN.match(image_path.stem)
    if not match:
        raise ValueError(
            f"Frame filename is not a timestamp: {image_path.name}"
        )

    return (
        int(match.group("minutes")),
        int(match.group("seconds")),
        int(match.group("milliseconds")),
    )


def find_images(folder):
    if not folder.is_dir():
        raise RuntimeError(f"Folder not found: {folder}")

    return [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]


def image_part(image_path):
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)

        image_bytes = io.BytesIO()
        image.save(
            image_bytes,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
        )

    return types.Part.from_bytes(
        data=image_bytes.getvalue(),
        mime_type="image/jpeg",
    )


def save_response(response_data):
    RESPONSE_FOLDER.mkdir(parents=True, exist_ok=True)
    response_json = json.dumps(response_data, indent=4)
    RESPONSE_FILE.write_text(response_json + "\n", encoding="utf-8")
    print(response_json)


def build_contents(sample_parts, frame_batch):
    contents = [PROMPT]

    for sample_name, sample_image in sample_parts:
        contents.append(f"POSITIVE SAMPLE IMAGE: {sample_name}")
        contents.append(sample_image)

    for frame_path in frame_batch:
        contents.append(f"CANDIDATE FRAME FILENAME: {frame_path.name}")
        contents.append(image_part(frame_path))

    return contents


def try_model_chain(client, key_label, contents, fallback_round):
    errors = []

    for model_number, model_name in enumerate(GEMINI_MODELS, start=1):
        print(
            f"Trying {key_label} key, model {model_number}/"
            f"{len(GEMINI_MODELS)} (round {fallback_round}): {model_name}",
            file=sys.stderr,
        )
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MatchResult,
                ),
            )

            return MatchResult.model_validate(json.loads(response.text)), None
        except Exception as error:
            errors.append(f"{model_name}: {error}")

            if model_number < len(GEMINI_MODELS):
                print(
                    f"{model_name} failed for the {key_label} key; "
                    f"falling back to the next model in "
                    f"{MODEL_RETRY_DELAY_SECONDS}s...",
                    file=sys.stderr,
                )
                time.sleep(MODEL_RETRY_DELAY_SECONDS)

    return None, errors


def call_gemini(clients, active_key_index, contents):
    fallback_round = 1

    while True:
        key_label, client = clients[active_key_index]
        result, errors = try_model_chain(
            client,
            key_label,
            contents,
            fallback_round,
        )
        if result is not None:
            return result, active_key_index

        if active_key_index + 1 < len(clients):
            active_key_index += 1
            fallback_round = 1
            print(
                f"All models failed with the {key_label} key. Switching to "
                f"{clients[active_key_index][0]} key for this and all "
                "remaining batches.",
                file=sys.stderr,
            )
            continue

        print(
            f"All models failed with the {key_label} key. Retrying the "
            f"complete fallback chain in {ALL_MODELS_RETRY_DELAY_SECONDS}s.\n"
            + "\n".join(errors),
            file=sys.stderr,
        )
        time.sleep(ALL_MODELS_RETRY_DELAY_SECONDS)
        fallback_round += 1


def main():
    if not GEMINI_API_KEY_FREE and not GEMINI_API_KEY_PAID:
        raise RuntimeError(
            "Neither GEMINI_API_KEY nor GEMINI_API_KEY_PAID is configured."
        )

    frame_paths = sorted(
        find_images(FRAMES_FOLDER),
        key=chronological_key,
    )
    sample_paths = sorted(find_images(SAMPLES_FOLDER), key=lambda path: path.name)

    if not frame_paths:
        raise RuntimeError(f"No frames found in: {FRAMES_FOLDER}")
    if not sample_paths:
        raise RuntimeError(f"No sample images found in: {SAMPLES_FOLDER}")

    print(
        f"Preparing {len(sample_paths)} positive sample images...",
        file=sys.stderr,
    )
    sample_parts = [
        (sample_path.name, image_part(sample_path))
        for sample_path in sample_paths
    ]

    clients = []
    if GEMINI_API_KEY_FREE:
        clients.append(
            ("free", genai.Client(api_key=GEMINI_API_KEY_FREE))
        )
    if GEMINI_API_KEY_PAID:
        clients.append(
            ("paid", genai.Client(api_key=GEMINI_API_KEY_PAID))
        )

    active_key_index = 0
    total_batches = (len(frame_paths) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_number, batch_start in enumerate(
        range(0, len(frame_paths), BATCH_SIZE),
        start=1,
    ):
        frame_batch = frame_paths[batch_start : batch_start + BATCH_SIZE]
        first_name = frame_batch[0].name
        last_name = frame_batch[-1].name

        print(
            f"Checking batch {batch_number}/{total_batches}: "
            f"{first_name} to {last_name}",
            file=sys.stderr,
        )

        result, active_key_index = call_gemini(
            clients,
            active_key_index,
            build_contents(sample_parts, frame_batch),
        )
        batch_filenames = {frame_path.name for frame_path in frame_batch}

        if (
            result.match_found
            and result.frame in batch_filenames
            and result.confidence is not None
            and result.confidence > MINIMUM_CONFIDENCE
        ):
            save_response(
                {
                    "match_found": True,
                    "frame": result.frame,
                    "confidence": result.confidence,
                    "reason": result.reason,
                }
            )
            return 0

    save_response({"match_found": False})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
