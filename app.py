import os
import io
import re
import json
import zlib
import struct
import zipfile
import olefile
import streamlit as st
from xml.sax.saxutils import escape as xml_escape
from google import genai
from google.genai import types

# 클라우드 Secrets 또는 로컬 환경에서 API 키 가져오기
API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# ---------------- 1. 리눅스 클라우드에서 .hwp 파일 직접 해독 함수 ----------------
def extract_text_from_hwp_bytes(file_bytes):
    """한글 프로그램 없이 순수 파이썬으로 .hwp 바이너리 파일의 모든 텍스트를 추출합니다."""
    if not olefile.isOleFile(io.BytesIO(file_bytes)):
        # 혹시 HWPML이나 텍스트 기반 .hwp인 경우
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    ole = olefile.OleFileIO(io.BytesIO(file_bytes))
    header = ole.openstream("FileHeader").read()
    is_compressed = (header[36] & 1) != 0

    extracted_lines = []
    # BodyText/Section0, Section1... 순서대로 읽기
    for entry in ole.listdir():
        if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section"):
            raw = ole.openstream(entry).read()
            data = zlib.decompress(raw, -15) if is_compressed else raw
            
            pos = 0
            size = len(data)
            while pos < size:
                if pos + 4 > size:
                    break
                rec_header = struct.unpack_from("<I", data, pos)[0]
                tag_id = rec_header & 0x3FF
                rec_len = (rec_header >> 20) & 0xFFF
                pos += 4
                if rec_len == 0xFFF:
                    if pos + 4 > size:
                        break
                    rec_len = struct.unpack_from("<I", data, pos)[0]
                    pos += 4
                
                # HWPTAG_PARA_TEXT (67번 태그 = 문단 글자 데이터)
                if tag_id == 67:
                    rec_data = data[pos:pos + rec_len]
                    chars = []
                    idx = 0
                    while idx + 1 < len(rec_data):
                        code = struct.unpack_from("<H", rec_data, idx)[0]
                        if code in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23):
                            idx += 16  # 확장/인라인 컨트롤 문자(16바이트) 건너뛰기
                        elif code in (10, 13):
                            chars.append("\n")
                            idx += 2
                        elif code < 32:
                            idx += 2
                        else:
                            chars.append(chr(code))
                            idx += 2
                    line_str = "".join(chars).strip()
                    if line_str:
                        extracted_lines.append(line_str)
                pos += rec_len

    ole.close()
    return "\n".join(extracted_lines)

# ---------------- 2. 한글 프로그램 없이 .hwp 파일 생성 (template.hml 기반) ----------------
def build_hwp_from_template(template_hml_text, day_data):
    """추출해둔 한글 양식 틀(template.hml)에 요일별 데이터를 채워 .hwp 파일을 생성합니다."""
    out_hml = template_hml_text

    mapping = {
        "__DATE_STR__": day_data.get("date_str", ""),
        "__TOPIC__": day_data.get("topic", ""),
        "__SUB_TOPIC__": day_data.get("sub_topic", ""),
        "__GOAL__": day_data.get("goal", ""),
        "__MORNING_CARE_PLAN__": day_data.get("morning_care_plan", ""),
        "__MORNING_ACT_PLAN__": day_data.get("morning_act_plan", ""),
        "__MORNING_ACT_EVAL__": day_data.get("morning_act_eval", ""),
        "__SNACK_AM_PLAN__": day_data.get("snack_am_plan", ""),
        "__BODY_PLAN__": day_data.get("body_plan", ""),
        "__BODY_EVAL__": day_data.get("body_eval", ""),
        "__LANG_PLAN__": day_data.get("lang_plan", ""),
        "__LANG_EVAL__": day_data.get("lang_eval", ""),
        "__SENSE_PLAN__": day_data.get("sense_plan", ""),
        "__SENSE_EVAL__": day_data.get("sense_eval", ""),
        "__ROLE_PLAN__": day_data.get("role_plan", ""),
        "__ROLE_EVAL__": day_data.get("role_eval", ""),
        "__OUTDOOR_AM_PLAN__": day_data.get("outdoor_am_plan", ""),
        "__OUTDOOR_AM_EVAL__": day_data.get("outdoor_am_eval", ""),
        "__LUNCH_CLEAN_PLAN__": day_data.get("lunch_clean_plan", ""),
        "__LUNCH_PLAN__": day_data.get("lunch_plan", ""),
        "__NAP_PLAN__": day_data.get("nap_plan", ""),
        "__NAP_EVAL__": day_data.get("nap_eval", ""),
        "__NAP_WAKE_PLAN__": day_data.get("nap_wake_plan", ""),
        "__CLEAN_PM_PLAN__": day_data.get("clean_pm_plan", ""),
        "__SNACK_PM_PLAN__": day_data.get("snack_pm_plan", ""),
        "__PM_CELL_1__": day_data.get("pm_cell_1", ""),
        "__PM_CELL_2__": day_data.get("pm_cell_2", ""),
        "__PM_CELL_3__": day_data.get("pm_cell_3", ""),
        "__PM_CELL_4__": day_data.get("pm_cell_4", ""),
        "__PM_INDOOR_EVAL__": day_data.get("pm_indoor_eval", ""),
        "__OUTDOOR_PM_PLAN__": day_data.get("outdoor_pm_plan", ""),
        "__OUTDOOR_PM_EVAL__": day_data.get("outdoor_pm_eval", ""),
        "__SNACK_EXTRA_PLAN__": day_data.get("snack_extra_plan", ""),
        "__HOME_GUIDE_PLAN__": day_data.get("home_guide_plan", ""),
        "__EVENING_CARE_PLAN__": day_data.get("evening_care_plan", ""),
        "__SAFETY_CHECK__": day_data.get("safety_check", ""),
        "__DAILY_EVAL__": day_data.get("daily_eval", ""),
    }

    for token, val in mapping.items():
        clean_val = str(val or "").replace("\r\n", "\n").replace("- - ", "- ").strip()
        lines = clean_val.split("\n")
        
        if len(lines) <= 1:
            out_hml = out_hml.replace(token, xml_escape(clean_val))
        else:
            # 여러 줄인 경우 한글 문단(<P>...</P>) 태그를 줄 수만큼 복제하여 줄바꿈 완벽 유지
            pattern = re.compile(
                r'(<P\b[^>]*>(?:(?!</P>).)*?<CHAR>)' + re.escape(token) + r'(</CHAR>(?:(?!</P>).)*?</P>)',
                re.DOTALL
            )
            def repl(match):
                prefix, suffix = match.group(1), match.group(2)
                return "\n".join(f"{prefix}{xml_escape(line)}{suffix}" for line in lines)
            
            new_hml, count = pattern.subn(repl, out_hml)
            if count > 0:
                out_hml = new_hml
            else:
                out_hml = out_hml.replace(token, xml_escape(clean_val))

    return out_hml.encode("utf-8")

# ---------------- 3. AI 분석 및 생성 함수 ----------------
def get_available_models(client):
    candidate_models = ["gemini-3.8-flash-lite", "gemini-3.8-pro", "gemini-3.8-flash"]
    try:
        for m in client.models.list():
            name = m.name.replace("models/", "")
            if "gemini" in name and ("flash" in name or "pro" in name):
                if not any(x in name for x in ["tts", "image", "embedding", "vision"]):
                    if name not in candidate_models:
                        candidate_models.insert(0, name)
    except Exception:
        pass
    return candidate_models

def analyze_and_generate(api_key, curriculum_bytes, mime_type, weekly_text, sample_daily_text, status_box):
    client = genai.Client(api_key=api_key.strip())
    prompt = f"""
    당신은 어린이집 만 1세 반 보육계획안 자동 작성 전문가입니다.
    첨부된 [표준보육과정 기준표 이미지]와 [실행주안 텍스트]를 분석하여,
    이번 주 평일(월~금 중 휴원일 제외) 각각의 일일보육계획안 전체 데이터를 JSON으로 생성하세요.

    [실행주안 텍스트]
    {weekly_text}

    [일일보육계획안 샘플 텍스트 (문체 및 구성 참고용)]
    {sample_daily_text}

    [작성 시 절대 주의사항]
    1. 주안에서 요일 칸에 '(0)', '(ㅇ)', '(x)', '(=)' 등 기호나 화살표만 있으면 이전 요일의 활동명을 그대로 이어받으세요.
    2. '활동방법'을 작성할 때 절대로 `1. [탐색 단계]` 처럼 대괄호 제목을 적지 마세요!
    3. 각 활동의 계획(plan) 포맷:
       ◆ 활동명: [활동명] ([실행기호])
       - 활동목표: [목표 1]
                  [목표 2]
       - 세부내용: [표준보육과정 이미지의 '영역>내용범주>내용' 중 알맞은 것 1]
                  [표준보육과정 이미지의 '영역>내용범주>내용' 중 알맞은 것 2]
       - 활동자료: [필요 자료]
       - 활동방법
       1. [구체적인 탐색 행동 문장]
        T: [상호작용 발화 1]
        T: [상호작용 발화 2]
       2. [구체적인 놀이 행동 문장]
        T: [상호작용 발화 1]
        T: [상호작용 발화 2]

    [출력 JSON 스키마]
    [
      {{
        "target_filename": "2026년 X월 X일 (요일) 일일보육계획안.hwp",
        "date_str": "2026년 X월 X일 X요일",
        "topic": "주안의 주제",
        "sub_topic": "주안의 소주제",
        "goal": "주안의 목표",
        "morning_care_plan": "- 등원하는 영아들을 웃는 얼굴로 맞이하면서 반갑게 인사한다.\\n- 양육자와 인사를 나누고 교실로 들어온다.\\n- 영아의 기분과 건강 상태를 살피고, 체온을 측정한다.\\n- 자유롭게 놀이하도록 한다.\\n  - 잠이 덜 깬 영아는 조용한 영역에서 쉴 수 있도록 한다.",
        "morning_act_plan": "등원 및 조용한 놀이 계획 전체 텍스트",
        "morning_act_eval": "등원 및 조용한 놀이 실행 및 평가 텍스트",
        "snack_am_plan": "- 가지고 놀던 놀잇감을 정리한 후 화장실로 이동해 손을 씻는다.\\n- 손을 다 씻은 영아는 턱받이를 하고 교사와 함께 매트에 앉아 손유희를 하며 식사를 준비한다.\\n- 자유롭게 식사 자리에 앉아 식사를 하도록 한다.\\n- 식사를 마친 영아들은 교사와 함께 화장실로 이동해 세수와 손 씻기를 한다.\\n- 세수를 마친 영아들은 로션을 바른다.\\n- 영아의 기저귀를 확인하고 갈아준다.",
        "body_plan": "오전 신체 활동 계획 전체 텍스트",
        "body_eval": "오전 신체 실행 및 평가 텍스트",
        "lang_plan": "오전 언어 활동 계획 전체 텍스트",
        "lang_eval": "오전 언어 실행 및 평가 텍스트",
        "sense_plan": "오전 감각·탐색 활동 계획 전체 텍스트",
        "sense_eval": "오전 감각·탐색 실행 및 평가 텍스트",
        "role_plan": "오전 역할·쌓기 활동 계획 전체 텍스트",
        "role_eval": "오전 역할·쌓기 실행 및 평가 텍스트",
        "outdoor_am_plan": "오전 실외놀이 계획 + \\n\\n[미세먼지 · 우천시 대체활동]\\n + 대체활동 계획 전체 텍스트",
        "outdoor_am_eval": "오전 실외놀이 실행 및 평가 텍스트",
        "lunch_clean_plan": "- 정리노래를 틀어주고 함께 놀잇감을 정리한다.\\n- 정리를 마친 영아들은 화장실로 이동하여 손을 씻으며 점심 식사 준비를 한다.",
        "lunch_plan": "◆ 점심식사\\n- 영아는 교사의 도움을 받아 턱받이를 한 후 자리에 앉아 식사를 한다.\\n- 교사는 영아가 수저와 포크를 사용하여 밥을 먹을 수 있도록 돕는다.\\n- 오늘 나온 반찬에 대해 여러 상호작용을 하며 반찬을 골고루 먹어 볼 수 있도록 한다.\\n\\n◆ 양치하기 및 기저귀 갈기\\n- 식사를 먼저 마친 영아들은 턱받이를 벗고 화장실로 이동하여 교사의 도움을 받아 양치와 세수를 한다.\\n- 교사는 양치와 세수를 마친 영아들이 종이타월로 손과 얼굴을 닦고 로션을 바를 수 있도록 돕는다.\\n- 영아의 기저귀를 확인하고 갈아준다.",
        "nap_plan": "◆ 낮잠음악 또는 낮잠동화 [제목] (0)\\n- 교사는 이불을 깔아준 후 영아가 자신의 자리로 가서 누울 수 있도록 돕는다.\\n- 낮잠 잘 준비를 하고 낮잠 동화를 듣는다.\\n- 교사는 늦게 잠들거나 일찍 깨는 영아들이 매트 위에 누워 휴식을 하거나 조용한 놀이를 할 수 있도록 돕는다.",
        "nap_eval": "개별 영아 낮잠 관찰 코멘트",
        "nap_wake_plan": "- 낮잠을 깬 영아의 기저귀를 확인하고 갈아준다.\\n- 기저귀 갈이를 한 영아는 놀이 할 수 있도록 한다.\\n- 교사는 불을 켜고 블라인드를 올리고 창문을 연다.\\n- 교사는 일어난 영아들의 매트를 정리한다.\\n- 자고 일어나 헝클어진 머리를 빗거나 묶어준다.",
        "clean_pm_plan": "- 손 씻기\\n- 영아들은 교사와 함께 화장실에 가서 손을 씻는다.",
        "snack_pm_plan": "- 간식 먹을 준비를 마친 영아들이 자유롭게 자리를 앉을 수 있도록 한다.\\n- 영아는 교사의 도움을 받아 수저와 포크를 사용하여 먹는다.\\n- 간식 메뉴의 이름을 이야기 해주며 상호작용한다.",
        "pm_cell_1": "[신체]\\n◆ 활동명: (오전 신체 활동명과 동일) ( )",
        "pm_cell_2": "[언어]\\n + (오후 실내 안전교육 또는 오후 중점 활동 전체 계획 텍스트)",
        "pm_cell_3": "[감각·탐색]\\n◆ 활동명: (오전 감각·탐색 활동명과 동일) ( )",
        "pm_cell_4": "[역할·쌓기]\\n◆ 활동명: (오전 역할·쌓기 활동명과 동일) ( )",
        "pm_indoor_eval": "오후 실내놀이 실행 및 평가 텍스트",
        "outdoor_pm_plan": "오후 실외활동 계획 전체 텍스트",
        "outdoor_pm_eval": "오후 실외활동 실행 및 평가 텍스트",
        "snack_extra_plan": "- 영아는 화장실을 다녀온 후 손을 씻고 간식을 먹는다.\\n- 바르게 앉아서 간식을 먹는다.\\n- 다 먹은 후 화장실에서 손과 입을 깨끗하게 씻는다.",
        "home_guide_plan": "- 부모님이 오시면 오늘 하루 영아의 상태에 대해 부모님과 간단한 대화를 나누고, 하원 지도를 한다.",
        "evening_care_plan": "- 통합보육실로 이동하여 놀이를 한다.\\n- 부모님이 오시는 대로 귀가한다.",
        "safety_check": "청결점검 (0) 등 주안의 기본생활 및 안전 문구",
        "daily_eval": "하단 일과평가 및 아동지도 종합 평가 (4~5문장)"
      }}
    ]
    """
    contents = [types.Part.from_bytes(data=curriculum_bytes, mime_type=mime_type), prompt]
    for model_name in get_available_models(client):
        try:
            status_box.info("🤖 AI가 요일별 일일보육계획안(.hwp)을 작성하고 있어요... (약 30초 소요)")
            res = client.models.generate_content(
                model=model_name,
                contents=contents,
                config={"response_mime_type": "application/json"}
            )
            return json.loads(res.text)
        except Exception:
            continue
    raise RuntimeError("AI 서버 응답 실패: 잠시 후 다시 시도해 주세요.")

# ---------------- 4. UI 화면 (.hwp 직접 업로드 & .hwp 다운로드) ----------------
st.set_page_config(page_title="일일보육계획안 자동 생성기", layout="wide")
st.title("🌸 일일보육계획안 자동 작성 홈페이지")
st.caption("컴퓨터가 꺼져 있어도 24시간 언제든 .hwp 파일을 올리고 완성된 .hwp 파일을 다운로드할 수 있습니다!")

col1, col2, col3 = st.columns(3)
with col1:
    f_curr = st.file_uploader("1️⃣ 교육 자료 (표준보육과정 사진/PDF)", type=["jpg", "jpeg", "png", "pdf"])
with col2:
    f_week = st.file_uploader("2️⃣ 실행주안 파일 (.hwp)", type=["hwp"])
with col3:
    f_daily = st.file_uploader("3️⃣ 일일보육계획안 샘플 (.hwp)", type=["hwp"])

if st.button("✨ 요일별 일일보육계획안 (.hwp) 자동 만들기", use_container_width=True):
    if not (f_curr and f_week and f_daily):
        st.warning("3개의 파일을 모두 업로드해 주세요!")
    elif not os.path.exists("template.hml"):
        st.error("서버에 'template.hml' 파일이 없습니다. GitHub 저장소에 template.hml 파일을 함께 업로드해 주세요!")
    else:
        status_box = st.empty()
        with st.spinner("1단계: 업로드된 한글(.hwp) 파일을 읽는 중..."):
            week_text = extract_text_from_hwp_bytes(f_week.getvalue())
            daily_text = extract_text_from_hwp_bytes(f_daily.getvalue())
            with open("template.hml", "r", encoding="utf-8") as tf:
                template_hml_text = tf.read()

        with st.spinner("2단계: 요일별 보육계획안 내용을 생성 중..."):
            mime = f_curr.type if f_curr.type else "image/png"
            days_data = analyze_and_generate(API_KEY, f_curr.getvalue(), mime, week_text, daily_text, status_box)
            status_box.empty()

        with st.spinner("3단계: 요일별 한글(.hwp) 파일을 조립 중..."):
            generated_files = []
            for day_info in days_data:
                fname = day_info["target_filename"]
                if not fname.endswith(".hwp"):
                    fname += ".hwp"
                hwp_bytes = build_hwp_from_template(template_hml_text, day_info)
                generated_files.append((fname, hwp_bytes))

            st.session_state["generated_files"] = generated_files

if "generated_files" in st.session_state and st.session_state["generated_files"]:
    st.divider()
    st.success("🎉 생성 완료! 아래 버튼을 누르면 한글(.hwp) 파일이 다운로드됩니다.")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, fbytes in st.session_state["generated_files"]:
            zf.writestr(fname, fbytes)

    st.download_button(
        label="🎁 이번 주 일일보육계획안 전체 한 번에 다운로드 (.zip)",
        data=zip_buffer.getvalue(),
        file_name="이번주_일일보육계획안_모음.zip",
        mime="application/zip",
        use_container_width=True
    )

    cols = st.columns(len(st.session_state["generated_files"]))
    for idx, (fname, fbytes) in enumerate(st.session_state["generated_files"]):
        with cols[idx]:
            st.download_button(
                label=f"📄 {fname}",
                data=fbytes,
                file_name=fname,
                mime="application/x-hwp"
            )