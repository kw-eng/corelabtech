from __future__ import annotations

import html
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "WIEDZA_PROJEKT_QA.txt"
OUTPUT = ROOT / "WIEDZA_PROJEKT_QA.epub"
TITLE = "CoreLabTech - Podrecznik projektu i plan nauki"
LANGUAGE = "pl"


def clean_text(value: str) -> str:
    value = value.rstrip("\n")
    value = value.replace("\t", "    ")
    return "".join(ch for ch in value if ch in "\t\n\r" or ord(ch) >= 32)


def esc(value: str) -> str:
    return html.escape(clean_text(value), quote=True)


def classify_heading(lines: list[str], index: int) -> tuple[int, str] | None:
    current = lines[index].strip()
    next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
    if current and set(next_line) == {"="} and len(next_line) >= 3:
        return 1, current
    if current and set(next_line) == {"-"} and len(next_line) >= 3:
        return 2, current
    if re.match(r"^\d+\.\s+[A-Z0-9].+", current):
        return 1, current
    if re.match(r"^\d+\.\d+\s+.+", current):
        return 2, current
    if re.match(r"^\d+\.\d+\.\d+\s+.+", current):
        return 3, current
    return None


def slugify(text: str, used: set[str]) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:70] or "section"
    base = slug
    suffix = 2
    while slug in used:
        slug = f"{base}-{suffix}"
        suffix += 1
    used.add(slug)
    return slug


def collect_headings(lines: list[str]) -> list[tuple[int, str, str]]:
    headings: list[tuple[int, str, str]] = []
    used: set[str] = set()
    skip = False
    for index in range(len(lines)):
        if skip:
            skip = False
            continue
        heading = classify_heading(lines, index)
        if not heading:
            continue
        level, text = heading
        headings.append((level, text, slugify(text, used)))
        if index + 1 < len(lines) and set(lines[index + 1].strip()) in ({"="}, {"-"}):
            skip = True
    return headings


def build_content(lines: list[str], headings: list[tuple[int, str, str]]) -> str:
    body: list[str] = []
    heading_iter = iter(headings)
    next_heading = next(heading_iter, None)
    in_code = False
    in_ul = False
    skip_next_underline = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            body.append("</ul>")
            in_ul = False

    for index, line in enumerate(lines):
        text = clean_text(line)
        stripped = text.strip()

        if skip_next_underline:
            skip_next_underline = False
            continue

        if stripped.startswith("```"):
            close_ul()
            if in_code:
                body.append("</code></pre>")
            else:
                body.append("<pre><code>")
            in_code = not in_code
            continue

        if in_code:
            body.append(esc(text))
            continue

        heading = classify_heading(lines, index)
        if heading and next_heading:
            close_ul()
            level, title = heading
            _, _, heading_id = next_heading
            level = min(max(level, 1), 3)
            body.append(f'<h{level} id="{heading_id}">{esc(title)}</h{level}>')
            next_heading = next(heading_iter, None)
            if index + 1 < len(lines) and set(lines[index + 1].strip()) in ({"="}, {"-"}):
                skip_next_underline = True
            continue

        if not stripped:
            close_ul()
            continue

        bullet = re.match(r"^[-*]\s+(.+)", stripped)
        if bullet:
            if not in_ul:
                body.append("<ul>")
                in_ul = True
            body.append(f"<li>{esc(bullet.group(1))}</li>")
            continue

        close_ul()
        body.append(f"<p>{esc(stripped)}</p>")

    close_ul()
    if in_code:
        body.append("</code></pre>")

    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="pl" lang="pl">
<head>
  <meta charset="UTF-8" />
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="styles.css" />
</head>
<body>
  <section class="cover">
    <h1>{title}</h1>
    <p>Wersja EPUB wygenerowana z WIEDZA_PROJEKT_QA.txt</p>
    <p>Data wygenerowania: {date}</p>
  </section>
  {body}
</body>
</html>
""".format(
        title=esc(TITLE),
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        body="\n  ".join(body),
    )


def build_nav(headings: list[tuple[int, str, str]]) -> str:
    items = "\n".join(
        f'      <li class="level-{level}"><a href="content.xhtml#{heading_id}">{esc(title)}</a></li>'
        for level, title, heading_id in headings[:300]
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="pl" lang="pl">
<head>
  <meta charset="UTF-8" />
  <title>Spis tresci</title>
  <link rel="stylesheet" type="text/css" href="styles.css" />
</head>
<body>
  <nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops" id="toc">
    <h1>Spis tresci</h1>
    <ol>
{items}
    </ol>
  </nav>
</body>
</html>
"""


def styles_css() -> str:
    return """
body {
  color: #0f172a;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  line-height: 1.55;
  margin: 0;
  padding: 1.5rem;
}
h1, h2, h3 {
  color: #0b4f8a;
  line-height: 1.2;
  margin: 1.8rem 0 0.7rem;
}
h1 { font-size: 1.7rem; }
h2 { font-size: 1.35rem; }
h3 { font-size: 1.15rem; }
p, li { font-size: 1rem; }
ul { padding-left: 1.4rem; }
pre {
  background: #f3f6fb;
  border: 1px solid #d8e0ec;
  border-radius: 6px;
  overflow-x: auto;
  padding: 0.85rem;
}
code {
  font-family: Consolas, "SFMono-Regular", monospace;
  font-size: 0.9rem;
}
.cover {
  border-bottom: 2px solid #0b4f8a;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
}
.level-2 { margin-left: 1rem; }
.level-3 { margin-left: 2rem; }
"""


def package_opf(identifier: str, modified: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:{identifier}</dc:identifier>
    <dc:title>{esc(TITLE)}</dc:title>
    <dc:language>{LANGUAGE}</dc:language>
    <dc:creator>Codex</dc:creator>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="content" href="content.xhtml" media-type="application/xhtml+xml"/>
    <item id="style" href="styles.css" media-type="text/css"/>
  </manifest>
  <spine>
    <itemref idref="content"/>
  </spine>
</package>
"""


def write_epub() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines()
    headings = collect_headings(lines)
    identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{TITLE}:{SOURCE.stat().st_mtime_ns}"))
    modified = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    files = {
        "META-INF/container.xml": """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        "EPUB/package.opf": package_opf(identifier, modified),
        "EPUB/nav.xhtml": build_nav(headings),
        "EPUB/content.xhtml": build_content(lines, headings),
        "EPUB/styles.css": styles_css(),
    }

    with zipfile.ZipFile(OUTPUT, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, content in files.items():
            epub.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)


def validate_epub() -> None:
    required = {
        "mimetype",
        "META-INF/container.xml",
        "EPUB/package.opf",
        "EPUB/nav.xhtml",
        "EPUB/content.xhtml",
        "EPUB/styles.css",
    }
    with zipfile.ZipFile(OUTPUT) as epub:
        names = set(epub.namelist())
        missing = required - names
        if missing:
            raise RuntimeError(f"Missing EPUB parts: {sorted(missing)}")
        first = epub.infolist()[0]
        if first.filename != "mimetype" or first.compress_type != zipfile.ZIP_STORED:
            raise RuntimeError("EPUB mimetype must be first and uncompressed")
        if epub.read("mimetype").decode("ascii") != "application/epub+zip":
            raise RuntimeError("Invalid EPUB mimetype")
        for name in ["META-INF/container.xml", "EPUB/package.opf", "EPUB/nav.xhtml", "EPUB/content.xhtml"]:
            ET.fromstring(epub.read(name))


if __name__ == "__main__":
    write_epub()
    validate_epub()
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Created {OUTPUT} ({size_kb:.1f} KB)")
