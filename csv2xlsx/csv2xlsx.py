#!/usr/bin/env python3
"""csv2xlsx - turn a CSV into a real .xlsx without Excel's encoding and
delimiter guesswork. Standard library only.

Exit codes: 0 = ok, 1 = output not written (exists / limits), 2 = bad input.
"""
import argparse
import codecs
import csv
import io
import os
import re
import sys
import zipfile
from xml.sax.saxutils import escape

__version__ = "0.1.0"

MAX_ROWS = 1_048_576
MAX_COLS = 16_384
MAX_CELL = 32_767
DELIMS = [",", ";", "\t", "|"]
ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Plain numbers only: leading zeros ("007") and 16+ digits stay text so
# ids, phone numbers and card-like values are not mangled.
INT_RE = re.compile(r"^-?(0|[1-9]\d*)$")
DEC_RE = re.compile(r"^-?(0|[1-9]\d*)\.\d+$")


class CsvError(Exception):
    pass


def decode(raw, forced=None):
    """Return (text, encoding_name)."""
    if forced:
        try:
            return raw.decode(forced), forced
        except (UnicodeDecodeError, LookupError) as e:
            raise CsvError(f"cannot decode as {forced}: {e}")
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8"), "utf-8-sig"
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    # Excel on Windows saves "CSV" as cp1252; latin-1 never fails.
    try:
        return raw.decode("cp1252"), "cp1252"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def detect_delimiter(text):
    """Pick the delimiter giving the most consistent multi-column rows."""
    sample = io.StringIO("\n".join(text.splitlines()[:50]))
    best, best_key = ",", (0.0, 0)
    for d in DELIMS:
        sample.seek(0)
        counts = [len(r) for r in csv.reader(sample, delimiter=d) if r]
        if not counts:
            continue
        modal = max(set(counts), key=counts.count)
        if modal < 2:
            continue
        key = (counts.count(modal) / len(counts), modal)
        if key > best_key:
            best, best_key = d, key
    return best


def parse_rows(text, delimiter):
    try:
        rows = [r for r in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)]
    except csv.Error as e:
        raise CsvError(f"malformed CSV: {e}")
    # drop fully blank trailing rows
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    return rows


def col_letter(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def cell_number(value, decimal):
    """Return a numeric string for the cell, or None to keep it as text."""
    v = value.strip()
    if decimal == ",":
        v = v.replace(",", ".") if v.count(",") == 1 and "." not in v else v
    if INT_RE.match(v):
        return v if len(v.lstrip("-")) <= 15 else None
    if DEC_RE.match(v):
        return v if len(v.replace("-", "").replace(".", "")) <= 15 else None
    return None


def build_sheet(rows, decimal, header_style):
    ncols = max(len(r) for r in rows)
    widths = [0] * ncols
    truncated = 0
    out = []
    for ri, row in enumerate(rows):
        cells = []
        for ci, value in enumerate(row):
            if value == "":
                continue
            ref = f"{col_letter(ci)}{ri + 1}"
            if ri < 200:
                widths[ci] = max(widths[ci], min(len(value), 60))
            num = None if (ri == 0 and header_style) else cell_number(value, decimal)
            style = ' s="1"' if (ri == 0 and header_style) else ""
            if num is not None:
                cells.append(f'<c r="{ref}"{style}><v>{num}</v></c>')
                continue
            if len(value) > MAX_CELL:
                value = value[:MAX_CELL]
                truncated += 1
            value = escape(ILLEGAL_XML.sub("", value))
            cells.append(
                f'<c r="{ref}"{style} t="inlineStr"><is><t xml:space="preserve">{value}</t></is></c>'
            )
        out.append(f'<row r="{ri + 1}">{"".join(cells)}</row>')
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{w + 2}" customWidth="1"/>'
        for i, w in enumerate(widths)
        if w
    )
    pane = ""
    if header_style and len(rows) > 1:
        pane = ('<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>')
    cols_xml = f"<cols>{cols}</cols>" if cols else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>'
        f'{cols_xml}<sheetData>{"".join(out)}</sheetData></worksheet>'
    )
    return xml, truncated


CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)
STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    "</styleSheet>"
)


def sheet_name(path):
    name = re.sub(r"[\[\]:*?/\\]", "_", os.path.splitext(os.path.basename(path))[0])
    return (name or "Sheet1")[:31]


def write_xlsx(path, rows, name, decimal=".", header_style=True):
    if len(rows) > MAX_ROWS:
        raise CsvError(f"{len(rows)} rows exceeds Excel's limit of {MAX_ROWS}")
    if max(len(r) for r in rows) > MAX_COLS:
        raise CsvError(f"too many columns for Excel (limit {MAX_COLS})")
    sheet, truncated = build_sheet(rows, decimal, header_style)
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        z.writestr("xl/styles.xml", STYLES)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return truncated


def build_parser():
    p = argparse.ArgumentParser(
        prog="csv2xlsx",
        description="Convert CSV to .xlsx, auto-detecting encoding and delimiter.",
    )
    p.add_argument("input", help="CSV file to convert")
    p.add_argument("-o", "--output", help="output path (default: input with .xlsx)")
    p.add_argument("--delimiter", help="force delimiter, e.g. ';' (default: detect)")
    p.add_argument("--encoding", help="force input encoding, e.g. cp1252 (default: detect)")
    p.add_argument("--decimal", choices=[".", ","], default=".",
                   help="decimal mark used in the data (default: '.')")
    p.add_argument("--no-header-style", action="store_true",
                   help="do not bold or freeze the first row")
    p.add_argument("--force", action="store_true", help="overwrite existing output")
    p.add_argument("--version", action="version", version=f"csv2xlsx {__version__}")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    out = args.output or os.path.splitext(args.input)[0] + ".xlsx"
    try:
        with open(args.input, "rb") as f:
            raw = f.read()
    except OSError as e:
        print(f"csv2xlsx: cannot read {args.input}: {e.strerror}", file=sys.stderr)
        return 2
    if not raw.strip():
        print(f"csv2xlsx: {args.input} is empty", file=sys.stderr)
        return 2
    if args.delimiter is not None and len(args.delimiter.replace("\\t", "\t")) != 1:
        print("csv2xlsx: --delimiter must be a single character", file=sys.stderr)
        return 2
    try:
        text, enc = decode(raw, args.encoding)
        delim = args.delimiter.replace("\\t", "\t") if args.delimiter else detect_delimiter(text)
        rows = parse_rows(text, delim)
        if not rows:
            raise CsvError("no rows found")
        if os.path.exists(out) and not args.force:
            print(f"csv2xlsx: {out} exists (use --force to overwrite)", file=sys.stderr)
            return 1
        truncated = write_xlsx(out, rows, sheet_name(out), args.decimal,
                               not args.no_header_style)
    except CsvError as e:
        print(f"csv2xlsx: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"csv2xlsx: cannot write {out}: {e.strerror}", file=sys.stderr)
        return 1
    shown = "tab" if delim == "\t" else delim
    print(f"read as {enc}, delimiter '{shown}', {len(rows)} rows x "
          f"{max(len(r) for r in rows)} cols -> {out}")
    if truncated:
        print(f"csv2xlsx: warning: {truncated} cell(s) cut to {MAX_CELL} chars",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
