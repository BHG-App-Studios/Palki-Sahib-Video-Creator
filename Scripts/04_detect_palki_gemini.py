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

# A single free Gemini API key is read from GEMINI_API_KEY (GOOGLE_API_KEY is
# also accepted for backward compatibility).
GEMINI_MODEL = "gemini-2.5-flash-lite"

BATCH_SIZE = 10
MINIMUM_CONFIDENCE = 95
# 765x765 keeps each image just under Gemini's 768px single-tile threshold,
# so every image costs the minimum 258 tokens.
MAX_IMAGE_SIZE = (765, 765)
JPEG_QUALITY = 85
RETRY_DELAY_SECONDS = 30
MAX_RETRIES = 5
# Do not let one stalled Gemini request hold the GitHub Actions job forever.
GEMINI_REQUEST_TIMEOUT_MILLISECONDS = 60_000

# ----------------------------------------

PROMPT = """You are an expert computer vision assistant.

Your job is to inspect a sequence of extracted video frames from the official SGPC Harmandir Sahib livestream and find the ONE frame that looks EXACTLY like the POSITIVE SAMPLE images you are given.

=========================================================
STUDY THE SAMPLE IMAGES FIRST (MOST IMPORTANT)
=========================================================

The POSITIVE SAMPLE images are the ground truth. The frame you return MUST match those samples. Study them before looking at any candidate frame.

The two things that define a correct match are:

• Baba Ji is CARRYING Sri Guru Granth Sahib Ji (a decorated, cloth-wrapped Rumala bundle) balanced ON TOP OF HIS HEAD, holding it up with BOTH raised hands.
• Baba Ji is wearing a MARIGOLD (orange/yellow) flower garland around his neck.

The marigold garland is the key signal that the procession has started and Baba Ji is carrying Sri Guru Granth Sahib Ji outside toward the Palki Sahib — NOT the earlier moment inside where it is just being lifted onto the head (no garland yet).

Do not depend on background colors, lighting, or decorations — those can change from day to day. Rely on the two points above and the overall look of the samples.

=========================================================
GOAL
=========================================================

Find the EXACT FIRST (earliest) frame that matches the samples: Baba Ji actively CARRYING Sri Guru Granth Sahib Ji on his head with both hands raised, wearing the marigold garland, as it is carried toward the Palki Sahib.

Return ONLY the earliest matching frame.

=========================================================
DO NOT MATCH THESE (COMMON MISTAKES)
=========================================================


✘ ONLY the decorated Palki Sahib visible from afar, without Baba Ji carrying on his head.

✘ Baba Ji not yet carrying Sri Guru Granth Sahib Ji on his head.

✘ Empty Darbar Sahib.

✘ Sangat sitting.

✘ Kirtan only.

✘ Camera moving / blurry.

✘ Before or after the procession.

✘ Partial visibility with low confidence.

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

39_55_00.png

Read them in chronological order.

Never sort alphabetically.

=========================================================
DETECTION RULES
=========================================================

Positive Match (must look like the samples):

✔ Baba Ji actively CARRYING Sri Guru Granth Sahib Ji balanced ON HIS HEAD with both hands raised

✔ Baba Ji is wearing a MARIGOLD flower garland

✔ Sikh ceremonial procession that has STARTED and is moving toward the Palki Sahib

Negative Match:

✘ Baba Ji is still lifting / placing Sri Guru Granth Sahib Ji onto the head and is NOT yet wearing the marigold garland (wrong, earlier moment)

✘ ONLY the decorated Palki Sahib is visible from afar (without Baba Ji carrying Sri Guru Granth Sahib Ji on his head)

✘ Baba Ji is not yet carrying Sri Guru Granth Sahib Ji on his head

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
    "reason": "First frame where Baba Ji is visibly carrying Sri Guru Granth Sahib Ji on his head, marking the strict start of the procession."
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


def load_api_key():
    """Read the single free Gemini API key.

    Uses GEMINI_API_KEY, falling back to GOOGLE_API_KEY for backward
    compatibility.  Returns the key string, or None when neither is set.
    """
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    key = key.strip() if key else ""
    return key or None


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


def describe_gemini_error(error):
    """Turn a Gemini/SDK exception into one concise, log-friendly line.

    The google-genai SDK raises APIError subclasses (ClientError, ServerError)
    that carry the HTTP status code and the server's JSON error body, which is
    what actually states the cause: quota/rate limit ("429 RESOURCE_EXHAUSTED"),
    an unavailable or unknown model ("404 NOT_FOUND"), a bad request
    ("400 INVALID_ARGUMENT"), a transient outage ("503 UNAVAILABLE"), etc.
    Other failures (request timeout, or the model returning non-JSON) fall back
    to the exception type and message.  Surfacing this is what lets the logs
    explain WHY a model was skipped, not just that it was.
    """
    parts = [type(error).__name__]

    header = []
    code = getattr(error, "code", None)
    if code is not None:
        header.append(str(code))
    status = getattr(error, "status", None)
    if status:
        header.append(str(status))
    if header:
        parts.append(" ".join(header))

    message = getattr(error, "message", None) or str(error)
    # Collapse newlines/indentation from the JSON body into a single line.
    message = " ".join(message.split())
    if message:
        parts.append(message)

    return " | ".join(parts)


def call_gemini(client, contents):
    """Call the single Gemini model, retrying the same request on failure.

    There is no model or key fallback: one model, one key.  On any error
    (rate limit, transient outage, timeout, non-JSON reply) the exact same
    request is retried up to MAX_RETRIES times with a delay in between."""
    last_error = "(no error captured)"

    for attempt in range(1, MAX_RETRIES + 1):
        print(
            f"Trying {GEMINI_MODEL} (attempt {attempt}/{MAX_RETRIES})",
            file=sys.stderr,
        )
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MatchResult,
                ),
            )

            return MatchResult.model_validate(json.loads(response.text))
        except Exception as error:
            last_error = describe_gemini_error(error)
            print(
                f"  [FAIL] {GEMINI_MODEL} (attempt {attempt}/{MAX_RETRIES}): "
                f"{last_error}",
                file=sys.stderr,
            )

            if attempt < MAX_RETRIES:
                print(
                    f"  -> Retrying in {RETRY_DELAY_SECONDS}s...",
                    file=sys.stderr,
                )
                time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"Gemini failed to return a response after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


def main():
    api_key = load_api_key()
    if not api_key:
        raise RuntimeError(
            "No Gemini API key configured. Set GEMINI_API_KEY."
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

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=GEMINI_REQUEST_TIMEOUT_MILLISECONDS
        ),
    )

    print(
        f"Loaded Gemini API key. Using model {GEMINI_MODEL}.",
        file=sys.stderr,
    )
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

        contents = build_contents(sample_parts, frame_batch)
        result = call_gemini(client, contents)
        batch_filenames = {frame_path.name for frame_path in frame_batch}

        is_match = (
            result.match_found
            and result.frame in batch_filenames
            and result.confidence is not None
            and result.confidence > MINIMUM_CONFIDENCE
        )
        if not is_match:
            continue

        matched_index = next(
            index
            for index, frame_path in enumerate(frame_paths)
            if frame_path.name == result.frame
        )
        verification_start = matched_index - 3
        verification_end = matched_index + 7
        if verification_start < 0 or verification_end > len(frame_paths):
            print(
                f"  Verification rejected {result.frame}: fewer than 3 earlier "
                "or 6 later frames are available. Continuing to the next batch.",
                file=sys.stderr,
            )
            continue

        verification_batch = frame_paths[verification_start:verification_end]
        print(
            f"  Possible match: {result.frame} at {result.confidence}% confidence. "
            f"Verifying with {verification_batch[0].name} to "
            f"{verification_batch[-1].name}; the match is frame 4/10...",
            file=sys.stderr,
        )
        verification = call_gemini(
            client,
            build_contents(sample_parts, verification_batch),
        )
        verification_filenames = {
            frame_path.name for frame_path in verification_batch
        }
        is_verified = (
            verification.match_found
            and verification.frame == result.frame
            and verification.frame in verification_filenames
            and verification.confidence is not None
            and verification.confidence > MINIMUM_CONFIDENCE
        )

        if not is_verified:
            verification_summary = (
                f"frame={verification.frame}, confidence={verification.confidence}"
                if verification.match_found
                else "no reliable match"
            )
            print(
                f"  Verification rejected {result.frame} ({verification_summary}). "
                "Continuing to the next batch.",
                file=sys.stderr,
            )
            continue

        print(
            f"  Match verified twice: {verification.frame} at "
            f"{verification.confidence}% confidence.",
            file=sys.stderr,
        )
        save_response(
            {
                "match_found": True,
                "frame": verification.frame,
                "confidence": verification.confidence,
                "reason": verification.reason,
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
