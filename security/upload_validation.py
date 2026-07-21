"""Small validation helpers for uploaded telemetry files."""

import os
from werkzeug.utils import secure_filename


def validate_extension(filename, allowed_extensions):
    """Return True when the filename extension is explicitly allowed."""

    if not filename:
        return False

    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()

    return ext in allowed_extensions


def safe_upload_filename(filename):
    """Normalize upload names so they are safe to store on disk."""

    return secure_filename(filename)


def validate_file_size(file, max_bytes):
    """Check upload size without consuming the file stream."""

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    return size <= max_bytes
