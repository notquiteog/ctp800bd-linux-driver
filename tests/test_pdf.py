# SPDX-License-Identifier: MIT
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from test_driver import cli


class PDFPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'input.pdf'
        self.output = Path(self.temp.name) / 'output.pdf'

    def fixture(self, sizes=((612, 792), (612, 792))):
        writer = PdfWriter()
        for width, height in sizes:
            page = writer.add_blank_page(width=width, height=height)
            content = DecodedStreamObject()
            # One-inch square inside the label; a second mark outside it.
            content.set_data(b'q 0 g 36 684 72 72 re f 400 80 20 20 re f Q')
            page[NameObject('/Contents')] = writer._add_object(content)
        with self.source.open('wb') as stream:
            writer.write(stream)

    def test_crop_preserves_scale_and_excludes_outside_content(self):
        self.fixture()
        original = self.source.read_bytes()
        self.assertEqual(cli.prepare_pdf(self.source, self.output, 'letter-top-left'), 2)
        self.assertEqual(self.source.read_bytes(), original)
        for page in PdfReader(self.output).pages:
            self.assertEqual(list(page.mediabox), [0, 0, 288, 432])
            self.assertEqual(list(page.cropbox), [0, 0, 288, 432])
        # Render with Ghostscript: the square remains exactly 72pt (one inch)
        # wide/high, and the mark outside the crop is absent from the bounds.
        result = subprocess.run(['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE',
            '-sDEVICE=bbox', str(self.output)], capture_output=True, text=True, check=True)
        boxes = re.findall(r'%%HiResBoundingBox: ([0-9. ]+)', result.stderr)
        self.assertEqual(len(boxes), 2)
        for box in boxes:
            for actual, expected in zip(map(float, box.split()), (36, 324, 108, 396)):
                self.assertAlmostEqual(actual, expected, delta=0.05)

    def test_letter_crop_must_be_explicit(self):
        self.fixture()
        with self.assertRaisesRegex(ValueError, 'letter-top-left'):
            cli.prepare_pdf(self.source, self.output, '4x6')
        self.assertFalse(self.output.exists())

    def test_existing_output_and_source_are_preserved(self):
        self.fixture()
        self.output.write_bytes(b'keep me')
        for destination in (self.output, self.source):
            with self.assertRaisesRegex(ValueError, 'never overwritten'):
                cli.prepare_pdf(self.source, destination, 'letter-top-left')
        self.assertEqual(self.output.read_bytes(), b'keep me')

    def test_all_pages_are_validated_before_output(self):
        self.fixture(sizes=((612, 792), (595, 842)))
        with self.assertRaisesRegex(ValueError, 'Page 2'):
            cli.prepare_pdf(self.source, self.output, 'letter-top-left')
        self.assertFalse(self.output.exists())

    def test_already_label_sized_pdf(self):
        self.fixture(sizes=((288, 432),))
        self.assertEqual(cli.prepare_pdf(self.source, self.output, '4x6'), 1)
        self.assertEqual(list(PdfReader(self.output).pages[0].mediabox), [0, 0, 288, 432])

    def test_invalid_pdf_is_reported(self):
        self.source.write_bytes(b'not a pdf')
        self.assertEqual(cli.main(['prepare-pdf', str(self.source), str(self.output)]), 1)
        self.assertFalse(self.output.exists())
