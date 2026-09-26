# 일일보육계획안 만들기

## GitHub / Streamlit 배포

실행에 필요한 파일은 `app.py`, `requirements.txt`, `template.hml`입니다.
이 세 파일을 함께 업데이트하고 Streamlit의 실행 파일은 `app.py`로 지정하세요.
`app1.py`, `make_template.py`, 실제 아동 정보가 있는 샘플 문서는 업로드할 필요가 없습니다.

Streamlit 앱 설정의 Secrets에 다음을 입력하세요. API 키를 GitHub에 올리지 마세요.

```toml
GEMINI_API_KEY = "발급받은 키"
```

기본적으로 계정에서 사용 가능한 정식 Flash 모델을 조회합니다. 모델을 직접 지정하려면
Secrets에 `GEMINI_MODEL = "사용 가능한 모델 ID"`를 추가하세요.
키가 설정되면 사용자는 파일만 올리면 됩니다. 키가 없으면 화면에서 임시 입력할 수 있습니다.

## 사용하는 방법

1. 표준보육과정 사진/PDF와 이번 주 실행주안(.hwp 또는 .hml)을 올립니다.
2. 문체 참고용 일일보육계획안은 필요한 경우에만 올립니다.
3. 초안 만들기를 누른 뒤 날짜·주제·요일별 활동을 원본과 대조합니다.
4. 전체 ZIP 또는 개별 .hml 파일을 다운로드합니다.
5. 한글의 **파일 → 열기**로 .hml을 열고 수정합니다. 필요하면 파일 형식을 전체 파일로 선택하세요.
6. 실제 관찰에 맞게 평가 칸을 작성하고 **다른 이름으로 저장 → 한글 문서(.hwp)**로 저장합니다.

출력은 한글 XML 문서(.hml)입니다. 확장자만 .hwp로 변경하지 마세요.
사용 중인 한글 버전에서 파일 열기, 편집, 저장, 인쇄 페이지 나눔을 최초 1회 확인하세요.
참고 문서를 바꿔도 출력 표는 `template.hml`에 등록된 양식을 사용합니다.
주안 표를 텍스트로 읽으므로 요일 연결과 반복 기호 해석은 반드시 확인하세요.
관찰·평가 내용은 자동으로 지어내지 않고 작성 안내를 넣습니다.
템플릿의 반 이름, 결재란, 출결 등 고정 항목은 필요한 경우 한글에서 수정하세요.

문서 내용은 Google Gemini로 전송됩니다. 아동 이름 등 개인정보를 지운 자료를 사용하세요.
암호·배포용 문서와 HWPX는 지원하지 않습니다. 한글에서 일반 HWP로 저장해서 올리세요.

## 로컬 실행 및 검증

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
python -m unittest discover -s tests
```

`make_template.py`는 Windows와 한글이 설치된 PC에서 양식을 다시 만들 때만 사용합니다.
재생성 시 입력 자리 누락을 검사하며, 배포 전에 테스트를 다시 실행하세요.

설정 참고: [Streamlit Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
