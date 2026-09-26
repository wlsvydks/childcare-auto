import io
import json
import unittest
import zipfile
from datetime import date
from unittest.mock import Mock, patch

from google.genai import types
from test_documents import NS, ROOT


WEEK = "실시기간 : 2026년 9월 1주 (8월 31일 ~ 9월 5일)\n31일 (월)\n1일 (화)\n2일 (수)\n3일 (목)\n4일 (금)\n5일 (토)\n토요통합 미운영"


class WeekTests(unittest.TestCase):
    def test_actual_period_layout_crosses_month(self):
        self.assertEqual(NS["weekly_dates"](WEEK), [date(2026, 8, 31)] +
                         [date(2026, 9, d) for d in range(1, 5)])

    def test_year_boundary(self):
        days = NS["weekly_dates"]("2027년 1월 1주 (12월 28일 ~ 1월 2일)")
        self.assertEqual(days[0], date(2026, 12, 28))
        self.assertEqual(days[-1], date(2027, 1, 1))

    def test_numeric_period_and_explicit_closed_day(self):
        days = NS["weekly_dates"]("2026.08.31 ~ 2026.09.05\n2일 (수) 휴원")
        self.assertEqual(len(days), 4)
        self.assertNotIn(date(2026, 9, 2), days)

    def test_ambiguous_or_invalid_period_stops_before_generation(self):
        for text in ("9월 1주", "2026년 9월 1주", "2026년 2월 30일 ~ 3월 1일",
                     "2026년 9월 1일 ~ 9월 30일"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                NS["weekly_dates"](text)

    def test_five_distinct_files_with_correct_document_dates(self):
        template = (ROOT / "template.hml").read_text(encoding="utf-8")
        generator = Mock(side_effect=lambda *args: {"date_str": NS["day_label"](args[-1])})
        with patch.dict(NS, {"analyze_and_generate": generator}):
            files = NS["generate_week_files"]("key", b"", "image/png", WEEK,
                                               "2026년 9월 4일 샘플", template, Mock())
        self.assertEqual(generator.call_count, 5)
        self.assertEqual(len({name for name, _ in files}), 5)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data in files:
                archive.writestr(name, data)
        with zipfile.ZipFile(buffer) as archive:
            self.assertEqual(len(archive.namelist()), 5)
            for name, target in zip(archive.namelist(), NS["weekly_dates"](WEEK)):
                self.assertIn(NS["day_label"](target), archive.read(name).decode("utf-8"))

    def test_interrupted_generation_resumes_without_recreating_completed_days(self):
        completed = {}
        generator = Mock(side_effect=[{"date_str": "day1"}, RuntimeError("quota")])
        with patch.dict(NS, {"analyze_and_generate": generator,
                             "build_hwp_from_template": lambda *args: b"document"}):
            with self.assertRaises(RuntimeError):
                NS["generate_week_files"]("key", b"", "image/png", WEEK, "", "", Mock(), completed)
            self.assertEqual(len(completed), 1)
            generator.reset_mock()
            generator.side_effect = lambda *args: {"date_str": NS["day_label"](args[-1])}
            files = NS["generate_week_files"]("key", b"", "image/png", WEEK, "", "", Mock(), completed)
        self.assertEqual(len(files), 5)
        self.assertEqual(generator.call_count, 4)

    def test_wrong_ai_date_retried_instead_of_accepting_sample_date(self):
        target = date(2026, 8, 31)
        correct = {"date_str": NS["day_label"](target)}
        request = Mock(side_effect=[[{"date_str": "2026년 9월 4일 금요일"}], [correct]])
        with patch.dict(NS, {"generate_with_fallback": request, "types": types, "json": json}):
            result = NS["analyze_and_generate"]("key", b"", "image/png", WEEK, "sample", Mock(), target)
        self.assertEqual(result['date_str'], correct['date_str'])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[2]["items"]["properties"]["date_str"]["enum"], [correct["date_str"]])


if __name__ == "__main__":
    unittest.main()
