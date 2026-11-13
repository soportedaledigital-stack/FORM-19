"""Run: python -m unittest discover -s tests -p 'test_core.py' -v"""
from io import BytesIO
from pathlib import Path
from unittest import TestCase, main
from zipfile import ZipFile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from form19_core import (READINGS, NS, xml, is_valid_book, get_values, patch_cell,
                         parse_value, parse_ocr_text, format_value, decode_image)


class CoreTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / 'data' / 'FORM19_PLANTILLA.xlsm').read_bytes()

    def test_template_has_all_21_empty_cells(self):
        is_valid_book(self.template)
        self.assertEqual(set(get_values(self.template)), set(READINGS))
        self.assertTrue(all(value is None for value in get_values(self.template).values()))

    def test_write_all_21_readings_without_touching_other_zip_members(self):
        data = self.template
        for index, cell in enumerate(READINGS):
            value = (index + 1) / 100
            data = patch_cell(data, cell, value)
            self.assertAlmostEqual(float(get_values(data)[cell]), value)
        with ZipFile(BytesIO(self.template)) as original, ZipFile(BytesIO(data)) as changed:
            path = is_valid_book(data)
            self.assertEqual(original.namelist(), changed.namelist())
            for name in original.namelist():
                if name != path:
                    self.assertEqual(original.read(name), changed.read(name), name)
            original_xml = xml(original.read(path))
            changed_xml = xml(changed.read(path))
            # Ignore the 21 editable cells, compare everything else in the worksheet.
            for root in (original_xml, changed_xml):
                for c in root.findall(f'.//{{{NS}}}sheetData/{{{NS}}}row/{{{NS}}}c'):
                    if c.get('r') in READINGS:
                        c.getparent().remove(c)
            from lxml import etree
            self.assertEqual(etree.tostring(original_xml), etree.tostring(changed_xml))
            self.assertIsNone(changed.testzip())

    def test_only_requested_cell_changes(self):
        data = patch_cell(self.template, 'E40', 0.2982)
        actual = get_values(data)
        self.assertEqual(actual['E40'], '0.2982')
        self.assertTrue(all(v is None for k, v in actual.items() if k != 'E40'))

    def test_invalid_cells_rejected(self):
        for cell in ('D40', 'E43', 'A1', '../E40', 'E40\"'):
            with self.assertRaises(ValueError):
                patch_cell(self.template, cell, 0.3)

    def test_numeric_validation(self):
        self.assertEqual(parse_value('0,000'), 0)
        self.assertEqual(parse_value('3.0000'), 3)
        self.assertEqual(parse_value('0,2982'), 0.2982)
        for value in ('300', '-0.1', '3.0001', 'nan', '1e-2', '0,3 g/L', None, 0.3, '<script>'):
            with self.assertRaises(ValueError):
                parse_value(value)

    def test_no_decimal_invention(self):
        for text in ('300\n300\n300', '0300\n0300', '1\n1', '3.001\n3.001'):
            self.assertIsNone(parse_ocr_text(text)[0])
        self.assertEqual(parse_ocr_text('.300\n.300\n.300')[0], '0,300')

    def test_concordant_ocr_and_zero(self):
        self.assertEqual(parse_ocr_text('0.300\n0,300\n0.300')[0], '0,300')
        self.assertEqual(parse_ocr_text('0 . 000\n0.000')[0], '0,000')
        self.assertEqual(parse_ocr_text('1.4878\n1.4878\n1.4878')[0], '1,4878')

    def test_ambiguous_ocr_and_single_line_not_accepted(self):
        self.assertIsNone(parse_ocr_text('0.300\n0.800\n0.300')[0])
        self.assertIsNone(parse_ocr_text('0.300')[0])
        self.assertFalse(parse_ocr_text('0.300\n0.800')[4])
        self.assertTrue(parse_ocr_text('')[4])

    def test_precision_and_invalid_photo(self):
        self.assertEqual(format_value(0.2982), '0,2982')
        self.assertEqual(format_value(0.3), '0,300')
        with self.assertRaises(ValueError):
            decode_image(b'not a photograph')


if __name__ == '__main__':
    main()
