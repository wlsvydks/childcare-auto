from pathlib import Path
p=Path('README.md')
s=p.read_text(encoding='utf-8').replace('`template.hml`, `routine_plans.json`입니다.', '`template.hml`, `routine_plans.json`, `curriculum_reference.json`입니다.').replace('이 네 파일','이 다섯 파일').replace('2026-09-26-r3','2026-09-26-r8')
s=s.replace('공식 기준의 정확한 세부내용을 반영하려면 교육 자료를 함께 올리세요.', '세부내용은 등록된 만 0~1세 4차 기준표 목록에서만 선택합니다. 다른 기준표를 업로드해도 등록 목록은 자동 변경되지 않습니다.')
s=s.replace('공식 세부내용은 첨부 자료에서 확인된 문구만 사용하도록 지시합니다. 실제 기록이 없는 평가는 빈칸으로 남기며, 미래형 지원 계획으로 대신 채우지 않습니다.', '세부내용은 `curriculum_reference.json`에 등록된 40개 원문 중 AI가 선택한 번호를 앱에서 치환합니다. 목록 밖의 문구와 번호는 거절합니다. 이 목록은 사용자 제공 만 0~1세 4차 기준표의 전사이며 최신판 자동 적용이 아닙니다. 상세 활동방법 각 단계의 T: 교사 발화 누락도 검사합니다. 실제 기록이 없는 평가는 [실행·평가 기록 전]이라는 작성 항목으로 표시하며 관찰 사실을 만들어 넣지 않습니다. 추가 실행·관찰 기록 입력란에 날짜·활동명과 실제 기록을 넣으면 해당 날짜 평가의 근거로 사용합니다.')
p.write_text(s,encoding='utf-8')
p=Path('app.py');s=p.read_text(encoding='utf-8').replace('실제 기록이 없는 평가는 빈칸으로 남습니다.', "실제 기록이 없는 평가는 '기록 전' 작성 항목으로 표시됩니다.")
p.write_text(s,encoding='utf-8')
