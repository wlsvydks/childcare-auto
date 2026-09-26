import os
import io
import json
import zipfile
import xml.etree.ElementTree as ET
import streamlit as st
from pypdf import PdfReader
from google import genai
from google.genai import types

# 클라우드 서버의 비밀 금고(Secrets)에서 API 키를 자동으로 가져옵니다.
API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# ---------------- 1. 한글 프로그램 없이 파일(.hwpx / .pdf) 텍스트 읽기 ----------------
def extract_text_without_hwp(uploaded_file):
    fname = uploaded_file.name.lower()
    raw_bytes = uploaded_file.getvalue()
    
    # PDF 파일인 경우
    if fname.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(raw_bytes))
        return "\n".join([page.extract_text() or "" for page in reader.pages])
        
    # HWPX 파일인 경우 (ZIP 내부 XML에서 텍스트 직접 추출)
    if zipfile.is_zipfile(io.BytesIO(raw_bytes)):
        texts = []
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
            for name in sorted(zf.namelist()):
                if name.startswith("Contents/section") and name.endswith(".xml"):
                    root = ET.fromstring(zf.read(name))
                    for elem in root.iter():
                        if elem.tag.endswith("}t") and elem.text:
                            texts.append(elem.text.strip())
        return "\n".join([t for t in texts if t])
        
    st.error(f"⚠️ '{uploaded_file.name}' 파일은 구형 .hwp 포맷입니다. 클라우드 서버에서 처리하려면 한글에서 [다른 이름으로 저장 -> .hwpx] 또는 [.pdf]로 저장해서 올려주세요!")
    st.stop()

# ---------------- 2. 한글 프로그램 없이 .hwpx 표(Table) 셀 직접 수정 ----------------
def get_cell_text(tc_elem):
    return "".join([t.text for t in tc_elem.iter() if t.tag.endswith("}t") and t.text]).strip()

def set_cell_multiline_text(tc_elem, new_text):
    """표 셀(tc)의 기존 문단을 지우고 줄바꿈이 적용된 새 텍스트를 넣습니다."""
    if not new_text:
        return
    sublist = next((ch for ch in tc_elem if ch.tag.endswith("}subList")), None)
    if sublist is None:
        return
    p_list = [ch for ch in sublist if ch.tag.endswith("}p")]
    if not p_list:
        return
        
    import copy
    template_p = copy.deepcopy(p_list[0])
    for p in p_list:
        sublist.remove(p)
        
    lines = str(new_text).replace("\r\n", "\n").strip().split("\n")
    for line in lines:
        new_p = copy.deepcopy(template_p)
        t_elems = [el for el in new_p.iter() if el.tag.endswith("}t")]
        if t_elems:
            t_elems[0].text = line.replace("- - ", "- ")
            for extra_t in t_elems[1:]:
                extra_t.text = ""
        sublist.append(new_p)

def build_hwpx_file(sample_hwpx_bytes, day_data):
    """원본 .hwpx의 표 구조를 분석해 요일별 내용을 채운 새 .hwpx 바이트를 반환합니다."""
    in_buf = io.BytesIO(sample_hwpx_bytes)
    out_buf = io.BytesIO()
    
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("Contents/section") and item.filename.endswith(".xml"):
                root = ET.fromstring(data)
                
                # 1) 상단 일시 텍스트 변경
                for elem in root.iter():
                    if elem.tag.endswith("}t") and elem.text and ("일 시:" in elem.text or "일시:" in elem.text):
                        elem.text = f"■ 일 시:  {day_data.get('date_str', '')}"
                
                # 2) 표(tbl) 내의 모든 행(tr)과 셀(tc) 순회하며 값 채우기
                for tbl in [el for el in root.iter() if el.tag.endswith("}tbl")]:
                    rows = [el for el in tbl if el.tag.endswith("}tr")]
                    for r_idx, tr in enumerate(rows):
                        cells = [el for el in tr if el.tag.endswith("}tc")]
                        for c_idx, tc in enumerate(cells):
                            txt = get_cell_text(tc).replace(" ", "")
                            
                            # 상단 주제/소주제/목표
                            if txt == "주제" and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("topic", ""))
                            elif txt == "소주제" and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("sub_topic", ""))
                            elif txt == "목표" and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("goal", ""))
                            elif "기본생활" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("safety_check", ""))
                            elif "일과평가" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("daily_eval", ""))
                                
                            # 시간 열 및 영역 라벨 매칭
                            elif "7:00" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("morning_care_plan", ""))
                            elif "8:00~8:50" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("morning_act_plan", ""))
                                if c_idx + 2 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 2], day_data.get("morning_act_eval", ""))
                            elif "8:50~9:20" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("snack_am_plan", ""))
                            elif txt == "신체" and c_idx + 2 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 2], day_data.get("body_plan", ""))
                                if c_idx + 3 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 3], day_data.get("body_eval", ""))
                            elif txt == "언어" and c_idx + 1 < len(cells):
                                target_idx = c_idx + 2 if "9:20" in get_cell_text(cells[c_idx + 1]) else c_idx + 1
                                if target_idx < len(cells):
                                    set_cell_multiline_text(cells[target_idx], day_data.get("lang_plan", ""))
                                if target_idx + 1 < len(cells):
                                    set_cell_multiline_text(cells[target_idx + 1], day_data.get("lang_eval", ""))
                            elif txt in ["감각·탐색", "감각탐색"] and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("sense_plan", ""))
                                if c_idx + 2 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 2], day_data.get("sense_eval", ""))
                            elif txt in ["역할·쌓기", "역할쌓기"] and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("role_plan", ""))
                                if c_idx + 2 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 2], day_data.get("role_eval", ""))
                            elif "10:30~11:20" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("outdoor_am_plan", ""))
                                if c_idx + 2 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 2], day_data.get("outdoor_am_eval", ""))
                            elif "11:20~11:30" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("lunch_clean_plan", ""))
                            elif "11:30~12:20" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("lunch_plan", ""))
                            elif "12:20~14:30" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("nap_plan", ""))
                                if c_idx + 2 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 2], day_data.get("nap_eval", ""))
                            elif "14:30~14:50" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("nap_wake_plan", ""))
                            elif "14:50~15:00" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("clean_pm_plan", ""))
                            elif "15:00~15:30" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("snack_pm_plan", ""))
                            elif "15:30~16:30" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("pm_cell_1", ""))
                                if c_idx + 2 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 2], day_data.get("pm_indoor_eval", ""))
                                if r_idx + 1 < len(rows) and len(rows[r_idx + 1]) > 0:
                                    set_cell_multiline_text(rows[r_idx + 1][0], day_data.get("pm_cell_2", ""))
                                if r_idx + 2 < len(rows) and len(rows[r_idx + 2]) > 0:
                                    set_cell_multiline_text(rows[r_idx + 2][0], day_data.get("pm_cell_3", ""))
                                if r_idx + 3 < len(rows) and len(rows[r_idx + 3]) > 0:
                                    set_cell_multiline_text(rows[r_idx + 3][0], day_data.get("pm_cell_4", ""))
                            elif "16:30~17:00" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("outdoor_pm_plan", ""))
                                if c_idx + 2 < len(cells):
                                    set_cell_multiline_text(cells[c_idx + 2], day_data.get("outdoor_pm_eval", ""))
                            elif "17:00~17:20" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("snack_extra_plan", ""))
                            elif "17:20~18:00" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("home_guide_plan", ""))
                            elif "18:00~20:00" in txt and c_idx + 1 < len(cells):
                                set_cell_multiline_text(cells[c_idx + 1], day_data.get("evening_care_plan", ""))

                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(item, data)
            
    return out_buf.getvalue()

# ---------------- 3. AI 생성 로직 (이전과 동일) ----------------
def analyze_and_generate(api_key, curriculum_bytes, mime_type, weekly_text, sample_daily_text, status_box):
    client = genai.Client(api_key=api_key.strip())
    prompt = f"""
    당신은 어린이집 만 1세 반 보육계획안 자동 작성 전문가입니다.
    첨부된 [표준보육과정 기준표 이미지]와 [실행주안 텍스트]를 분석하여,
    이번 주 평일(월~금 중 휴원일 제외) 각각의 일일보육계획안 전체 데이터를 JSON으로 생성하세요.
    [실행주안 텍스트]\n{weekly_text}\n[샘플 텍스트]\n{sample_daily_text}
    (출력 스키마: target_filename(확장자는 .hwpx로), date_str, topic, sub_topic, goal, morning_care_plan, morning_act_plan, morning_act_eval, snack_am_plan, body_plan, body_eval, lang_plan, lang_eval, sense_plan, sense_eval, role_plan, role_eval, outdoor_am_plan, outdoor_am_eval, lunch_clean_plan, lunch_plan, nap_plan, nap_eval, nap_wake_plan, clean_pm_plan, snack_pm_plan, pm_cell_1, pm_cell_2, pm_cell_3, pm_cell_4, pm_indoor_eval, outdoor_pm_plan, outdoor_pm_eval, snack_extra_plan, home_guide_plan, evening_care_plan, safety_check, daily_eval)
    """
    contents = [types.Part.from_bytes(data=curriculum_bytes, mime_type=mime_type), prompt]
    for model_name in ["gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.8-pro"]:
        try:
            status_box.info("🤖 AI가 요일별 보육계획안을 작성하고 있어요...")
            res = client.models.generate_content(model=model_name, contents=contents, config={"response_mime_type": "application/json"})
            return json.loads(res.text)
        except Exception:
            continue
    raise RuntimeError("AI 서버 연결 실패")

# ---------------- 4. UI 화면 ----------------
st.set_page_config(page_title="일일보육계획안 자동 생성기", layout="wide")
st.title("🌸 일일보육계획안 24시간 자동 작성 사이트")

col1, col2, col3 = st.columns(3)
with col1:
    f_curr = st.file_uploader("1️⃣ 교육 자료 (사진/PDF)", type=["jpg", "jpeg", "png", "pdf"])
with col2:
    f_week = st.file_uploader("2️⃣ 실행주안 파일 (.hwpx 또는 .pdf)", type=["hwpx", "pdf"])
with col3:
    f_daily = st.file_uploader("3️⃣ 일일보육계획안 샘플 (.hwpx)", type=["hwpx"])

if st.button("✨ 요일별 일일보육계획안 자동 만들기", use_container_width=True):
    if not (f_curr and f_week and f_daily):
        st.warning("3개의 파일을 모두 업로드해 주세요!")
    else:
        status_box = st.empty()
        week_text = extract_text_without_hwp(f_week)
        daily_text = extract_text_without_hwp(f_daily)
        days_data = analyze_and_generate(API_KEY, f_curr.getvalue(), f_curr.type or "image/png", week_text, daily_text, status_box)
        status_box.empty()
        
        generated = []
        for d in days_data:
            fname = d["target_filename"].replace(".hwp", ".hwpx")
            if not fname.endswith(".hwpx"):
                fname += ".hwpx"
            hwpx_bytes = build_hwpx_file(f_daily.getvalue(), d)
            generated.append((fname, hwpx_bytes))
        st.session_state["generated_files"] = generated

if "generated_files" in st.session_state:
    st.success("🎉 생성 완료! 아래 버튼을 눌러 바탕화면에 저장하세요.")
    for fname, fbytes in st.session_state["generated_files"]:
        st.download_button(f"📥 {fname} 다운로드", data=fbytes, file_name=fname)