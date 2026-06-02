import os
from werkzeug.utils import secure_filename


def validate_extension(filename, allowed_extensions):

    if not filename:
        return False

    if "." not in filename:
        return False

    ext = filename.rsplit(".", 1)[1].lower()

    return ext in allowed_extensions


def safe_upload_filename(filename):

    return secure_filename(filename)


def validate_file_size(file, max_bytes):

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    return size <= max_bytes