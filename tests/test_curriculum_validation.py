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
            with self.subTest(dialogue=dialogue), self.assertRaisesRegex(ValueError, '교사 발화'):
                NS['finalize_activity_plans']({'lang_plan': self.plan(dialogue=dialogue)})

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
