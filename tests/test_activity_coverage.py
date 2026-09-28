import json
import unittest
from datetime import date
from unittest.mock import Mock, patch
from google.genai import types
from test_documents import NS, ROOT


class ActivityCoverageTests(unittest.TestCase):
    def test_missing_or_swapped_sensory_activity_is_rejected(self):
        activities = {'sense_plan': ['도로 위에 탈 것 스티커를 붙여요']}
        for day in ({'sense_plan': ''}, {'lang_plan': activities['sense_plan'][0]},
                    {'sense_plan': '활동목표\n활동방법\n◈ 활동명: 공을 굴려요'}):
            with self.subTest(day=day), self.assertRaises(ValueError):
                NS['validate_activity_coverage'](day, activities)

    def test_unsupported_extracted_activity_is_not_accepted(self):
        request = Mock(return_value={'body_plan': [], 'lang_plan': [],
                                    'sense_plan': ['없는 활동'], 'role_plan': []})
        with patch.dict(NS, {'generate_with_fallback': request}):
            with self.assertRaises(ValueError):
                NS['extract_day_activities']('key', '감각·탐색: 스티커 붙이기', '월요일', Mock())
        self.assertEqual(request.call_count, 2)

    def test_omitted_sensory_plan_is_repaired_before_file_creation(self):
        target = date(2026, 9, 21)
        titles = {'body_plan': ['신체 놀이'], 'lang_plan': ['언어 놀이'],
                  'sense_plan': ['도로 위에 탈 것 스티커를 붙여요'], 'role_plan': ['세차장 놀이']}
        extracted = dict(titles, **{f'pm_cell_{i}': [] for i in range(1, 5)})
        def plan(title):
            return (f'◈ 활동명: {title}\n- 활동목표: 놀이에 관심을 가진다.\n'
                    '- 세부내용: C001\n- 활동자료: 놀잇감\n- 활동방법\n'
                    '1. 살펴본다.\nT: 무엇이 보이니?')
        correct = {'date_str': NS['day_label'](target),
                   **{k: plan(v[0]) for k, v in titles.items()}}
        missing = dict(correct, sense_plan='')
        request = Mock(side_effect=[extracted, [missing], [correct]])
        week = '2026년 9월 21일 ~ 9월 23일\n오전 실내놀이\n감각·탐색\n' + '\n'.join(v[0] for v in titles.values())
        with patch.dict(NS, {'generate_with_fallback': request, 'json': json, 'types': types}):
            day = NS['analyze_and_generate']('key', b'', 'image/png', week, '', Mock(), target)
        document = NS['build_hwp_from_template']((ROOT / 'template.hml').read_text(encoding='utf-8'), day)
        self.assertIn(titles['sense_plan'][0], NS['extract_text_from_hwp_bytes'](document))
        self.assertEqual(request.call_count, 3)


if __name__ == '__main__':
    unittest.main()
