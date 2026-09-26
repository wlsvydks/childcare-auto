from pathlib import Path
p=Path('README.md')
s=p.read_text(encoding='utf-8').replace('2026-09-26-r8', '2026-09-26-r9').replace('상세 활동방법 각 단계의 T: 교사 발화 누락도 검사합니다.', '상세 활동방법에서 빠진 T: 교사 발화는 해당 단계의 행동에 맞는 제안 발화로 자동 보완합니다. 기존 발화는 유지하며 번호 없는 방법과 교사: 표기도 정리합니다. 관찰 사실이나 아동 반응을 새로 만들지 않습니다.')
p.write_text(s,encoding='utf-8')
