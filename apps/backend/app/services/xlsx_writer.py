from __future__ import annotations

from collections.abc import Sequence
from html import escape
from io import BytesIO
from math import isfinite
from zipfile import ZIP_DEFLATED, ZipFile

CellValue = str | int | float | None
SheetRows = Sequence[Sequence[CellValue]]


def build_xlsx(sheets: Sequence[tuple[str, SheetRows]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(len(sheets)))
        archive.writestr("_rels/.rels", _root_relationships())
        archive.writestr("xl/workbook.xml", _workbook(sheets))
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            _workbook_relationships(len(sheets)),
        )
        archive.writestr("xl/styles.xml", _styles())
        for index, (_, rows) in enumerate(sheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _worksheet(rows),
            )
    return buffer.getvalue()


def _content_types(sheets_count: int) -> str:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheets_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.styles+xml"/>'
        f"{sheet_overrides}</Types>"
    )


def _root_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook(sheets: Sequence[tuple[str, SheetRows]]) -> str:
    sheet_items = "".join(
        f'<sheet name="{_xml_attr(_sheet_name(name))}" sheetId="{index}" '
        f'r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships">'
        f"<sheets>{sheet_items}</sheets>"
        "</workbook>"
    )


def _workbook_relationships(sheets_count: int) -> str:
    sheet_relationships = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        f'relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheets_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        f"{sheet_relationships}"
        f'<Relationship Id="rId{sheets_count + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def _styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" '
        'borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" '
        'borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" '
        'applyFont="1"/></cellXfs>'
        "</styleSheet>"
    )


def _worksheet(rows: SheetRows) -> str:
    row_items = "".join(
        f'<row r="{row_index}">{_cells(row, row_index)}</row>'
        for row_index, row in enumerate(rows, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{row_items}</sheetData>"
        "</worksheet>"
    )


def _cells(row: Sequence[CellValue], row_index: int) -> str:
    return "".join(
        _cell(value, _cell_reference(column_index, row_index), is_header=row_index == 1)
        for column_index, value in enumerate(row, start=1)
    )


def _cell(value: CellValue, reference: str, *, is_header: bool) -> str:
    style = ' s="1"' if is_header else ""
    if value is None:
        return f'<c r="{reference}"{style}/>'
    if isinstance(value, int):
        return f'<c r="{reference}"{style}><v>{value}</v></c>'
    if isinstance(value, float) and isfinite(value):
        return f'<c r="{reference}"{style}><v>{value:.6f}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr"{style}>'
        f"<is><t>{_xml_text(str(value))}</t></is></c>"
    )


def _cell_reference(column_index: int, row_index: int) -> str:
    letters = ""
    current = column_index
    while current:
        current, remainder = divmod(current - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row_index}"


def _sheet_name(value: str) -> str:
    forbidden = set("[]:*?/\\")
    normalized = "".join("_" if char in forbidden else char for char in value).strip()
    return (normalized or "Лист")[:31]


def _xml_text(value: str) -> str:
    return escape(value, quote=False)


def _xml_attr(value: str) -> str:
    return escape(value, quote=True)
