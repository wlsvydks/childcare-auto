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
        detail = {'goals': ['놀이에 관심을 가진다.'], 'curriculum_ids': ['C001'],
                  'materials': ['놀잇감'], 'steps': [{'action': '살펴본다.', 'speech': ['무엇이 보이니?']}]}
        request = Mock(side_effect=[extracted, [missing], detail])
        week = '2026년 9월 21일 ~ 9월 23일\n오전 실내놀이\n감각·탐색\n' + '\n'.join(v[0] for v in titles.values())
        with patch.dict(NS, {'generate_with_fallback': request, 'json': json, 'types': types}):
            day = NS['analyze_and_generate']('key', b'', 'image/png', week, '', Mock(), target)
        document = NS['build_hwp_from_template']((ROOT / 'template.hml').read_text(encoding='utf-8'), day)
        self.assertIn(titles['sense_plan'][0], NS['extract_text_from_hwp_bytes'](document))
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args.args[2]['type'], 'OBJECT')

    def test_changed_title_is_rebuilt_with_exact_source_title_and_cached(self):
        title = '[둘이 살짝] 노래에 맞추어 몸을 움직여요(사전)'
        detail = {'goals': ['음악에 맞추어 움직인다.'], 'curriculum_ids': ['C001'],
                  'materials': ['음원'], 'steps': [{'action': '음악을 듣는다.', 'speech': ['함께 움직여볼까?']}]}
        request = Mock(return_value=detail)
        cache = {}
        day = {'body_plan': '◈ 활동명: 둘이 살짝 체조', 'body_eval': '실제 기록'}
        with patch.dict(NS, {'generate_with_fallback': request}):
            for _ in range(2):
                result = NS['repair_morning_plans'](day, {'body_plan': [title]}, {},
                    'key', title, '', Mock(), cache)
                NS['validate_activity_coverage'](result, {'body_plan': [title]})
                self.assertIn('◈ 활동명: ' + title, result['body_plan'])
                self.assertIn('활동방법', result['body_plan'])
                self.assertEqual(result['body_eval'], '실제 기록')
        self.assertEqual(request.call_count, 1)

    def test_missing_repeated_activity_is_inserted_without_ai(self):
        title = '공 굴리기'
        request = Mock(side_effect=AssertionError('반복 활동에는 AI 호출 불필요'))
        with patch.dict(NS, {'generate_with_fallback': request}):
            result = NS['repair_morning_plans']({}, {'body_plan': [title]}, {'body_plan': [title]},
                'key', title, '', Mock(), {})
        self.assertEqual(result['body_plan'], '◈ 활동명: 공 굴리기')

    def test_valid_plan_is_kept_and_only_missing_activity_is_generated(self):
        from test_sample_rules import plan
        original = plan('공 굴리기')
        detail = {'goals': ['탐색한다.'], 'curriculum_ids': ['C001'], 'materials': [],
                  'steps': [{'action': '살펴본다.', 'speech': ['무엇이 보이니?']}]}
        request = Mock(return_value=detail)
        with patch.dict(NS, {'generate_with_fallback': request}):
            result = NS['repair_morning_plans']({'body_plan': original},
                {'body_plan': ['공 굴리기', '터널 지나가기']}, {}, 'key', '', '', Mock(), {})
        self.assertEqual(request.call_count, 1)
        self.assertIn('공 굴리기', result['body_plan'])
        self.assertIn('터널 지나가기', result['body_plan'])
        self.assertIn('T: 무엇이 보이니?', result['body_plan'])


if __name__ == '__main__':
    unittest.main()
