import csv
import io
import unittest
from datetime import datetime
from zipfile import ZipFile

from openpyxl import Workbook

from vlearn_importer.structured import CONTRACT, ParseError, parse_bytes

KIND = 'VOCABULARY'
HEADERS = CONTRACT['kinds'][KIND]['columns']


def csv_file(rows):
    buffer = io.StringIO(newline='')
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode('utf-8-sig')


def workbook_file(value, merge=False):
    workbook = Workbook()
    workbook.active.append(HEADERS)
    workbook.active.append([value, 'văn phòng'])
    if merge:
        workbook.active.merge_cells('A2:B2')
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class SpreadsheetTests(unittest.TestCase):
    def test_csv_preserves_multiline_unicode_and_physical_row(self):
        row = ['office', 'văn phòng', '', '', 'line 1\nline 2', '', '', '']
        result = parse_bytes(csv_file([HEADERS, row, row]), '.csv', KIND)
        self.assertEqual(result, [
            {'row': 2, 'values': dict(zip(HEADERS, row, strict=True))},
            {'row': 4, 'values': dict(zip(HEADERS, row, strict=True))},
        ])

    def test_csv_rejects_invalid_headers_width_encoding_and_quotes(self):
        for data in (
            csv_file([HEADERS[:-1]]), csv_file([HEADERS[:-1] + [HEADERS[0]]]),
            csv_file([HEADERS, ['one cell']]), csv_file([HEADERS]) + b'\xff',
            csv_file([HEADERS]) + b'"unterminated',
        ):
            with self.subTest(data=data), self.assertRaises(ParseError):
                parse_bytes(data, '.csv', KIND)

    def test_csv_limits(self):
        for rows in ([['x' * 20001] * 8], [['x'] * 8] * 201, [['x' * 20000] * 8] * 8):
            with self.assertRaises(ParseError):
                parse_bytes(csv_file([HEADERS] + rows), '.csv', KIND)

    def test_xlsx_converts_numbers_and_preserves_blanks(self):
        [record] = parse_bytes(workbook_file(12.5), '.xlsx', KIND)
        self.assertEqual(record['row'], 2)
        self.assertEqual(list(record['values']), HEADERS)
        self.assertEqual(record['values']['term'], '12.5')
        self.assertEqual(record['values']['meaning'], 'văn phòng')
        self.assertEqual(record['values']['ipa'], '')

    def test_xlsx_rejects_formulas_dates_and_merged_cells(self):
        for value, merge in [('=1+1', False), (datetime(2026, 1, 1), False), ('x', True)]:
            with self.assertRaises(ParseError):
                parse_bytes(workbook_file(value, merge), '.xlsx', KIND)

    def test_xlsx_rejects_excessive_xml_elements_in_other_parts(self):
        archive = io.BytesIO(workbook_file('office'))
        with ZipFile(archive, 'a', compression=8) as package:
            package.writestr('unused.xml', b'<root>' + b'<x/>' * 100_001 + b'</root>')
        with self.assertRaises(ParseError):
            parse_bytes(archive.getvalue(), '.xlsx', KIND)

    def test_xlsx_rejects_invalid_or_unsafe_packages(self):
        for name, data in (
            ('xl/vbaProject.bin', b'macro'), ('xl/externalLinks/x.xml', b'x'),
            ('large', bytes(30 * 1024 * 1024 + 1)),
        ):
            archive = io.BytesIO()
            with ZipFile(archive, 'w', compression=8) as package:
                package.writestr(name, data)
            with self.assertRaises(ParseError):
                parse_bytes(archive.getvalue(), '.xlsx', KIND)
        with self.assertRaises(ParseError):
            parse_bytes(b'not a zip', '.xlsx', KIND)


def document_file(
    *, merge=False, nested=False, extra_table=False, row_count=2, reorder=False,
):
    from docx import Document

    document = Document()
    table = document.add_table(rows=row_count, cols=len(HEADERS))
    for cell, header in zip(table.rows[0].cells, HEADERS, strict=True):
        cell.text = header
    first = table.cell(1, 0)
    first.text = 'office'
    table.cell(1, 1).text = 'văn phòng'
    example = table.cell(1, 4)
    example.text = 'one\ntwo'
    example.add_paragraph('three')
    if merge:
        first.merge(table.cell(1, 1))
    if nested:
        first.add_table(rows=1, cols=1)
    if extra_table:
        document.add_table(rows=1, cols=1)
    if reorder:
        for row in table.rows:
            row._tr.append(row.cells[0]._tc)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class DocxTests(unittest.TestCase):
    def test_docx_preserves_line_breaks_and_paragraphs(self):
        [row] = parse_bytes(document_file(), '.docx', KIND)
        self.assertEqual(row['row'], 2)
        self.assertEqual(row['values']['example'], 'one\ntwo\nthree')
        self.assertEqual(row['values']['meaning'], 'văn phòng')

    def test_docx_orders_values_by_header_and_retains_row_numbers(self):
        [row] = parse_bytes(document_file(row_count=3, reorder=True), '.docx', KIND)
        self.assertEqual(list(row['values']), HEADERS)
        self.assertEqual(row['values']['term'], 'office')
        self.assertEqual(row['values']['meaning'], 'văn phòng')
        self.assertEqual(row['row'], 2)

    def test_docx_rejects_merged_nested_additional_and_oversize_tables(self):
        for kwargs in ({'merge': True}, {'nested': True}, {'extra_table': True}, {'row_count': 202}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ParseError):
                parse_bytes(document_file(**kwargs), '.docx', KIND)
