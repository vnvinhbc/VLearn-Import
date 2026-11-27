"""Generate editable example files using the shared template contract."""

import csv
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Inches, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from vlearn_importer.structured import CONTRACT

SAMPLES = {
    "TOEIC": {
        "group_key": "example-part-5",
        "part": "5",
        "title": "Part 5 — Office notices",
        "question": "All visitors must ___ in at the front desk.",
        "option_a": "sign",
        "option_b": "signs",
        "option_c": "signed",
        "option_d": "signing",
        "correct_answer": "A",
        "explanation": "Dùng động từ nguyên mẫu sau must.",
        "difficulty": "EASY",
    },
    "VOCABULARY": {
        "term": "office",
        "meaning": "văn phòng",
        "part_of_speech": "noun",
        "ipa": "/ˈɑːfɪs/",
        "example": "She works in the main office.",
        "example_translation": "Cô ấy làm việc ở văn phòng chính.",
        "topic": "Workplace",
        "difficulty": "EASY",
    },
    "GRAMMAR": {
        "title": "Thì hiện tại đơn",
        "topic": "Verb tenses",
        "explanation": "Dùng thì hiện tại đơn để nói về thói quen hoặc sự thật.",
        "structure": "S + V(s/es)",
        "examples": "I work every morning.\nShe works every morning.",
        "common_mistakes": "Thêm -s hoặc -es khi chủ ngữ là ngôi thứ ba số ít.",
        "question": "The office ___ at 8 a.m. every day.",
        "option_a": "open",
        "option_b": "opens",
        "option_c": "opening",
        "option_d": "to open",
        "correct_answer": "B",
        "question_explanation": "The office là chủ ngữ số ít nên dùng opens.",
        "difficulty": "EASY",
    },
}


def write_excel(path, columns, values):
    book = Workbook()
    sheet = book.active
    sheet.title = "VLearn"
    sheet.freeze_panes = "A2"
    sheet.append(columns)
    sheet.append(values)
    for heading in sheet[1]:
        heading.font = Font(bold=True)
        sheet.column_dimensions[heading.column_letter].width = max(17, len(heading.value) + 3)
    for cell in sheet[2]:
        cell.alignment = Alignment(vertical="top", wrap_text=True)
    book.save(path)
    book.close()


def write_word(path, columns, values):
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Inches(16.54 if len(columns) > 10 else 11.69)
    section.page_height = Inches(11.69 if len(columns) > 10 else 8.27)
    section.left_margin = section.right_margin = Inches(0.35)
    document.styles["Normal"].font.size = Pt(9)
    table = document.add_table(rows=2, cols=len(columns))
    table.style = "Table Grid"
    for cell, column in zip(table.rows[0].cells, columns, strict=True):
        cell.paragraphs[0].add_run(column).bold = True
    for cell, value in zip(table.rows[1].cells, values, strict=True):
        cell.text = value
    document.save(path)


def generate_templates(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for kind, spec in CONTRACT["kinds"].items():
        columns = spec["columns"]
        values = [SAMPLES[kind].get(column, "") for column in columns]
        name = kind.lower()
        with (output / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            csv.writer(stream).writerows([columns, values])
        write_excel(output / f"{name}.xlsx", columns, values)
        write_word(output / f"{name}.docx", columns, values)
