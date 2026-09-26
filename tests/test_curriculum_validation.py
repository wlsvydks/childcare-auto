import unittest
from test_documents import NS


class CurriculumTests(unittest.TestCase):
    def plan(self, details='C001', dialogue='T: 무엇이 보이니?'):
        return ('◈ 활동명: 그림을 살펴봐요\n- 활동목표: 그림에 관심을 가진다.\n'
                f'- 세부내용: {details}\n- 활동자료: 그림\n- 활동방법\n'
                f'1. 그림을 살펴본다.\n{dialogue}')

    def test_only_registered_text_is_inserted(self):
        result = NS['finalize_activity_plans']({'lang_plan': self.plan('C001, C002')})
        self.assertIn(NS['curriculum_catalog']()['C001'], result['lang_plan'])
        self.assertIn(NS['curriculum_catalog']()['C002'], result['lang_plan'])
        self.assertNotIn('C001', result['lang_plan'])
        self.assertIn('T: 무엇이 보이니?', result['lang_plan'])

    def test_fabricated_curriculum_and_unknown_ids_rejected(self):
        for details in ('C999', '기본생활>건강하게 생활하기>손을 깨끗이 씻는다',
                        'C001\n가짜 세부내용', ''):
            with self.subTest(details=details), self.assertRaises(ValueError):
                NS['finalize_activity_plans']({'lang_plan': self.plan(details)})

    def test_each_method_step_needs_teacher_dialogue(self):
        for dialogue in ('', 'T:', 'T: 무엇일까?\n2. 그림을 고른다.'):
            with self.subTest(dialogue=dialogue):
                result = NS['finalize_activity_plans']({'lang_plan': self.plan(dialogue=dialogue)})
                self.assertIn('T:', result['lang_plan'])
                if '2.' in dialogue:
                    self.assertIn('T:', result['lang_plan'].split('2.')[1])

    def test_existing_teacher_speech_is_preserved(self):
        plan = self.plan(dialogue='T: 어떤 그림이 마음에 드니?')
        self.assertEqual(NS['complete_teacher_dialogue'](plan),
                         NS['complete_teacher_dialogue'](NS['complete_teacher_dialogue'](plan)))
        self.assertIn('T: 어떤 그림이 마음에 드니?', NS['complete_teacher_dialogue'](plan))

    def test_empty_speech_does_not_swallow_next_step(self):
        plan = self.plan(dialogue='T:\n2. 공을 굴린다.\nT:')
        result = NS['finalize_activity_plans']({'morning_act_plan': plan})['morning_act_plan']
        self.assertIn('2. 공을 굴린다.', result)
        self.assertIn('T: 어느 쪽으로', result.split('2.')[1])

    def test_unnumbered_methods_and_alternate_teacher_prefixes(self):
        for method in ('그림을 살펴본다.', '1) 그림을 살펴본다.\n- T： 무엇이 보이니?',
                       '1. 그림을 살펴본다.\n교사: 그림을 볼까?'):
            plan = self.plan().split('- 활동방법')[0] + '- 활동방법\n' + method
            result = NS['finalize_activity_plans']({'lang_plan': plan})['lang_plan']
            self.assertIn('1. ', result)
            self.assertIn('T:', result)

    def test_generated_missing_speech_reaches_document_without_manual_input(self):
        import json
        from datetime import date
        from unittest.mock import Mock, patch
        from google.genai import types
        from test_documents import ROOT
        target = date(2026, 9, 21)
        request = Mock(return_value=[{'date_str': NS['day_label'](target),
                                    'morning_act_plan': self.plan(dialogue='')}])
        with patch.dict(NS, {'generate_with_fallback': request, 'types': types, 'json': json}):
            day = NS['analyze_and_generate']('key', b'', 'image/png', '', '', Mock(), target)
        document = NS['build_hwp_from_template']((ROOT / 'template.hml').read_text(encoding='utf-8'), day)
        self.assertIn('T: 무엇이 보이니?', NS['extract_text_from_hwp_bytes'](document))
        self.assertEqual(request.call_count, 1)

    def test_evaluation_notes_are_not_fabricated_observations(self):
        actual = '- 공을 반복해서 굴리는 모습이 나타남.'
        result = NS['add_evaluation_prompts']({
            'body_plan': '공 굴리기', 'body_eval': actual,
            'lang_plan': '그림 보기', 'lang_eval': ''})
        self.assertEqual(result['body_eval'], actual)
        self.assertIn('[실행·평가 기록 전]', result['lang_eval'])
        self.assertNotIn('나타남', result['lang_eval'])
        self.assertEqual(NS['add_evaluation_prompts'](result), result)


if __name__ == '__main__':
    unittest.main()
