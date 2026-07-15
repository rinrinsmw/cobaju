"""Validation and local storage for original clothing images."""

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


MAX_IMAGE_BYTES = 5 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class UnsupportedImageError(Exception):
    """Raised when the upload is not an allowed image type."""


class ImageTooLargeError(Exception):
    """Raised when an upload exceeds the Phase 4 size limit."""


def detect_image_extension(header: bytes) -> str | None:
    """Identify the three supported formats from their file signatures."""

    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    return None


async def save_original_image(
    upload: UploadFile,
    upload_directory: Path,
    user_id: int,
) -> str:
    """Validate and stream one upload to a user-specific local directory.

    The returned path is relative to the configured upload root so database
    records remain portable when the project directory moves.
    """

    expected_extension = ALLOWED_CONTENT_TYPES.get(upload.content_type or "")
    if expected_extension is None:
        raise UnsupportedImageError

    first_chunk = await upload.read(READ_CHUNK_BYTES)
    detected_extension = detect_image_extension(first_chunk)
    if detected_extension != expected_extension:
        raise UnsupportedImageError

    relative_path = Path(str(user_id)) / f"{uuid4().hex}{detected_extension}"
    destination = upload_directory / relative_path
    bytes_written = 0

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stored_file:
            chunk = first_chunk
            while chunk:
                bytes_written += len(chunk)
                if bytes_written > MAX_IMAGE_BYTES:
                    raise ImageTooLargeError
                stored_file.write(chunk)
                chunk = await upload.read(READ_CHUNK_BYTES)
    except Exception:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return relative_path.as_posix()


def delete_stored_image(upload_directory: Path, relative_path: str) -> None:
    """Remove one known stored image without failing when it is already gone."""

    upload_root = upload_directory.resolve()
    stored_path = (upload_root / relative_path).resolve()
    if not stored_path.is_relative_to(upload_root):
        return
    stored_path.unlink(missing_ok=True)
