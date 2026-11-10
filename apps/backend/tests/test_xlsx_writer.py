from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from app.services.xlsx_writer import XlsxTotal, build_xlsx


def test_build_xlsx_reserves_default_fills_before_custom_total_fill() -> None:
    """
    Проверяем оформление итогов XLSX:
    - сохранить обязательные стандартные заливки Excel
    - применить голубую заливку к обычным итогам и серую к общим
    - проверять стиль ячейки без ограничения числа доступных стилей
    """
    content = build_xlsx(
        [("Отчет", [["Заголовок"], [XlsxTotal("Итого")], [XlsxTotal(10, gray=True)]])]
    )

    with ZipFile(BytesIO(content)) as workbook:
        styles = ElementTree.fromstring(workbook.read("xl/styles.xml"))
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    fills = styles.findall("x:fills/x:fill/x:patternFill", namespace)
    assert [fill.attrib["patternType"] for fill in fills[:2]] == ["none", "gray125"]
    cell_styles = styles.findall("x:cellXfs/x:xf", namespace)
    for address, expected_color in [("A2", "FFDCEAF5"), ("A3", "FFE5E7EB")]:
        cell = sheet.find(f".//x:c[@r='{address}']", namespace)
        assert cell is not None
        cell_style = cell_styles[int(cell.attrib["s"])]
        fill = fills[int(cell_style.attrib["fillId"])]
        assert fill.attrib["patternType"] == "solid"
        color = fill.find("x:fgColor", namespace)
        assert color is not None and color.attrib["rgb"] == expected_color
