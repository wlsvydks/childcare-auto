"""Regression cases from the supplied plans, without children's records."""
import struct
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from unittest.mock import Mock, patch

from google.genai import types
from hwp_documents import paragraph_text, records, weekly_day_contexts
from test_documents import NS, ROOT


def plan(title):
    return (f'◈ 활동명: {title}\n- 활동목표: 탐색한다.\n- 세부내용: C001\n'
            '- 활동자료: 놀잇감\n- 활동방법\n1. 함께 살펴본다.\nT: 무엇이 보이니?')


def weekly_hml():
    root = ET.Element('HWPML')
    table = ET.SubElement(root, 'TABLE')
    def cell(row, col, text, width=12010, span=1):
        r = ET.SubElement(table, 'ROW')
        c = ET.SubElement(r, 'CELL', RowAddr=str(row), ColAddr=str(col),
                          ColSpan=str(span), RowSpan='1', Width=str(width))
        ET.SubElement(ET.SubElement(c, 'P'), 'CHAR').text = text
    for col, day, weekday in zip((2, 3, 4, 5, 7), range(3, 8), '월화수목금'):
        cell(0, col, f'{day}일 ({weekday})')
    rows = [('등원및조용한놀이', ['친구와 인사해요', '(ㅇ)', '(ㅇ)', '(ㅇ)', '(ㅇ)']),
            ('오전실외놀이', ['공 놀이', '(x)', '(x)', '(x)', '(x)']),
            ('오전실내놀이 신체', ['체조해요', '징검다리', '동작 화보', '(ㅇ)', '풍선 놀이']),
            ('오전실내놀이 언어', ['단어 카드', '끼적이기\n(+) 책 보기', '그림책', '얼굴 그림', '사진 그림']),
            ('오전실내놀이 감각·탐색', ['몸 꾸미기', '돋보기', '표정 퍼즐', '관절 인형\n(+) 다양한 표정 퍼즐', '얼굴 꾸미기']),
            ('오전실내놀이 역할·쌓기', ['병원 놀이', '(ㅇ)', '벽돌 블록', '(ㅇ)', '(ㅇ)']),
            ('점심및낮잠', ['낮잠음악 [love me]', '(ㅇ)', '(ㅇ)\n+놀잇감을 정리해요(중점)', '낮잠동화 [사이좋게 지내자]', '(ㅇ)']),
            ('오후활동 실내', ['안전 그림책', '(ㅇ)\n+ 손 지문', '(ㅇ)\n+ 거품 손 씻기', '(ㅇ)', '(ㅇ)']),
            ('오후활동 실외', ['장애물', '(x)', '(x)', '선을 따라 걸어요', '(x)']),
            ('미세먼지·우천시대체활동', ['볼링', '(ㅇ)', '(ㅇ)', '(ㅇ)', '(ㅇ)']),
            ('기본생활및안전', ['청결점검', '물기 닦기', '(ㅇ)', '(ㅇ)', '(ㅇ)'])]
    for row, (label, values) in enumerate(rows, 1):
        if ' ' in label:
            group, area = label.split(' ', 1)
            cell(row, 0, group, 2704)
            cell(row, 1, area, 5576)
        else:
            cell(row, 0, label, 8280, 2)
        for col, value in zip((2, 3, 4, 6, 8), values):
            cell(row, col, value)
    return ET.tostring(root, encoding='utf-8')


class TableTests(unittest.TestCase):
    def setUp(self):
        self.contexts = weekly_day_contexts(weekly_hml())

    def test_five_days_and_eleven_rows_despite_different_grid_splits(self):
        self.assertEqual(len(self.contexts), 5)
        self.assertTrue(all(len(v) == 11 for v in self.contexts.values()))
        self.assertEqual(self.contexts['6일(목)'][2]['inherited'], '동작 화보')
        self.assertEqual(self.contexts['7일(금)'][8]['inherited'], '선을 따라 걸어요')

    def test_new_afternoon_addition_replaces_yesterdays_addition(self):
        self.assertEqual(self.contexts['5일(수)'][7]['inherited'], '안전 그림책')
        self.assertIn('거품 손 씻기', self.contexts['6일(목)'][7]['inherited'])
        self.assertNotIn('손 지문', self.contexts['6일(목)'][7]['inherited'])

    def test_table_morning_and_title_only_rules(self):
        rows = self.contexts['6일(목)']
        activities = NS['morning_activities_from_table'](rows)
        self.assertEqual(activities['sense_plan'], ['관절 인형', '다양한 표정 퍼즐'])
        brief = NS['table_title_only'](rows, activities)
        self.assertEqual(brief['body_plan'], ['동작 화보'])
        self.assertEqual(brief['sense_plan'], ['다양한 표정 퍼즐'])
        self.assertNotIn('관절 인형', brief['sense_plan'])

    def test_other_day_and_weekly_evaluation_not_in_day_source(self):
        source = NS['scoped_day_source']('■ 실시기간: 2026년 8월 3일 ~ 8월 8일\n주간 총 평가\n다른 기록',
                                          date(2026, 8, 6), self.contexts['6일(목)'])
        self.assertNotIn('다른 기록', source)
        self.assertNotIn('징검다리', source)
        self.assertIn('동작 화보', source)

    def test_unknown_layout_is_not_guessed(self):
        self.assertEqual(weekly_day_contexts(b'<HWPML><TABLE/></HWPML>'), {})

    def test_completely_different_activity_names_come_from_uploaded_cells(self):
        data = weekly_hml().decode('utf-8').replace('체조해요', '낙엽으로 길을 만들어요').replace('볼링', '눈송이 옮기기')
        rows = weekly_day_contexts(data.encode('utf-8'))['3일(월)']
        required = NS['required_activities_from_table'](rows)
        self.assertEqual(required['body_plan'], ['낙엽으로 길을 만들어요'])
        self.assertIn('눈송이 옮기기', required['outdoor_am_plan'])
        self.assertNotIn('볼링', str(required))

    def test_wrapped_goal_is_preserved(self):
        text = '■ 주 제 : 움직이며 놀이해요\n■ 소 주 제 : 움직이는 것이 재미있어요\n■ 목 표 : 몸을 자유롭게\n움직이며 다양한 활동에 참여해봅니다.\n■ 실시기간 : 2026년 8월 31일 ~ 9월 5일\n날       짜'
        result = NS['scoped_day_source'](text, date(2026, 8, 31), [])
        self.assertIn('몸을 자유롭게 움직이며 다양한 활동에 참여해봅니다.', result)
        self.assertIn('소주제: 움직이는 것이 재미있어요', result)

    def test_supplementary_unicode_and_extended_control(self):
        data = '놀이😀'.encode('utf-16le') + b'\x0b\x00' + b'\x00' * 14 + '끝'.encode('utf-16le')
        self.assertEqual(paragraph_text(data), '놀이😀끝')

    def test_truncated_records_rejected(self):
        with self.assertRaises(ValueError):
            list(records(struct.pack('<I', 67 | (20 << 20)) + b'abc'))


class PlanRuleTests(unittest.TestCase):
    def test_missing_outdoor_and_focus_plans_are_automatically_built(self):
        rows = weekly_day_contexts(weekly_hml())['5일(수)']
        activities = NS['required_activities_from_table'](rows)
        brief = NS['table_title_only'](rows, activities)
        response = {'goals': ['탐색한다.'], 'curriculum_ids': ['C001'], 'materials': [],
                    'steps': [{'action': '살펴본다.', 'speech': ['무엇이 보이니?']}]}
        with patch.dict(NS, {'generate_with_fallback': Mock(return_value=response)}):
            result = NS['repair_morning_plans']({}, activities, brief, 'key', '', '', Mock(), {})
        NS['validate_activity_coverage'](result, activities, brief)
        result = NS['restore_alternative_heading'](result, rows)
        self.assertIn('[미세먼지 · 우천시 대체활동]', result['outdoor_am_plan'])
        self.assertIn('놀잇감을 정리해요(중점)', result['lunch_plan'])
        self.assertIn('친구와 인사해요', result['morning_act_plan'])
        self.assertIn('장애물', result['outdoor_pm_plan'])

    def test_similar_title_is_not_shortened(self):
        day = {'body_plan': plan('공 굴리기') + '\n' + plan('큰 공 굴리기')}
        result = NS['shorten_continued_plans'](day, {'body_plan': ['공 굴리기']})
        self.assertEqual(result['body_plan'].count('활동방법'), 1)
        self.assertIn(plan('큰 공 굴리기'), result['body_plan'])

    def test_every_new_activity_needs_its_own_details(self):
        with self.assertRaises(ValueError):
            NS['validate_activity_coverage']({'body_plan': plan('공 굴리기') + '\n◈ 활동명: 큰 공 굴리기'},
                                             {'body_plan': ['공 굴리기', '큰 공 굴리기']})

    def test_execution_marker_does_not_change_identity(self):
        NS['validate_activity_coverage']({'body_plan': plan('공 굴리기 (ㅇ)')}, {'body_plan': ['공 굴리기']})

    def test_focus_activity_survives_final_document(self):
        title = '놀잇감을 정리해요(중점)'
        day = {'lunch_plan': plan(title)}
        NS['validate_focus_activities'](day, '+ ' + title)
        NS['validate_table_focus'](day, [{'area': '점심및낮잠', 'original': '(ㅇ)\n+' + title}])
        result = NS['finalize_activity_plans'](day)
        document = NS['build_hwp_from_template']((ROOT / 'template.hml').read_text(encoding='utf-8'), result)
        text = NS['extract_text_from_hwp_bytes'](document)
        self.assertIn(title, text)
        self.assertIn('활동방법', text)
        self.assertEqual(NS['fill_routine_plans'](result), result)

    def test_missing_or_invented_focus_activity_rejected(self):
        with self.assertRaises(ValueError):
            NS['validate_focus_activities']({'lunch_plan': plan('없는 놀이(중점)')}, '놀잇감을 정리해요(중점)')
        with self.assertRaises(ValueError):
            NS['validate_table_focus']({}, [{'area': '점심및낮잠', 'original': '+놀잇감을 정리해요(중점)'}])

    def test_observation_notes_are_selected_by_full_date(self):
        source = '[추가 실행·관찰 기록]\n날짜 없는 기록\n2026-08-03\n월요일 기록\n2026년 8월 4일\n화요일 기록'
        self.assertEqual(NS['dated_observation_notes'](source, date(2026, 8, 4)), '화요일 기록')

    def test_nap_title_uses_weekly_cell_instead_of_reference(self):
        rows = weekly_day_contexts(weekly_hml())['7일(금)']
        result = NS['apply_table_nap_title']({'nap_plan': '◈ 낮잠음악 [다른 음악] (ㅇ)\n- 휴식을 돕는다.'}, rows)
        self.assertIn('낮잠동화 [사이좋게 지내자]', result['nap_plan'])
        self.assertNotIn('다른 음악', result['nap_plan'])
        self.assertIn('- 휴식을 돕는다.', result['nap_plan'])

    def test_table_generation_does_not_copy_other_day_evaluation(self):
        target = date(2026, 8, 6)
        rows = weekly_day_contexts(weekly_hml())['6일(목)']
        activities = NS['required_activities_from_table'](rows)
        day = {'date_str': NS['day_label'](target), **{k: '\n'.join(plan(t) for t in v) for k, v in activities.items()}}
        invented = dict(day, body_eval='월요일에만 기록된 문장')
        request = Mock(side_effect=[[invented], [day]])
        with patch.dict(NS, {'generate_with_fallback': request, 'types': types,
                             'extract_afternoon_activities': Mock(return_value={f'pm_cell_{i}': [] for i in range(1, 5)})}):
            result = NS['analyze_and_generate']('key', b'', 'image/png',
                '■ 실시기간: 2026년 8월 3일 ~ 8월 8일\n[추가 실행·관찰 기록]\n2026-08-03\n월요일에만 기록된 문장',
                '', Mock(), target, rows)
        self.assertEqual(request.call_count, 2)
        self.assertNotIn('월요일에만 기록된 문장', result['body_eval'])
        self.assertNotIn('활동방법', result['body_plan'])
        self.assertIn('활동방법', result['sense_plan'])


if __name__ == '__main__':
    unittest.main()
