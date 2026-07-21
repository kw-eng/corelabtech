from __future__ import annotations

import html
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "WIEDZA_PROJEKT_QA.txt"
OUTPUT = ROOT / "WIEDZA_PROJEKT_QA.docx"


def clean_text(value: str) -> str:
    value = value.rstrip("\n")
    value = value.replace("\t", "    ")
    return "".join(ch for ch in value if ch == "\t" or ch == "\n" or ch == "\r" or ord(ch) >= 32)


def esc(value: str) -> str:
    return html.escape(clean_text(value), quote=False)


def run_xml(text: str, *, bold: bool = False, italic: bool = False, color: str | None = None, size: int | None = None, font: str | None = None) -> str:
    props: list[str] = []
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if color:
        props.append(f'<w:color w:val="{color}"/>')
    if size:
        props.append(f'<w:sz w:val="{size * 2}"/>')
    if font:
        props.append(f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    space = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    return f"<w:r>{rpr}<w:t{space}>{esc(text)}</w:t></w:r>"


def paragraph_xml(
    text: str = "",
    *,
    style: str | None = None,
    num_id: int | None = None,
    ilvl: int = 0,
    runs: list[str] | None = None,
    keep_next: bool = False,
) -> str:
    ppr: list[str] = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if keep_next:
        ppr.append("<w:keepNext/>")
    if num_id is not None:
        ppr.append(f"<w:numPr><w:ilvl w:val=\"{ilvl}\"/><w:numId w:val=\"{num_id}\"/></w:numPr>")
    ppr_xml = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
    content = "".join(runs) if runs is not None else run_xml(text)
    return f"<w:p>{ppr_xml}{content}</w:p>"


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


def toc_entries(lines: list[str]) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    skip = False
    for idx in range(len(lines)):
        if skip:
            skip = False
            continue
        heading = classify_heading(lines, idx)
        if not heading:
            continue
        level, text = heading
        entries.append((level, text))
        if idx + 1 < len(lines) and set(lines[idx + 1].strip()) in ({"="}, {"-"}):
            skip = True
    return entries


def build_document_xml(source_text: str) -> str:
    raw_lines = source_text.splitlines()
    body: list[str] = []

    body.append(paragraph_xml("CoreLabTech - Podrecznik projektu i plan nauki", style="DocTitle"))
    body.append(paragraph_xml("Wersja Word wygenerowana z WIEDZA_PROJEKT_QA.txt", style="Subtitle"))
    body.append(paragraph_xml(f"Data wygenerowania: {datetime.now().strftime('%Y-%m-%d %H:%M')}", style="Muted"))
    body.append(paragraph_xml("Spis tresci", style="Heading1"))

    for level, title in toc_entries(raw_lines)[:240]:
        style = "TOC1" if level == 1 else "TOC2"
        body.append(paragraph_xml(title, style=style))

    body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    in_code = False
    skip_next_underline = False

    for idx, line in enumerate(raw_lines):
        text = clean_text(line)
        stripped = text.strip()

        if skip_next_underline:
            skip_next_underline = False
            continue

        heading = classify_heading(raw_lines, idx)
        if heading:
            level, title = heading
            style = "Heading1" if level == 1 else "Heading2" if level == 2 else "Heading3"
            body.append(paragraph_xml(title, style=style, keep_next=True))
            if idx + 1 < len(raw_lines) and set(raw_lines[idx + 1].strip()) in ({"="}, {"-"}):
                skip_next_underline = True
            continue

        if stripped.startswith("```"):
            in_code = not in_code
            continue

        if not stripped:
            body.append(paragraph_xml(""))
            continue

        if in_code:
            body.append(paragraph_xml(text, style="CodeBlock"))
            continue

        if stripped.startswith("Q:"):
            body.append(paragraph_xml(stripped, style="Question"))
            continue

        if stripped.startswith("A:"):
            body.append(paragraph_xml(stripped, style="Answer"))
            continue

        bullet_match = re.match(r"^[-*]\s+(.+)", stripped)
        if bullet_match:
            body.append(paragraph_xml(bullet_match.group(1), num_id=1))
            continue

        number_match = re.match(r"^\d+\.\s+(.+)", stripped)
        if number_match:
            body.append(paragraph_xml(number_match.group(1), num_id=2))
            continue

        body.append(paragraph_xml(stripped))

    section = (
        "<w:sectPr>"
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<w:body>{''.join(body)}{section}</w:body></w:document>"
    )


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="120" w:line="300" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="DocTitle"><w:name w:val="Document Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="180"/></w:pPr><w:rPr><w:b/><w:color w:val="0B2545"/><w:sz w:val="40"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="120"/></w:pPr><w:rPr><w:color w:val="555555"/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Muted"><w:name w:val="Muted"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:color w:val="666666"/><w:sz w:val="20"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/><w:spacing w:before="360" w:after="200"/></w:pPr><w:rPr><w:b/><w:color w:val="2E74B5"/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="1"/><w:spacing w:before="280" w:after="140"/></w:pPr><w:rPr><w:b/><w:color w:val="2E74B5"/><w:sz w:val="26"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:outlineLvl w:val="2"/><w:spacing w:before="200" w:after="100"/></w:pPr><w:rPr><w:b/><w:color w:val="1F4D78"/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Question"><w:name w:val="Question"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="120" w:after="80"/></w:pPr><w:rPr><w:b/><w:color w:val="0B2545"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Answer"><w:name w:val="Answer"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="120"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="CodeBlock"><w:name w:val="Code Block"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="40" w:after="40" w:line="260" w:lineRule="auto"/><w:ind w:left="240"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/><w:color w:val="333333"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="TOC 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="40"/></w:pPr><w:rPr><w:b/><w:color w:val="0B2545"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TOC2"><w:name w:val="TOC 2"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360"/><w:spacing w:after="20"/></w:pPr><w:rPr><w:color w:val="444444"/><w:sz w:val="20"/></w:rPr></w:style>
</w:styles>"""


def numbering_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="singleLevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="540"/></w:tabs><w:ind w:left="540" w:hanging="270"/></w:pPr></w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:multiLevelType w:val="singleLevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:lvlJc w:val="left"/><w:pPr><w:tabs><w:tab w:val="num" w:pos="540"/></w:tabs><w:ind w:left="540" w:hanging="270"/></w:pPr></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>"""


def write_docx() -> None:
    source_text = SOURCE.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>""",
        "word/_rels/document.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
</Relationships>""",
        "word/document.xml": build_document_xml(source_text),
        "word/styles.xml": styles_xml(),
        "word/numbering.xml": numbering_xml(),
        "word/settings.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/></w:settings>""",
        "docProps/core.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>CoreLabTech - Podrecznik projektu i plan nauki</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>""",
        "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Codex</Application></Properties>""",
    }

    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        for name, content in files.items():
            docx.writestr(name, content)


def validate_docx() -> None:
    required = {
        "[Content_Types].xml",
        "_rels/.rels",
        "word/document.xml",
        "word/styles.xml",
        "word/numbering.xml",
        "word/settings.xml",
        "word/_rels/document.xml.rels",
        "docProps/core.xml",
        "docProps/app.xml",
    }
    with zipfile.ZipFile(OUTPUT) as docx:
        names = set(docx.namelist())
        missing = required - names
        if missing:
            raise RuntimeError(f"Missing DOCX parts: {sorted(missing)}")
        for name in required:
            ET.fromstring(docx.read(name))


if __name__ == "__main__":
    write_docx()
    validate_docx()
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Created {OUTPUT} ({size_kb:.1f} KB)")
