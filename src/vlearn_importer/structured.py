"""Read bounded VLearn templates into rows with source positions."""

import csv
import io
import json
import math
import re
from importlib.resources import files
from zipfile import ZipFile

from defusedxml import ElementTree
from docx import Document
from openpyxl import load_workbook

CONTRACT = json.loads(files("vlearn_importer").joinpath("import-formats.json").read_bytes())
MAX_FILE_BYTES = CONTRACT["maxFileBytes"]
MAX_ROWS = CONTRACT["maxRows"]
MAX_CELL_CHARS = 20_000
MAX_RESULT_BYTES = 1024 * 1024
MAX_INFLATED_BYTES = 30 * 1024 * 1024
MAX_ARCHIVE_FILES = 512
MAX_XML_ELEMENTS = 100_000


class ParseError(ValueError):
    """An import validation error safe to display to a learner."""


def json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def csv_rows(source):
    with io.TextIOWrapper(io.BytesIO(source), encoding="utf-8-sig", newline="") as text:
        reader = csv.reader(text, strict=True)
        while True:
            number = reader.line_num + 1
            cells = next(reader, None)
            if cells is None:
                return
            if number == 1 or cells:
                yield number, cells


def inspect_package(source, extension, column_count):
    """Validate ZIP metadata and XML before loading an Office document."""
    with ZipFile(io.BytesIO(source)) as archive:
        entries = archive.infolist()
        if (
            len(entries) > MAX_ARCHIVE_FILES
            or sum(entry.file_size for entry in entries) > MAX_INFLATED_BYTES
            or len({entry.filename.casefold() for entry in entries}) != len(entries)
        ):
            raise ParseError("Tệp Office vượt giới hạn giải nén hoặc có mục trùng lặp.")
        remaining_elements = MAX_XML_ELEMENTS
        for entry in entries:
            name = entry.filename.casefold()
            if entry.flag_bits & 1 or "vbaproject" in name or "/externallinks/" in name:
                raise ParseError("Tệp Office chứa nội dung mã hóa, macro hoặc liên kết ngoài.")
            if name.endswith((".xml", ".rels")):
                with archive.open(entry) as stream:
                    nodes = ElementTree.iterparse(
                        stream, events=("start",),
                        forbid_dtd=True, forbid_entities=True, forbid_external=True,
                    )
                    for _ in nodes:
                        if remaining_elements == 0:
                            raise ParseError("Tệp Office có cấu trúc XML quá lớn.")
                        remaining_elements -= 1
                    root = nodes.root
                if name.endswith(".rels"):
                    if any(item.get("TargetMode", "").lower() == "external" for item in root):
                        raise ParseError("Tệp Office chứa liên kết ngoài.")
                if name == "[content_types].xml":
                    if any("macroenabled" in item.get("ContentType", "").lower() for item in root):
                        raise ParseError("Tệp Office chứa macro.")
                if extension == ".xlsx":
                    inspect_worksheet(root, column_count)
            else:
                # Reading all entries checks CRCs even for parts unused by the parser.
                archive.read(entry)


def inspect_worksheet(root, column_count):
    from openpyxl.utils.cell import column_index_from_string

    prefix = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    if root.tag != f"{prefix}worksheet":
        return
    previous_row = 0
    for node in root.iter():
        if node.tag in {f"{prefix}mergeCell", f"{prefix}f"}:
            raise ParseError("Bảng tính chứa ô gộp hoặc công thức.")
        if node.tag == f"{prefix}row":
            number = int(node.get("r", "0"))
            if not previous_row < number <= MAX_ROWS + 1:
                raise ParseError("Bảng tính có vị trí dòng không hợp lệ hoặc vượt giới hạn 200 dòng.")
            previous_row = number
            previous_column = 0
            for cell in node.findall(f"{prefix}c"):
                match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", cell.get("r", ""))
                if not match or int(match[2]) != number:
                    raise ParseError("Bảng tính có địa chỉ ô không hợp lệ.")
                column = column_index_from_string(match[1])
                if not previous_column < column <= column_count:
                    raise ParseError("Bảng tính có cột thừa hoặc bị trùng.")
                previous_column = column


def xlsx_rows(source, column_count):
    workbook = load_workbook(io.BytesIO(source), read_only=True, data_only=False, keep_links=False)
    try:
        if len(workbook.sheetnames) != 1 or len(workbook.worksheets) != 1:
            raise ParseError("Tệp Excel phải chứa đúng một bảng tính.")
        sheet = workbook.worksheets[0]
        for number, row in enumerate(sheet.iter_rows(max_col=column_count, max_row=MAX_ROWS + 1), 1):
            cells = []
            for cell in row:
                value = cell.value
                if value is None:
                    cells.append("")
                elif isinstance(value, str) and cell.data_type in ("s", "inlineStr"):
                    cells.append(value)
                elif type(value) in (int, float) and math.isfinite(value):
                    cells.append(str(value))
                else:
                    raise ParseError(f"Dòng {number} chứa ô không phải văn bản hoặc số.")
            yield number, cells
    finally:
        workbook.close()


def docx_rows(source, column_count):
    document = Document(io.BytesIO(source))
    if len(document.tables) != 1 or len(document.element.xpath(".//w:tbl")) != 1:
        raise ParseError("Tệp Word phải chứa đúng một bảng và không có bảng lồng nhau.")
    table = document.tables[0]
    if len(table.rows) > MAX_ROWS + 1:
        raise ParseError("Bảng Word vượt giới hạn 200 dòng dữ liệu.")
    if len(table.columns) != column_count:
        raise ParseError("Bảng Word có số cột không đúng mẫu.")
    if table._tbl.xpath(
        ".//w:gridSpan|.//w:vMerge|.//w:hMerge|.//w:fldSimple|.//w:fldChar"
        "|.//w:ins|.//w:del|.//w:sdt|.//w:moveFrom|.//w:moveTo|.//w:altChunk"
    ):
        raise ParseError("Bảng Word chứa ô gộp, trường tự động hoặc nội dung chưa hoàn tất.")
    for number, row in enumerate(table.rows, 1):
        if row.grid_cols_before or row.grid_cols_after:
            raise ParseError(f"Dòng {number} trong bảng Word có ô bị thiếu.")
        yield number, [cell.text for cell in row.cells]


def normalize_rows(rows, columns):
    header = next(rows, None)
    if header is None or header[0] != 1 or sorted(header[1]) != sorted(columns):
        raise ParseError("Tiêu đề phải chứa đủ tên cột và mỗi tên cột chỉ xuất hiện một lần.")
    headers = header[1]
    result = []
    # Include the envelope, array delimiters and row separators in the bound.
    result_size = len(b'{"rows":[]}')
    for number, cells in rows:
        if len(cells) != len(headers):
            raise ParseError(f"Dòng {number} có số cột không đúng mẫu.")
        if any(len(cell.encode("utf-16-le")) // 2 > MAX_CELL_CHARS or "\0" in cell for cell in cells):
            raise ParseError(f"Dòng {number} chứa ô quá dài hoặc ký tự không hợp lệ.")
        if not any(cell.strip() for cell in cells):
            continue
        if len(result) == MAX_ROWS:
            raise ParseError(f"Mỗi tệp chỉ được chứa tối đa {MAX_ROWS} dòng dữ liệu.")
        mapped = dict(zip(headers, cells, strict=True))
        record = {"row": number, "values": {column: mapped[column] for column in columns}}
        result_size += len(json_bytes(record)) + bool(result)
        if result_size > MAX_RESULT_BYTES:
            raise ParseError("Dữ liệu sau khi đọc vượt giới hạn 1 MiB.")
        result.append(record)
    if not result:
        raise ParseError("Tệp mẫu không có dòng dữ liệu.")
    return result


def parse_bytes(source: bytes, extension: str, kind: str) -> list[dict]:
    if kind not in CONTRACT["kinds"]:
        raise ParseError("Loại nội dung không hợp lệ.")
    if not 0 < len(source) <= MAX_FILE_BYTES:
        raise ParseError("Tệp phải có dữ liệu và không lớn hơn 5 MiB.")
    columns = CONTRACT["kinds"][kind]["columns"]
    extension = extension.lower()
    try:
        if extension == ".csv":
            return normalize_rows(csv_rows(source), columns)
        if extension == ".xlsx":
            inspect_package(source, extension, len(columns))
            return normalize_rows(xlsx_rows(source, len(columns)), columns)
        if extension == ".docx":
            inspect_package(source, extension, len(columns))
            return normalize_rows(docx_rows(source, len(columns)), columns)
    except ParseError:
        raise
    except Exception:
        raise ParseError("Không thể đọc tệp. Hãy kiểm tra định dạng và thử lại.") from None
    raise ParseError("Định dạng tệp chưa được hỗ trợ.")
