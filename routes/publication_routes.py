from pathlib import Path

from flask import Blueprint, render_template, send_from_directory


pub_bp = Blueprint("pub", __name__)

PAPERS_DIR = Path("research/papers")
VISIBLE_PUBLICATION_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
}


@pub_bp.route("/publications")
def publications():
    papers = []

    if PAPERS_DIR.exists():
        for path in sorted(PAPERS_DIR.iterdir(), key=lambda item: item.name.lower()):
            if (
                not path.is_file()
                or path.name.startswith(".")
                or path.suffix.lower() not in VISIBLE_PUBLICATION_EXTENSIONS
            ):
                continue

            stat = path.stat()
            papers.append({
                "filename": path.name,
                "title": path.stem.replace("_", " ").replace("-", " ").title(),
                "extension": path.suffix.lower().lstrip(".").upper(),
                "size_kb": max(1, round(stat.st_size / 1024)),
                "updated_at": stat.st_mtime,
            })

    return render_template(
        "publications.html",
        papers=papers,
    )


@pub_bp.route("/publications/download/<filename>")
def download_publication(filename):
    return send_from_directory(
        PAPERS_DIR,
        filename,
        as_attachment=True,
    )


@pub_bp.route("/research/datasets")
def datasets():
    return render_template("datasets.html")


@pub_bp.route("/research/reports")
def reports():
    return render_template("reports.html")
