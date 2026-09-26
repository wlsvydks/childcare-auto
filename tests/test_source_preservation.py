import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

from google.genai import types
from test_documents import NS


class SourcePreservationTests(unittest.TestCase):
    def test_sparse_plan_gets_routines_without_inventing_evaluation(self):
        day = {'morning_act_plan': '가방 스스로 정리해보기(ㅇ)',
               'snack_am_plan': '-', 'daily_eval': ''}
        result = NS['fill_routine_plans'](day)
        self.assertIn('건강 상태', result['morning_act_plan'])
        self.assertIn(day['morning_act_plan'], result['morning_act_plan'])
        self.assertIn('손을 씻는다', result['snack_am_plan'])
        self.assertTrue(result['morning_care_plan'])
        self.assertEqual(result['daily_eval'], '')
        self.assertEqual(day['snack_am_plan'], '-')

    def test_existing_routine_is_preserved_and_filling_is_idempotent(self):
        day = {'snack_am_plan': '- 교사와 함께 간식 먹기를 준비한다.'}
        result = NS['fill_routine_plans'](day)
        self.assertEqual(result['snack_am_plan'], day['snack_am_plan'])
        self.assertEqual(NS['fill_routine_plans'](result), result)

    def test_verbatim_evaluation_and_empty_fields_are_allowed(self):
        NS['validate_evaluation_sources'](
            {'sense_eval': '- 도장을 찍는 모습이 나타남.', 'nap_eval': ''},
            '- 도장을 찍는 모습이\n나타남.')

    def test_invented_observation_and_future_plan_are_rejected(self):
        for text in ('즐겁게 참여하였음.', '탐색하도록 지원할 예정이다.'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                NS['validate_evaluation_sources']({'daily_eval': text}, '꽃을 탐색함.')

    def test_sample_evaluation_is_not_evidence_for_new_day(self):
        target = date(2026, 4, 24)
        label = NS['day_label'](target)
        invented = {'date_str': label, 'sense_eval': '도장을 찍는 모습이 나타남.'}
        corrected = {'date_str': label, 'sense_eval': ''}
        request = Mock(side_effect=[[invented], [corrected]])
        with patch.dict(NS, {'generate_with_fallback': request, 'types': types, 'json': json}):
            result = NS['analyze_and_generate'](
                'key', b'', 'image/png', '2026년 4월 20일 ~ 4월 24일',
                invented['sense_eval'], Mock(), target)
        self.assertEqual(result, corrected)
        self.assertEqual(request.call_count, 2)

    def test_repeated_ungrounded_result_stops(self):
        target = date(2026, 4, 24)
        request = Mock(return_value=[{
            'date_str': NS['day_label'](target), 'nap_eval': '잘 잤음.'}])
        with patch.dict(NS, {'generate_with_fallback': request, 'types': types, 'json': json}):
            with self.assertRaisesRegex(ValueError, '확인할 수 없는 문장'):
                NS['analyze_and_generate']('key', b'', 'image/png', '', '', Mock(), target)
        self.assertEqual(request.call_count, 2)


if __name__ == '__main__':
    unittest.main()
