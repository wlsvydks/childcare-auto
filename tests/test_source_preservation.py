import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

from google.genai import types
from test_documents import NS


class SourcePreservationTests(unittest.TestCase):
    def test_pdf_routines_survive_document_generation_without_shortening(self):
        from test_documents import ROOT
        defaults = json.loads((ROOT / 'routine_plans.json').read_text(encoding='utf-8'))
        document = NS['build_hwp_from_template'](
            (ROOT / 'template.hml').read_text(encoding='utf-8'), {})
        text = NS['extract_text_from_hwp_bytes'](document)
        for field, value in defaults.items():
            for line in value.splitlines():
                if line:
                    with self.subTest(field=field, line=line):
                        self.assertIn(line, text)
        self.assertEqual(defaults['clean_pm_plan'], '- 손 씻기')
        self.assertEqual(len(defaults['lunch_clean_plan'].splitlines()), 2)
        self.assertIn('손유희를 하며 식사를 준비한다.', defaults['snack_am_plan'])
        self.assertNotIn('love me', text)

    def test_routine_lesson_expansion_is_removed_from_saved_document(self):
        from test_documents import ROOT
        expanded = ('- 활동목표: 식사 전 손을 씻는다.\n'
                    '- 세부내용: 기본생활>확인되지 않은 문구\n'
                    '- 활동자료: 비누, 수건\n- 활동방법:\n1. 손을 씻는다.')
        defaults = json.loads((ROOT / 'routine_plans.json').read_text(encoding='utf-8'))
        day = {field: expanded for field in defaults if field != 'morning_act_plan'}
        text = NS['extract_text_from_hwp_bytes'](NS['build_hwp_from_template'](
            (ROOT / 'template.hml').read_text(encoding='utf-8'), day))
        for label in ('활동목표:', '세부내용:', '활동자료:', '활동방법:', '1. 손을'):
            self.assertNotIn(label, text)
        self.assertIn('- 손 씻기', text)
        self.assertIn('통합보육실에서 조용한 놀이 및 휴식하기', text)

    def test_play_details_and_plain_routines_are_preserved(self):
        detail = '◈ 활동명: 공을 굴려요\n- 활동목표: 공을 탐색한다.\n- 활동방법\n1. 공을 굴린다.\nT: 굴려볼까?'
        play_fields = ('morning_act_plan', 'body_plan', 'lang_plan', 'sense_plan',
                       'role_plan', 'outdoor_am_plan', 'pm_cell_1', 'pm_cell_2',
                       'pm_cell_3', 'pm_cell_4', 'outdoor_pm_plan')
        day = {field: detail for field in play_fields}
        day['nap_plan'] = '◈ 낮잠음악 [원문 제목]\n- 자신의 자리에 누울 수 있도록 돕는다.'
        result = NS['fill_routine_plans'](day)
        for field in play_fields:
            self.assertIn(detail, result[field])
        self.assertEqual(result['nap_plan'], day['nap_plan'])

    def test_numbered_routine_without_headers_is_also_removed(self):
        for expanded in ('1. 손을 씻는다.\n2. 닦는다.', '- T: 손을 씻어볼까?',
                         '**활동 목표**: 청결을 유지한다.'):
            self.assertEqual(NS['fill_routine_plans']({'clean_pm_plan': expanded})[
                'clean_pm_plan'], '- 손 씻기')

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
        self.assertEqual(result['date_str'], corrected['date_str'])
        self.assertEqual(result['sense_eval'], '')
        self.assertIn('기록 전', result['daily_eval'])
        self.assertEqual(request.call_count, 2)

    def test_repeated_ungrounded_result_stops(self):
        target = date(2026, 4, 24)
        request = Mock(return_value=[{
            'date_str': NS['day_label'](target), 'nap_eval': '잘 잤음.'}])
        with patch.dict(NS, {'generate_with_fallback': request, 'types': types, 'json': json}):
            with self.assertRaisesRegex(ValueError, '확인할 수 없는 문장'):
                NS['analyze_and_generate']('key', b'', 'image/png', '', '', Mock(), target)
        self.assertEqual(request.call_count, 3)


if __name__ == '__main__':
    unittest.main()
