from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from app.services.xlsx_writer import XlsxTotal, build_xlsx


def test_build_xlsx_reserves_default_fills_before_custom_total_fill() -> None:
    content = build_xlsx(
        [("Отчет", [["Заголовок"], [XlsxTotal("Итого")]])]
    )

    with ZipFile(BytesIO(content)) as workbook:
        styles = ElementTree.fromstring(workbook.read("xl/styles.xml"))

    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    fills = styles.find("x:fills", namespace)
    assert fills is not None
    pattern_types = [
        pattern.attrib["patternType"]
        for pattern in fills.findall("x:fill/x:patternFill", namespace)
    ]
    assert pattern_types == ["none", "gray125", "solid"]

    cell_xfs = styles.find("x:cellXfs", namespace)
    assert cell_xfs is not None
    assert [item.attrib["fillId"] for item in cell_xfs.findall("x:xf", namespace)] == [
        "0",
        "0",
        "0",
        "2",
        "2",
    ]
