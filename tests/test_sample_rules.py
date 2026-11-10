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


def weekly_hml(holiday=None):
    """holiday: 0~4 중 하나를 주면 그 요일 칸 전체가 '휴원'으로 세로 병합된 주안을 만듭니다."""
    root = ET.Element('HWPML')
    table = ET.SubElement(root, 'TABLE')
    def cell(row, col, text, width=12010, span=1, rowspan=1):
        r = ET.SubElement(table, 'ROW')
        c = ET.SubElement(r, 'CELL', RowAddr=str(row), ColAddr=str(col),
                          ColSpan=str(span), RowSpan=str(rowspan), Width=str(width))
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
        for index, (col, value) in enumerate(zip((2, 3, 4, 6, 8), values)):
            if index == holiday:
                if row == 1:
                    cell(row, col, '지방선거일\n(휴원)', rowspan=len(rows))
                continue
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
        # 실제 문서: 오전 칸의 '(+) 추가 놀이'는 계획란에 없고 평가란에 '+ 제목'으로만 적힙니다.
        self.assertEqual(activities['sense_plan'], ['관절 인형'])
        brief = NS['table_title_only'](rows, activities)
        self.assertEqual(brief['body_plan'], ['동작 화보'])
        self.assertNotIn('sense_plan', brief)
        self.assertEqual(NS['table_additions'](rows), {'sense_eval': ['다양한 표정 퍼즐']})
        day = NS['apply_table_additions']({'sense_plan': plan('관절 인형'), 'sense_eval': ''}, rows)
        self.assertEqual(day['sense_eval'], '+ 다양한 표정 퍼즐')
        prompted = NS['add_evaluation_prompts'](day)
        self.assertTrue(prompted['sense_eval'].startswith('+ 다양한 표정 퍼즐\n[실행·평가 기록 전]'))
        self.assertEqual(NS['add_evaluation_prompts'](prompted), prompted)
        self.assertEqual(NS['apply_table_additions'](prompted, rows), prompted)
        recorded = NS['apply_table_additions']({'sense_eval': '실제 기록'}, rows)
        self.assertEqual(recorded['sense_eval'], '+ 다양한 표정 퍼즐\n실제 기록')

    def test_plus_only_cell_continues_previous_activity(self):
        # 실제 10월 주안: 금요일 신체 칸이 '+ [비만 예방 정글체조] ...'뿐이면 전날 활동이 제목으로 이어집니다.
        data = weekly_hml().decode('utf-8').replace('풍선 놀이', '+ 정글체조 따라하기')
        rows = weekly_day_contexts(data.encode('utf-8'))['7일(금)']
        self.assertEqual(rows[2]['inherited'], '동작 화보')
        activities = NS['required_activities_from_table'](rows)
        self.assertEqual(activities['body_plan'], ['동작 화보'])
        self.assertEqual(NS['table_title_only'](rows, activities)['body_plan'], ['동작 화보'])
        self.assertEqual(NS['table_additions'](rows)['body_eval'], ['정글체조 따라하기'])
        source = NS['scoped_day_source']('■ 실시기간: 2026년 8월 3일 ~ 8월 8일\n날       짜', date(2026, 8, 7), rows)
        self.assertIn('계획란에 쓰지 않음', source)

    def test_plus_without_any_base_becomes_the_main_activity(self):
        data = weekly_hml().decode('utf-8').replace('체조해요', '+ 첫날 추가 놀이')
        rows = weekly_day_contexts(data.encode('utf-8'))['3일(월)']
        self.assertEqual(NS['required_activities_from_table'](rows)['body_plan'], ['첫날 추가 놀이'])
        self.assertNotIn('body_eval', NS['table_additions'](rows))

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

    def test_holiday_column_is_skipped_and_arrows_jump_over_it(self):
        contexts = weekly_day_contexts(weekly_hml(holiday=2))
        self.assertEqual(contexts['5일(수)'], [])
        self.assertEqual(len(contexts['3일(월)']), 11)
        thursday = {r['area']: r for r in contexts['6일(목)']}
        self.assertEqual(thursday['등원및조용한놀이']['inherited'], '친구와 인사해요')
        self.assertEqual(thursday['오전실내놀이 신체']['inherited'], '징검다리')
        self.assertEqual(thursday['오전실내놀이 신체']['original'], '(ㅇ)')

    def test_marks_follow_the_day_cell_of_each_area(self):
        rows = weekly_day_contexts(weekly_hml())['4일(화)']
        day = {'body_plan': '◈ 활동명: 징검다리\n- 활동목표: 건넌다.',
               'role_plan': '◈ 활동명: 병원 놀이',
               'outdoor_am_plan': '◈ 활동명: 공 놀이\n- 활동목표: 던진다.\n[미세먼지 · 우천시 대체활동]\n◈ 활동명: 볼링',
               'pm_cell_2': '[언어]\n◈ 활동명: 안전 그림책\n\n◈ 활동명: 손 지문\n- 활동목표: 찍는다.',
               'pm_cell_4': '[역할·쌓기]\n◈ 활동명: 병원 놀이',
               'safety_check': '물기 닦기'}
        result = NS['apply_table_marks'](day, rows)
        # 실제 문서: 기호가 없는 놀이 칸(징검다리)도 (ㅇ), + 추가 활동(손 지문)은 기본 활동의 기호를 따릅니다.
        self.assertEqual(result['body_plan'].splitlines()[0], '◈ 활동명: 징검다리 (ㅇ)')
        self.assertEqual(result['role_plan'], '◈ 활동명: 병원 놀이 (ㅇ)')
        self.assertIn('◈ 활동명: 공 놀이 (x)', result['outdoor_am_plan'])
        self.assertIn('◈ 활동명: 볼링 (ㅇ)', result['outdoor_am_plan'])
        self.assertIn('◈ 활동명: 안전 그림책 (ㅇ)', result['pm_cell_2'])
        self.assertIn('◈ 활동명: 손 지문 (ㅇ)\n', result['pm_cell_2'])
        self.assertEqual(result['pm_cell_4'], '[역할·쌓기]\n◈ 활동명: 병원 놀이 (ㅇ)')
        self.assertEqual(result['safety_check'], '물기 닦기')
        self.assertIn('던진다.\n[미세먼지 · 우천시 대체활동]\n◈ 활동명: 볼링 (ㅇ)', result['outdoor_am_plan'])
        self.assertEqual(NS['apply_table_marks'](result, rows), result)

    def test_marks_are_normalized_and_safety_lines_lose_bullets(self):
        rows = weekly_day_contexts(weekly_hml())['5일(수)']
        day = {'morning_act_plan': '- 등원 인사\n◈ 활동명: 친구와 인사해요(ㅇ)',
               'role_plan': '◈ 활동명: 벽돌 블록(ㅇ)\n- 활동목표: 쌓는다.',
               'outdoor_am_plan': '◈ 활동명: 공 놀이\n[미세먼지 · 우천시 대체활동]\n◈ 활동명: 볼링',
               'safety_check': '◈ 물기 닦기(ㅇ)\n- 청결점검'}
        result = NS['apply_table_marks'](day, rows)
        # 그날 칸에 기호가 있으면 ' (ㅇ)' 형식으로 정리하고, 기호가 없는 놀이 칸도 실제 문서처럼 (ㅇ)로 적습니다.
        self.assertEqual(result['morning_act_plan'], '- 등원 인사\n◈ 활동명: 친구와 인사해요 (ㅇ)')
        self.assertEqual(result['role_plan'], '◈ 활동명: 벽돌 블록 (ㅇ)\n- 활동목표: 쌓는다.')
        self.assertEqual(result['outdoor_am_plan'],
                         '◈ 활동명: 공 놀이 (x)\n[미세먼지 · 우천시 대체활동]\n◈ 활동명: 볼링 (ㅇ)')
        self.assertEqual(result['safety_check'], '물기 닦기 (ㅇ)\n청결점검 (ㅇ)')

    def test_alternative_activity_mark_is_opposite_of_outdoor_mark(self):
        # 실제 문서 24일치: 실외 (ㅇ)이면 대체 (x), 실외 (x)이면 대체 (ㅇ). 주안 대체 칸의 (ㅇ) 반복 기호보다 우선합니다.
        contexts = weekly_day_contexts(weekly_hml())
        day = {'outdoor_am_plan': '◈ 활동명: 공 놀이\n[미세먼지 · 우천시 대체활동]\n◈ 활동명: 볼링'}
        monday = NS['apply_table_marks'](day, contexts['3일(월)'])
        self.assertEqual(monday['outdoor_am_plan'],
                         '◈ 활동명: 공 놀이 (ㅇ)\n[미세먼지 · 우천시 대체활동]\n◈ 활동명: 볼링 (x)')
        tuesday = NS['apply_table_marks'](day, contexts['4일(화)'])
        self.assertEqual(tuesday['outdoor_am_plan'],
                         '◈ 활동명: 공 놀이 (x)\n[미세먼지 · 우천시 대체활동]\n◈ 활동명: 볼링 (ㅇ)')

    def test_nap_row_has_no_evaluation_prompt_but_daily_does(self):
        result = NS['add_evaluation_prompts']({'nap_plan': '◈ 낮잠음악 [love me]\n- 돕는다.', 'nap_eval': '',
                                               'body_plan': '◈ 활동명: 공 놀이', 'body_eval': ''})
        self.assertEqual(result['nap_eval'], '')
        self.assertIn('[실행·평가 기록 전]', result['body_eval'])
        self.assertIn('[일과평가 기록 전]', result['daily_eval'])

    def test_lunch_row_plus_safety_education_goes_under_nap_wake_routine(self):
        # 실제 11월 주안: 점심·낮잠 칸 '+ [성폭력 예방교육] 배변 후 ...' → 낮잠 깨기 및 기저귀 갈기 일과 아래 상세 계획.
        title = '[성폭력 예방교육] 배변 후 도움받아 바지 입어보기'
        data = weekly_hml().decode('utf-8').replace('(ㅇ)\n+놀잇감을 정리해요(중점)', '(ㅇ)\n+ ' + title)
        rows = weekly_day_contexts(data.encode('utf-8'))['5일(수)']
        activities = NS['required_activities_from_table'](rows)
        self.assertEqual(activities['nap_wake_plan'], [title])
        self.assertNotIn('lunch_plan', activities)
        response = {'goals': ['바지를 입어 본다.', '도움을 받아 시도한다.'], 'curriculum_ids': ['C001'], 'materials': [],
                    'steps': [{'action': '바지를 살펴본다.', 'speech': ['바지를 입어볼까?']},
                              {'action': '한쪽씩 다리를 넣어본다.', 'speech': ['선생님이 도와줄게.']}]}
        request = Mock(return_value=response)
        with patch.dict(NS, {'generate_with_fallback': request}):
            result = NS['repair_nap_wake_plan']({}, activities, 'key', '', '', Mock(), {})
        self.assertTrue(result['nap_wake_plan'].startswith('- 낮잠을 깬 영아의 기저귀를 확인하고 갈아준다.'))
        self.assertIn('◈ 활동명: ' + title, result['nap_wake_plan'])
        self.assertIn('T: 바지를 입어볼까?', result['nap_wake_plan'])
        self.assertEqual(request.call_count, 1)
        # 실제 11월 5·6일 문서: 다음 날부터는 같은 칸에 '◈ 활동명: ...' 제목 한 줄만 이어 적었습니다.
        memory = {}
        first, carried = NS['carry_nap_wake_addition'](activities, memory)
        self.assertEqual((first, carried), (activities, []))
        later, carried = NS['carry_nap_wake_addition']({'body_plan': ['x']}, memory)
        self.assertEqual((later['nap_wake_plan'], carried), ([title], [title]))
        with patch.dict(NS, {'generate_with_fallback': request}):
            titled = NS['repair_nap_wake_plan']({}, later, 'key', '', '', Mock(), {}, carried)
        self.assertTrue(titled['nap_wake_plan'].endswith('\n\n◈ 활동명: ' + title))
        self.assertNotIn('활동목표', titled['nap_wake_plan'])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(NS['carry_nap_wake_addition']({'body_plan': ['x']}, None), ({'body_plan': ['x']}, []))
        # 저장 단계의 일상생활 보정과 최종 문서에서도 유지됩니다.
        self.assertEqual(NS['fill_routine_plans'](result)['nap_wake_plan'], result['nap_wake_plan'])
        document = NS['build_hwp_from_template']((ROOT / 'template.hml').read_text(encoding='utf-8'), result)
        self.assertIn(title, NS['extract_text_from_hwp_bytes'](document))
        # AI가 일상생활 칸에 임의로 쓴 활동은 여전히 기본 안내로 되돌립니다.
        self.assertNotIn('활동명', NS['fill_routine_plans']({'nap_wake_plan': plan('임의 활동')})['nap_wake_plan'])

    def test_empty_safety_cell_is_filled_from_the_table_and_marked(self):
        contexts = weekly_day_contexts(weekly_hml())
        # 화요일 칸은 기호가 없어 그대로, 수요일은 '(ㅇ)' 반복 기호를 이어받아 기호가 붙습니다.
        tuesday = NS['apply_table_marks'](NS['apply_table_safety']({'safety_check': ''}, contexts['4일(화)']), contexts['4일(화)'])
        self.assertEqual(tuesday['safety_check'], '물기 닦기')
        wednesday = NS['apply_table_marks'](NS['apply_table_safety']({'safety_check': ''}, contexts['5일(수)']), contexts['5일(수)'])
        self.assertEqual(wednesday['safety_check'], '물기 닦기 (ㅇ)')
        kept = NS['apply_table_safety']({'safety_check': '청결점검'}, contexts['5일(수)'])
        self.assertEqual(kept['safety_check'], '청결점검')
        # AI가 행 이름을 내용처럼 적은 줄은 지우고, 그래서 비게 되면 표에서 채웁니다.
        labelled = NS['apply_table_safety']({'safety_check': '기본생활 및 안전\n친구에게 인사하기'}, contexts['5일(수)'])
        self.assertEqual(labelled['safety_check'], '친구에게 인사하기')
        only_label = NS['apply_table_safety']({'safety_check': '- 기본생활 및 안전:'}, contexts['5일(수)'])
        self.assertEqual(only_label['safety_check'], '물기 닦기')
        # 실제 10월 14일 결과: AI가 '활동명: 스스로 로션짜서 발라보기'처럼 머리말을 붙였습니다.
        headed = NS['apply_table_safety']({'safety_check': '◈ 활동명: 스스로 로션짜서 발라보기'}, contexts['5일(수)'])
        self.assertEqual(headed['safety_check'], '스스로 로션짜서 발라보기')

    def test_plan_lines_are_indented_like_the_edited_documents(self):
        # 10·11월 편집본 측정값: 목표·세부내용 둘째 줄 공백 11칸(44+36건), '1.' 1칸(98건), 'T:' 2칸(236건), 나머지 0칸.
        value = ('- 등원 안내\n\n◈ 활동명: 공 굴리기 (ㅇ)\n- 활동목표: 공을 탐색한다.\n  친구와 굴린다.\n'
                 '- 세부내용: C001\n- 활동자료: 공\n- 활동방법\n1. 공을 살펴본다.\nT: 무엇이 보이니?\n'
                 '[미세먼지 · 우천시 대체활동]\n◈ 활동명: 실내 공놀이')
        result = NS['finalize_activity_plans']({'outdoor_am_plan': value})['outdoor_am_plan']
        lines = result.splitlines()
        self.assertEqual(lines[0], '- 등원 안내')
        self.assertEqual(lines[4], ' ' * 11 + '친구와 굴린다.')
        self.assertTrue(lines[5].startswith('- 세부내용: 신체운동'))
        self.assertEqual(lines[8], ' 1. 공을 살펴본다.')
        self.assertEqual(lines[9], '  T: 무엇이 보이니?')
        self.assertEqual(lines[10], '[미세먼지 · 우천시 대체활동]')
        self.assertEqual(NS['finalize_activity_plans']({'outdoor_am_plan': result})['outdoor_am_plan'], result)
        two = NS['indent_plan_lines']('- 세부내용: 가\n  나\n  다\n- 활동자료: 없음')
        self.assertEqual(two, '- 세부내용: 가\n' + ' ' * 11 + '나\n' + ' ' * 11 + '다\n- 활동자료: 없음')

    def test_marks_missing_the_opening_bracket_are_still_marks(self):
        # 실제 9월 4주 주안 오타 '자동차 막대 인형으로 놀이해요ㅇ)'가 결과에 '놀이해요ㅇ) (ㅇ)'로 찍혔습니다.
        self.assertEqual(NS['titles_from_cell']('자동차 막대 인형으로 놀이해요ㅇ)'), ['자동차 막대 인형으로 놀이해요'])
        self.assertEqual(NS['activity_name']('◈ 활동명: 자동차 막대 인형으로 놀이해요ㅇ)'), '자동차막대인형으로놀이해요')
        self.assertEqual(NS['cell_mark']('자동차 막대 인형으로 놀이해요ㅇ)'), 'ㅇ')
        self.assertEqual(NS['cell_mark']('비닐 풍선을 잡아보아요×)'), 'x')
        self.assertEqual(NS['add_marks']('◈ 활동명: 자동차 막대 인형으로 놀이해요ㅇ)', 'ㅇ', {}),
                         '◈ 활동명: 자동차 막대 인형으로 놀이해요 (ㅇ)')

    def test_afternoon_titles_snap_to_the_weekly_cell_text(self):
        # 실제 10월 14일 결과: AI가 '[장애인식 개선교육]:...' 앞의 '['를 빼고 돌려줘 새 활동으로 취급됐습니다.
        rows = [{'area': '오후활동 실내', 'original': '(ㅇ)\n+ 동물 징검다리 건너보기',
                 'inherited': '[장애인식 개선교육]:우리 모두 친구가 될 수 있어요] 그림책 보기(ㅇ)'}]
        afternoon = {'pm_cell_1': ['동물 징검다리  건너보기'], 'pm_cell_2': ['장애인식 개선교육]:우리 모두 친구가 될 수 있어요] 그림책 보기'],
                     'pm_cell_3': [], 'pm_cell_4': []}
        result = NS['snap_afternoon_titles'](afternoon, rows)
        self.assertEqual(result['pm_cell_2'], ['[장애인식 개선교육]:우리 모두 친구가 될 수 있어요] 그림책 보기'])
        self.assertEqual(result['pm_cell_1'], ['동물 징검다리 건너보기'])
        self.assertEqual(NS['table_title_only'](rows, result)['pm_cell_2'], result['pm_cell_2'])
        unknown = {'pm_cell_1': [], 'pm_cell_2': ['전혀 다른 활동'], 'pm_cell_3': [], 'pm_cell_4': []}
        self.assertEqual(NS['snap_afternoon_titles'](unknown, rows), unknown)
        self.assertEqual(NS['snap_afternoon_titles'](afternoon, []), afternoon)

    def test_clearly_physical_afternoon_activity_goes_to_the_body_slot(self):
        # 실제 9월 4주: 교통안전교육 '횡단보도 걸어보기'는 [신체]에 적혔습니다. 그림책·화보 보기는 그대로 [언어]입니다.
        afternoon = {'pm_cell_1': [], 'pm_cell_2': ['교통안전교육 : [건너가는 길] 노래 들으며 횡단보도 걸어보기'],
                     'pm_cell_3': [], 'pm_cell_4': ['한복을 입어요(사전)']}
        result = NS['reassign_afternoon_slots'](afternoon)
        self.assertEqual(result['pm_cell_1'], ['교통안전교육 : [건너가는 길] 노래 들으며 횡단보도 걸어보기'])
        self.assertEqual(result['pm_cell_2'], [])
        self.assertEqual(result['pm_cell_4'], ['한복을 입어요(사전)'])
        kept = {'pm_cell_1': [], 'pm_cell_2': ['인터넷중독 예방 및 해소 관련 교육 [꼭! 꼭! 약속해요] 화보보기'],
                'pm_cell_3': [], 'pm_cell_4': []}
        self.assertEqual(NS['reassign_afternoon_slots'](kept), kept)

    def test_afternoon_activity_keeps_its_first_slot_across_days(self):
        memory = {}
        monday = NS['stabilize_afternoon_slots'](
            {'pm_cell_1': [], 'pm_cell_2': ['안전 그림책'], 'pm_cell_3': [], 'pm_cell_4': []}, memory)
        self.assertEqual(monday['pm_cell_2'], ['안전 그림책'])
        tuesday = NS['stabilize_afternoon_slots'](
            {'pm_cell_1': ['안전 그림책'], 'pm_cell_2': [], 'pm_cell_3': ['손 지문'], 'pm_cell_4': []}, memory)
        self.assertEqual(tuesday, {'pm_cell_1': [], 'pm_cell_2': ['안전 그림책'], 'pm_cell_3': ['손 지문'], 'pm_cell_4': []})
        self.assertEqual(NS['stabilize_afternoon_slots'](tuesday, None), tuesday)

    def test_goal_lines_are_joined_to_label_without_bullets(self):
        value = '◈ 활동명: X\n- 활동목표:\n· 하나를 한다.\n· 둘을 경험한다.\n- 세부내용: C001\n- 활동자료: 없음'
        self.assertEqual(NS['normalize_goal_lines'](value),
                         '◈ 활동명: X\n- 활동목표: 하나를 한다.\n  둘을 경험한다.\n- 세부내용: C001\n- 활동자료: 없음')
        kept = '◈ 활동명: X\n- 활동목표: 하나를 한다.\n  둘을 경험한다.\n- 세부내용: C001'
        self.assertEqual(NS['normalize_goal_lines'](kept), kept)

    def test_nap_title_uses_weekly_cell_instead_of_reference(self):
        rows = weekly_day_contexts(weekly_hml())['7일(금)']
        result = NS['apply_table_nap_title']({'nap_plan': '◈ 낮잠음악 [다른 음악] (ㅇ)\n- 휴식을 돕는다.'}, rows)
        # 수기 문서처럼 제목 뒤에 그날 칸의 실행기호를 붙입니다(금요일 칸 '(ㅇ)').
        self.assertIn('◈ 낮잠동화 [사이좋게 지내자] (ㅇ)\n', result['nap_plan'])
        thursday = NS['apply_table_nap_title']({'nap_plan': '- 휴식을 돕는다.'}, weekly_day_contexts(weekly_hml())['6일(목)'])
        self.assertEqual(thursday['nap_plan'], '◈ 낮잠동화 [사이좋게 지내자]\n- 휴식을 돕는다.')
        self.assertNotIn('다른 음악', result['nap_plan'])
        self.assertIn('- 휴식을 돕는다.', result['nap_plan'])

    def test_nap_title_with_colon_is_not_duplicated(self):
        rows = weekly_day_contexts(weekly_hml())['7일(금)']
        plan = '◈ 낮잠동화 [사이좋게 지내자]\n낮잠동화: [사이좋게 지내자]\n- 휴식을 돕는다.'
        result = NS['apply_table_nap_title']({'nap_plan': plan}, rows)
        self.assertEqual(result['nap_plan'].count('사이좋게 지내자'), 1)
        self.assertEqual(result['nap_plan'], '◈ 낮잠동화 [사이좋게 지내자] (ㅇ)\n- 휴식을 돕는다.')
        self.assertEqual(NS['apply_table_nap_title'](result, rows), result)
        # 실제 배포 결과(9월 1일)에 있던 '[낮잠음악] 제목' 꼴의 중복 줄도 지웁니다.
        bracketed = '◈ 낮잠동화 [사이좋게 지내자]\n[낮잠동화] 사이좋게 지내자\n- 휴식을 돕는다.\n- 낮잠 잘 준비를 하고 낮잠 동화를 듣는다.'
        result = NS['apply_table_nap_title']({'nap_plan': bracketed}, rows)
        self.assertEqual(result['nap_plan'], '◈ 낮잠동화 [사이좋게 지내자] (ㅇ)\n- 휴식을 돕는다.\n- 낮잠 잘 준비를 하고 낮잠 동화를 듣는다.')
        # 실제 10월 15일 결과: '- 낮잠동화 [사이좋게 지내자]' 줄이 제목 아래 한 번 더 있었습니다.
        dashed = NS['apply_table_nap_title']({'nap_plan': '◈ 낮잠동화 [사이좋게 지내자] (ㅇ)\n- 낮잠동화 [사이좋게 지내자]\n- 휴식을 돕는다.'}, rows)
        self.assertEqual(dashed['nap_plan'], '◈ 낮잠동화 [사이좋게 지내자] (ㅇ)\n- 휴식을 돕는다.')

    def test_date_line_keeps_the_template_spacing(self):
        document = NS['build_hwp_from_template']((ROOT / 'template.hml').read_text(encoding='utf-8'),
                                                 {'date_str': '2026년 9월 1일 화요일'})
        self.assertIn('■ 일 시:  2026년 9월 1일 화요일', NS['extract_text_from_hwp_bytes'](document))

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
