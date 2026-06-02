import logging
import os


os.makedirs(
    "logs",
    exist_ok=True
)


def build_logger(name, filename):

    logger = logging.getLogger(name)

    logger.setLevel(logging.INFO)

    if not logger.handlers:

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )

        file_handler = logging.FileHandler(
            f"logs/{filename}"
        )

        file_handler.setFormatter(
            formatter
        )

        logger.addHandler(
            file_handler
        )

    return logger


app_logger = build_logger(
    "app_logger",
    "app.log"
)

security_logger = build_logger(
    "security_logger",
    "security.log"
)

performance_logger = build_logger(
    "performance_logger",
    "performance.log"
)

ai_logger = build_logger(
    "ai_logger",
    "ai.log"
)

upload_logger = build_logger(
    "upload_logger",
    "uploads.log"
)

auth_logger = build_logger(
    "auth_logger",
    "auth.log"
)

error_logger = build_logger(
    "error_logger",
    "errors.log"
)

access_logger = build_logger(
    "access_logger",
    "access.log"
) 