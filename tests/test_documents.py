import ast
import io
import json
import re
import struct
import unittest
import xml.etree.ElementTree as ET
import zlib
from copy import deepcopy
from pathlib import Path
from datetime import date, timedelta

import olefile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
# Load document helpers without executing the Streamlit UI or calling Gemini.
FUNCTIONS = ast.Module(body=[n for n in ast.parse(SOURCE).body
                            if isinstance(n, ast.FunctionDef)], type_ignores=[])
NS = dict(re=re, io=io, json=json, struct=struct, zlib=zlib, olefile=olefile,
          ET=ET, deepcopy=deepcopy, date=date, timedelta=timedelta, TEMPLATE_PATH=ROOT / "template.hml")
exec(compile(FUNCTIONS, "app.py", "exec"), NS)


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.template = (ROOT / "template.hml").read_text(encoding="utf-8")
        self.tokens = set(re.findall(r"__[A-Z0-9_]+__", self.template))
        self.day = {t.strip("_").lower(): "첫 줄 & <내용>\n둘째 줄"
                    for t in self.tokens}

    def test_template_complete(self):
        expected = set(re.findall(r"__[A-Z0-9_]+__", SOURCE))
        self.assertEqual(expected, self.tokens)
        self.assertEqual(len(self.tokens), 37)

    def test_multiline_preserves_tables_and_fills_every_field(self):
        result = NS["build_hwp_from_template"](self.template, self.day)
        before, after = ET.fromstring(self.template), ET.fromstring(result)
        for tag in ("TABLE", "ROW", "CELL"):
            self.assertEqual(len(list(before.iter(tag))), len(list(after.iter(tag))))
        self.assertNotRegex(result.decode(), r"__[A-Z0-9_]+__")
        text = list(c.text for c in after.iter("CHAR"))
        self.assertEqual(text.count("첫 줄 & <내용>"), 37)
        self.assertEqual(text.count("둘째 줄"), 37)

    def test_missing_template_token_rejected(self):
        with self.assertRaises(ValueError):
            NS["build_hwp_from_template"](self.template.replace("__TOPIC__", ""), self.day)

    def test_invalid_ai_data_rejected(self):
        for data in ({}, [], [self.day, self.day], [{"date_str": "월요일"}], [None]):
            with self.subTest(data_type=type(data)), self.assertRaises(ValueError):
                NS["validate_days"](data)
        self.assertEqual(NS["validate_days"]([self.day]), [self.day])

    def test_invalid_upload_rejected(self):
        with self.assertRaises(ValueError):
            NS["extract_text_from_hwp_bytes"](b"not a document")

    def test_hml_readback(self):
        result = NS["build_hwp_from_template"](self.template, self.day)
        text = NS["extract_text_from_hwp_bytes"](result)
        self.assertIn("첫 줄 & <내용>", text)


if __name__ == "__main__":
    unittest.main()
