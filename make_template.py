import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import win32com.client as win32

# ⭐ 여기에 평소 쓰시는 '일일보육계획안 샘플.hwp' 파일 이름을 정확히 적어주세요!
SAMPLE_HWP_NAME = "일일보육계획안 샘플.hwp"

def start_hwp():
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    hwp.XHwpWindows.Item(0).Visible = True
    hwp.SetMessageBoxMode(0x00010001)
    return hwp

def write_cell(hwp, text):
    hwp.HAction.Run("Cancel")
    hwp.HAction.Run("SelectAll")
    hwp.HAction.Run("Delete")
    pset_char = hwp.HParameterSet.HCharShape
    hwp.HAction.GetDefault("CharShape", pset_char.HSet)
    pset_char.TextColor = 0
    hwp.HAction.Execute("CharShape", pset_char.HSet)

    pset = hwp.HParameterSet.HInsertText
    hwp.HAction.GetDefault("InsertText", pset.HSet)
    pset.Text = text
    hwp.HAction.Execute("InsertText", pset.HSet)

def find_text_from_top(hwp, keyword_list, occurrence=1):
    for kw in keyword_list:
        hwp.HAction.Run("MoveDocBegin")
        found_count = 0
        for step in range(occurrence):
            pset = hwp.HParameterSet.HFindReplace
            hwp.HAction.GetDefault("RepeatFind", pset.HSet)
            pset.FindString = kw
            pset.IgnoreMessage = 1
            pset.Direction = 0
            if hwp.HAction.Execute("RepeatFind", pset.HSet):
                found_count += 1
                hwp.HAction.Run("Cancel")
                if step < occurrence - 1:
                    hwp.HAction.Run("MoveRight")
            else:
                break
        if found_count == occurrence:
            return True
    return False

def fill_by_time_col(hwp, time_str, plan_token, eval_token=None, occurrence=1):
    if not find_text_from_top(hwp, [time_str], occurrence=occurrence):
        return
    hwp.HAction.Run("TableRightCell")
    write_cell(hwp, plan_token)
    if eval_token:
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, eval_token)

def fill_by_label_top(hwp, labels, right_count, token):
    if not find_text_from_top(hwp, labels, occurrence=1):
        return
    for _ in range(right_count):
        hwp.HAction.Run("TableRightCell")
    write_cell(hwp, token)

if __name__ == "__main__":
    sample_path = os.path.abspath(SAMPLE_HWP_NAME)
    if not os.path.exists(sample_path):
        print(f"❌ '{SAMPLE_HWP_NAME}' 파일을 D:\\childcare_auto 폴더 안에 넣어주세요!")
        exit()

    hwp = start_hwp()
    hwp.Open(sample_path, "HWP", "forceopen:true;versionwarning:false")

    # 상단 날짜 및 주제 토큰 심기
    if find_text_from_top(hwp, ["일 시:", "일시:", "일 시 :", "일시 :"]):
        hwp.HAction.Run("MoveRight")
        hwp.HAction.Run("Select")
        hwp.HAction.Run("MoveLineEnd")
        hwp.HAction.Run("Delete")
        pset = hwp.HParameterSet.HInsertText
        hwp.HAction.GetDefault("InsertText", pset.HSet)
        pset.Text = "  __DATE_STR__"
        hwp.HAction.Execute("InsertText", pset.HSet)

    fill_by_label_top(hwp, ["주 제", "주제"], 1, "__TOPIC__")
    fill_by_label_top(hwp, ["소주제", "소 주 제"], 1, "__SUB_TOPIC__")
    fill_by_label_top(hwp, ["목 표", "목표"], 1, "__GOAL__")

    fill_by_time_col(hwp, "7:00", "__MORNING_CARE_PLAN__")
    fill_by_time_col(hwp, "8:00", "__MORNING_ACT_PLAN__", "__MORNING_ACT_EVAL__", occurrence=2)
    fill_by_time_col(hwp, "8:50", "__SNACK_AM_PLAN__", occurrence=2)

    if find_text_from_top(hwp, ["9:20"], occurrence=2):
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__BODY_PLAN__")
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__BODY_EVAL__")
        hwp.HAction.Run("TableLeftCell")

        hwp.HAction.Run("TableLowerCell")
        write_cell(hwp, "__LANG_PLAN__")
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__LANG_EVAL__")
        hwp.HAction.Run("TableLeftCell")

        hwp.HAction.Run("TableLowerCell")
        write_cell(hwp, "__SENSE_PLAN__")
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__SENSE_EVAL__")
        hwp.HAction.Run("TableLeftCell")

        hwp.HAction.Run("TableLowerCell")
        write_cell(hwp, "__ROLE_PLAN__")
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__ROLE_EVAL__")

    fill_by_time_col(hwp, "10:30", "__OUTDOOR_AM_PLAN__", "__OUTDOOR_AM_EVAL__", occurrence=2)
    fill_by_time_col(hwp, "11:20", "__LUNCH_CLEAN_PLAN__", occurrence=2)
    fill_by_time_col(hwp, "12:20", "__LUNCH_PLAN__", occurrence=1)
    fill_by_time_col(hwp, "12:20", "__NAP_PLAN__", "__NAP_EVAL__", occurrence=2)
    fill_by_time_col(hwp, "14:50", "__NAP_WAKE_PLAN__", occurrence=1)
    fill_by_time_col(hwp, "14:50", "__CLEAN_PM_PLAN__", occurrence=2)
    fill_by_time_col(hwp, "15:00", "__SNACK_PM_PLAN__", occurrence=2)

    if find_text_from_top(hwp, ["15:30"], occurrence=2):
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__PM_CELL_1__")
        hwp.HAction.Run("TableLowerCell")
        write_cell(hwp, "__PM_CELL_2__")
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__PM_INDOOR_EVAL__")
        hwp.HAction.Run("TableLeftCell")
        hwp.HAction.Run("TableLowerCell")
        write_cell(hwp, "__PM_CELL_3__")
        hwp.HAction.Run("TableLowerCell")
        write_cell(hwp, "__PM_CELL_4__")

    fill_by_time_col(hwp, "16:30", "__OUTDOOR_PM_PLAN__", "__OUTDOOR_PM_EVAL__", occurrence=2)
    fill_by_time_col(hwp, "17:00", "__SNACK_EXTRA_PLAN__", occurrence=2)
    fill_by_time_col(hwp, "17:20", "__HOME_GUIDE_PLAN__", occurrence=2)
    fill_by_time_col(hwp, "18:00", "__EVENING_CARE_PLAN__", occurrence=2)

    hwp.HAction.Run("MoveDocEnd")
    pset = hwp.HParameterSet.HFindReplace
    hwp.HAction.GetDefault("RepeatFind", pset.HSet)
    pset.FindString = "기본생활"
    pset.IgnoreMessage = 1
    pset.Direction = 1
    if hwp.HAction.Execute("RepeatFind", pset.HSet):
        hwp.HAction.Run("Cancel")
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__SAFETY_CHECK__")

    hwp.HAction.Run("MoveDocEnd")
    pset.FindString = "일과평가"
    if hwp.HAction.Execute("RepeatFind", pset.HSet):
        hwp.HAction.Run("Cancel")
        hwp.HAction.Run("TableRightCell")
        write_cell(hwp, "__DAILY_EVAL__")

    # ⭐ 클라우드 서버에서도 한글 표 서식을 100% 유지하는 HWPML2X 포맷으로 저장
    out_hml = os.path.abspath("template.hml")
    hwp.SaveAs(out_hml, "HWPML2X", "")
    hwp.Clear(1)
    hwp.Quit()
    # 검색 시 띄어쓰기가 달라도 주제와 목표가 빠지지 않도록 보완합니다.
    root = ET.parse(out_hml).getroot()
    for label, token in [("주제", "__TOPIC__"), ("목표", "__GOAL__")]:
        for row in root.iter("ROW"):
            cells = row.findall("CELL")
            if len(cells) >= 2 and "".join("".join(cells[0].itertext()).split()) == label:
                paragraphs = cells[1].find("PARALIST")
                for child in list(paragraphs):
                    paragraphs.remove(child)
                p = ET.SubElement(paragraphs, "P", {"ParaShape": "18", "Style": "0"})
                ET.SubElement(ET.SubElement(p, "TEXT", {"CharShape": "12"}), "CHAR").text = token
    content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    expected = set(re.findall(r"__[A-Z0-9_]+__", Path(__file__).with_name("app.py").read_text(encoding="utf-8")))
    actual = set(re.findall(r"__[A-Z0-9_]+__", content.decode("utf-8")))
    if expected - actual:
        raise RuntimeError(f"양식 생성 실패: 입력 자리 누락 {sorted(expected - actual)}. 이 양식은 배포하지 마세요.")
    Path(out_hml).write_bytes(content)
    print("✅ 'template.hml' 양식 추출이 완료되었습니다!")
