"""
Google Sheets 연동 모듈

생성된 콘텐츠를 Google Sheets에 자동 저장합니다.
"""

import json
import os
from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

# 스코프 설정
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# 시트 컬럼 구조 (가독성 개선 버전)
# 각 레벨을 en/kr/child로 분리하여 셀당 하나의 정보만 저장
COLUMNS = [
    "No.", "date", "day", "situation",
    "level1_en", "level1_kr",
    "level2_en", "level2_kr", "level2_child",
    "level3_en", "level3_kr", "level3_child",
    "mommyvoca"
]

# 레거시 컬럼 (기존 형식)
LEGACY_COLUMNS = ["No.", "date", "day", "situation", "level1", "level2", "level3", "mommyvoca"]


def parse_level_text(level_text: str) -> dict:
    """레벨 텍스트를 en, kr, child로 분리합니다.

    Args:
        level_text: "1️⃣ English...\n한국어...\n2️⃣ ..." 형식

    Returns:
        {
            "en": "Let's go! | Put on shoes. | Ready?",
            "kr": "가자! | 신발 신어. | 준비됐어?",
            "child": "Yes! / 응! | Ready! / 준비됐어!"  # 없으면 빈 문자열
        }
    """
    import re

    if not level_text or level_text.strip() == "":
        return {"en": "", "kr": "", "child": ""}

    # ⭐ 기준으로 엄마 파트와 아이 파트 분리
    parts = level_text.split("⭐")
    mom_part = parts[0].strip()
    child_part = parts[1].strip() if len(parts) > 1 else ""

    # 엄마 파트 파싱 (1️⃣, 2️⃣, 3️⃣ 패턴)
    en_sentences = []
    kr_sentences = []

    # 이모지 넘버링으로 분리
    emoji_pattern = re.compile(r'[1-3]️⃣')
    segments = emoji_pattern.split(mom_part)

    for seg in segments[1:]:  # 첫 번째는 빈 문자열이므로 스킵
        lines = [l.strip() for l in seg.strip().split('\n') if l.strip()]
        if lines:
            en_sentences.append(lines[0])  # 첫 줄: 영어
            if len(lines) > 1:
                kr_sentences.append(lines[1])  # 둘째 줄: 한국어

    en_str = " | ".join(en_sentences)
    kr_str = " | ".join(kr_sentences)

    # 아이 파트 파싱
    child_str = ""
    if child_part and "생략" not in child_part:
        # {아이이름}: 제거
        child_part = re.sub(r'\{아이이름\}:\s*', '', child_part)
        lines = [l.strip() for l in child_part.split('\n') if l.strip()]

        # 영어/한국어 쌍으로 묶기
        child_pairs = []
        for i in range(0, len(lines), 2):
            en = lines[i] if i < len(lines) else ""
            kr = lines[i + 1] if i + 1 < len(lines) else ""
            if en or kr:
                child_pairs.append(f"{en} / {kr}")

        child_str = " | ".join(child_pairs)

    return {"en": en_str, "kr": kr_str, "child": child_str}


def get_credentials() -> Credentials:
    """서비스 계정 인증 정보를 가져옵니다."""
    errors = []

    # 1. 환경 변수에서 JSON 문자열로 시도
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

    if creds_json:
        try:
            creds_dict = json.loads(creds_json)
            return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except Exception as e:
            errors.append(f"환경변수 파싱 실패: {e}")

    # 2. Streamlit secrets에서 시도
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'GOOGLE_SHEETS_CREDENTIALS' in st.secrets:
            creds_data = st.secrets['GOOGLE_SHEETS_CREDENTIALS']
            if isinstance(creds_data, str):
                creds_dict = json.loads(creds_data)
            else:
                # Streamlit secrets에서 dict 또는 AttrDict로 올 수 있음
                creds_dict = dict(creds_data)
            return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        else:
            errors.append("Streamlit secrets에 GOOGLE_SHEETS_CREDENTIALS 키 없음")
    except json.JSONDecodeError as e:
        errors.append(f"Streamlit secrets JSON 파싱 실패: {e}")
    except Exception as e:
        errors.append(f"Streamlit secrets 읽기 실패: {e}")

    # 3. 로컬 파일에서 시도
    local_path = os.path.join(os.path.dirname(__file__), "docs", "klarity-482204-b2cb4fe72848.json")
    if os.path.exists(local_path):
        try:
            return Credentials.from_service_account_file(local_path, scopes=SCOPES)
        except Exception as e:
            errors.append(f"로컬 파일 로드 실패: {e}")
    else:
        errors.append(f"로컬 파일 없음: {local_path}")

    raise ValueError(f"Google Sheets 인증 정보를 찾을 수 없습니다. 시도한 방법들: {'; '.join(errors)}")


def get_client() -> gspread.Client:
    """gspread 클라이언트를 반환합니다."""
    creds = get_credentials()
    return gspread.authorize(creds)


def get_or_create_spreadsheet(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> gspread.Spreadsheet:
    """스프레드시트를 가져오거나 새로 생성합니다."""
    client = get_client()

    try:
        # 기존 스프레드시트 찾기
        spreadsheet = client.open(spreadsheet_name)
    except gspread.SpreadsheetNotFound:
        # 새로 생성
        spreadsheet = client.create(spreadsheet_name)

        # 첫 번째 시트에 헤더 추가 (새 컬럼 구조: 13개)
        worksheet = spreadsheet.sheet1
        worksheet.update('A1:M1', [COLUMNS])

        # 헤더 스타일 (볼드)
        worksheet.format('A1:M1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
        })

        # 열 너비 조정
        worksheet.set_basic_filter()

    return spreadsheet


def append_content(
    topic: str,
    target_date: str,
    level1_text: str,
    level2_text: str,
    level3_text: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """새 콘텐츠를 시트에 추가합니다.

    Args:
        topic: 주제명 (situation)
        target_date: 발송일 (YYYY-MM-DD)
        level1_text: 레벨1 admin_text
        level2_text: 레벨2 admin_text
        level3_text: 레벨3 admin_text
        spreadsheet_name: 스프레드시트 이름

    Returns:
        {'success': True, 'row': 10, 'url': 'https://...'}
    """
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1

        # 현재 행 수 (다음 번호 계산)
        all_values = worksheet.get_all_values()

        # 중복 체크: 같은 날짜의 콘텐츠가 이미 있으면 저장하지 않음
        for row in all_values[1:]:  # 헤더 제외
            if len(row) > 1 and row[1] == target_date:
                # 이미 해당 날짜에 콘텐츠 존재
                existing_no = row[0] if row else "?"
                return {
                    'success': True,
                    'row': all_values.index(row) + 1,
                    'no': existing_no,
                    'url': spreadsheet.url,
                    'duplicate': True,
                    'message': f'이미 {target_date} 날짜에 콘텐츠가 존재합니다 (No.{existing_no})'
                }

        next_row = len(all_values) + 1
        next_no = len(all_values)  # 헤더 제외

        # 요일 계산
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        day_str = weekdays[dt.weekday()]

        # 각 레벨 텍스트 파싱
        l1 = parse_level_text(level1_text)
        l2 = parse_level_text(level2_text)
        l3 = parse_level_text(level3_text)

        # 새 행 데이터 (새 컬럼 구조: 13개)
        new_row = [
            next_no,           # No.
            target_date,       # date
            day_str,           # day
            topic,             # situation
            l1["en"],          # level1_en
            l1["kr"],          # level1_kr
            l2["en"],          # level2_en
            l2["kr"],          # level2_kr
            l2["child"],       # level2_child
            l3["en"],          # level3_en
            l3["kr"],          # level3_kr
            l3["child"],       # level3_child
            ""                 # mommyvoca (Canva에서 추가)
        ]

        # 행 추가
        worksheet.append_row(new_row, value_input_option='USER_ENTERED')

        return {
            'success': True,
            'row': next_row,
            'no': next_no,
            'url': spreadsheet.url
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def get_spreadsheet_url(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> Optional[str]:
    """스프레드시트 URL을 반환합니다."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        return spreadsheet.url
    except Exception:
        return None


def share_spreadsheet(email: str, spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> bool:
    """스프레드시트를 특정 이메일과 공유합니다."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        spreadsheet.share(email, perm_type='user', role='writer')
        return True
    except Exception:
        return False


def get_all_contents(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> list:
    """시트의 모든 콘텐츠를 가져옵니다 (새 컬럼 구조)."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1
        all_values = worksheet.get_all_values()

        if len(all_values) == 0:
            return []

        # 첫 행이 헤더인지 확인
        first_row = all_values[0]
        has_header = first_row and first_row[0] == "No."

        if has_header:
            data_rows = all_values[1:]
            start_row = 2
        else:
            print("헤더 없음 - 헤더 행 삽입 중...")
            worksheet.insert_row(COLUMNS, 1)
            data_rows = all_values
            start_row = 2

        # 컬럼 수로 신규/레거시 구분 (13개 = 신규, 8개 = 레거시)
        is_new_format = len(first_row) >= 13 and "level1_en" in first_row

        contents = []
        for i, row in enumerate(data_rows, start=start_row):
            if not row or not row[0]:
                continue

            if is_new_format:
                # 새 컬럼 구조 (13개)
                content = {
                    "row_number": i,
                    "no": row[0] if len(row) > 0 else "",
                    "date": row[1] if len(row) > 1 else "",
                    "day": row[2] if len(row) > 2 else "",
                    "situation": row[3] if len(row) > 3 else "",
                    "level1_en": row[4] if len(row) > 4 else "",
                    "level1_kr": row[5] if len(row) > 5 else "",
                    "level2_en": row[6] if len(row) > 6 else "",
                    "level2_kr": row[7] if len(row) > 7 else "",
                    "level2_child": row[8] if len(row) > 8 else "",
                    "level3_en": row[9] if len(row) > 9 else "",
                    "level3_kr": row[10] if len(row) > 10 else "",
                    "level3_child": row[11] if len(row) > 11 else "",
                    "mommyvoca": row[12] if len(row) > 12 else ""
                }
            else:
                # 레거시 컬럼 구조 (8개)
                content = {
                    "row_number": i,
                    "no": row[0] if len(row) > 0 else "",
                    "date": row[1] if len(row) > 1 else "",
                    "day": row[2] if len(row) > 2 else "",
                    "situation": row[3] if len(row) > 3 else "",
                    "level1": row[4] if len(row) > 4 else "",
                    "level2": row[5] if len(row) > 5 else "",
                    "level3": row[6] if len(row) > 6 else "",
                    "mommyvoca": row[7] if len(row) > 7 else ""
                }
            contents.append(content)

        return contents
    except Exception as e:
        print(f"get_all_contents 에러: {e}")
        raise


def delete_content(row_number: int, spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> dict:
    """특정 행의 콘텐츠를 삭제하고, 월간 기획에서도 상태를 pending으로 변경합니다."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1

        # 삭제 전에 해당 행의 날짜 정보 가져오기
        row_data = worksheet.row_values(row_number)
        deleted_date = row_data[1] if len(row_data) > 1 else None

        # 행 삭제
        worksheet.delete_rows(row_number)

        # 월간 기획에서 해당 날짜의 상태를 pending으로 변경
        if deleted_date:
            sync_result = sync_monthly_plan_with_sheet(spreadsheet_name)

        return {
            'success': True,
            'row': row_number,
            'deleted_date': deleted_date,
            'plan_synced': True
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def sync_monthly_plan_with_sheet(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> dict:
    """시트의 실제 콘텐츠와 월간 기획의 상태를 동기화합니다.

    - 시트에 있는 콘텐츠: completed
    - 시트에 없는 콘텐츠: pending (재생성 가능)
    """
    try:
        # 시트의 실제 콘텐츠 날짜 목록
        contents = get_all_contents(spreadsheet_name)
        sheet_dates = {c['date'] for c in contents if c.get('date')}

        # 저장된 모든 월의 기획 확인
        saved_months = get_all_saved_months(spreadsheet_name)

        updated_months = []
        for month_info in saved_months:
            month = month_info['month']
            topics = load_monthly_plan_from_sheets(month, spreadsheet_name)

            if not topics:
                continue

            changed = False
            for topic in topics:
                date = topic.get('date', '')
                current_status = topic.get('status', 'pending')

                if date in sheet_dates:
                    # 시트에 있으면 completed
                    if current_status != 'completed':
                        topic['status'] = 'completed'
                        changed = True
                else:
                    # 시트에 없으면 pending (재생성 가능)
                    if current_status == 'completed':
                        topic['status'] = 'pending'
                        changed = True

            if changed:
                save_monthly_plan_to_sheets(month, topics, spreadsheet_name)
                updated_months.append(month)

        return {
            'success': True,
            'synced_months': updated_months,
            'sheet_dates': list(sheet_dates)
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def update_content(
    row_number: int,
    level1_text: str,
    level2_text: str,
    level3_text: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """특정 행의 콘텐츠를 업데이트합니다 (새 컬럼 구조)."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1

        # 각 레벨 텍스트 파싱
        l1 = parse_level_text(level1_text)
        l2 = parse_level_text(level2_text)
        l3 = parse_level_text(level3_text)

        # 새 컬럼 구조로 업데이트 (E~L 컬럼, 8개)
        worksheet.update(f'E{row_number}:L{row_number}', [[
            l1["en"], l1["kr"],
            l2["en"], l2["kr"], l2["child"],
            l3["en"], l3["kr"], l3["child"]
        ]])
        return {'success': True, 'row': row_number}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def migrate_to_new_format(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> dict:
    """기존 레거시 형식을 새 컬럼 구조로 마이그레이션합니다.

    기존: No.|date|day|situation|level1|level2|level3|mommyvoca (8개)
    신규: No.|date|day|situation|level1_en|level1_kr|level2_en|level2_kr|level2_child|level3_en|level3_kr|level3_child|mommyvoca (13개)
    """
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1
        all_values = worksheet.get_all_values()

        if len(all_values) == 0:
            return {'success': True, 'migrated': 0, 'message': '데이터 없음'}

        # 이미 새 형식인지 확인
        header = all_values[0]
        if len(header) >= 13 and "level1_en" in header:
            return {'success': True, 'migrated': 0, 'message': '이미 새 형식입니다'}

        # 헤더 업데이트
        worksheet.update('A1:M1', [COLUMNS])
        worksheet.format('A1:M1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
        })

        # 각 데이터 행 마이그레이션
        migrated_count = 0
        for i, row in enumerate(all_values[1:], start=2):
            if not row or not row[0]:
                continue

            # 기존 데이터 추출
            no = row[0] if len(row) > 0 else ""
            date = row[1] if len(row) > 1 else ""
            day = row[2] if len(row) > 2 else ""
            situation = row[3] if len(row) > 3 else ""
            level1_text = row[4] if len(row) > 4 else ""
            level2_text = row[5] if len(row) > 5 else ""
            level3_text = row[6] if len(row) > 6 else ""
            mommyvoca = row[7] if len(row) > 7 else ""

            # 파싱
            l1 = parse_level_text(level1_text)
            l2 = parse_level_text(level2_text)
            l3 = parse_level_text(level3_text)

            # 새 형식으로 업데이트
            new_row = [
                no, date, day, situation,
                l1["en"], l1["kr"],
                l2["en"], l2["kr"], l2["child"],
                l3["en"], l3["kr"], l3["child"],
                mommyvoca
            ]
            worksheet.update(f'A{i}:M{i}', [new_row])
            migrated_count += 1

        return {
            'success': True,
            'migrated': migrated_count,
            'message': f'{migrated_count}개 행 마이그레이션 완료'
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


def add_content_raw(
    no: int,
    date: str,
    day: str,
    topic: str,
    level1_en: str,
    level1_kr: str,
    level2_en: str,
    level2_kr: str,
    level2_child: str,
    level3_en: str,
    level3_kr: str,
    level3_child: str,
    mommyvoca: str = "",
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """새 컬럼 구조로 직접 콘텐츠를 추가합니다 (복구용)."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1

        new_row = [
            no, date, day, topic,
            level1_en, level1_kr,
            level2_en, level2_kr, level2_child,
            level3_en, level3_kr, level3_child,
            mommyvoca
        ]

        worksheet.append_row(new_row, value_input_option='USER_ENTERED')

        return {'success': True, 'no': no}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================
# 월간 기획 저장/로드 (Google Sheets 기반)
# ============================================================

PLANS_SHEET_NAME = "monthly_plans"
PLANS_COLUMNS = ["month", "created_at", "topics_json"]


def get_or_create_plans_worksheet(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"):
    """월간 기획 시트를 가져오거나 생성합니다."""
    spreadsheet = get_or_create_spreadsheet(spreadsheet_name)

    try:
        worksheet = spreadsheet.worksheet(PLANS_SHEET_NAME)
    except gspread.WorksheetNotFound:
        # 새 시트 생성
        worksheet = spreadsheet.add_worksheet(title=PLANS_SHEET_NAME, rows=100, cols=3)
        worksheet.update('A1:C1', [PLANS_COLUMNS])
        worksheet.format('A1:C1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.85, 'green': 0.92, 'blue': 1.0}
        })

    return worksheet


def save_monthly_plan_to_sheets(
    month: str,
    topics: list,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """월간 기획을 Google Sheets에 저장합니다.

    Args:
        month: 월 (YYYY-MM 형식)
        topics: 주제 리스트
        spreadsheet_name: 스프레드시트 이름

    Returns:
        {'success': True} or {'success': False, 'error': '...'}
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)

        # 기존 데이터 확인 (같은 월이 있으면 업데이트)
        all_values = worksheet.get_all_values()

        row_to_update = None
        for i, row in enumerate(all_values[1:], start=2):  # 헤더 제외
            if row and row[0] == month:
                row_to_update = i
                break

        # 데이터 준비
        created_at = datetime.now().isoformat()
        topics_json = json.dumps(topics, ensure_ascii=False)

        if row_to_update:
            # 기존 행 업데이트
            worksheet.update(f'A{row_to_update}:C{row_to_update}', [[month, created_at, topics_json]])
        else:
            # 새 행 추가
            worksheet.append_row([month, created_at, topics_json], value_input_option='USER_ENTERED')

        return {'success': True, 'month': month}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def load_monthly_plan_from_sheets(
    month: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> list:
    """Google Sheets에서 월간 기획을 로드합니다.

    Args:
        month: 월 (YYYY-MM 형식)
        spreadsheet_name: 스프레드시트 이름

    Returns:
        주제 리스트 (없으면 빈 리스트)
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        for row in all_values[1:]:  # 헤더 제외
            if row and row[0] == month:
                topics_json = row[2] if len(row) > 2 else "[]"
                return json.loads(topics_json)

        return []

    except Exception as e:
        print(f"월간 기획 로드 실패: {e}")
        return []


def delete_monthly_plan_from_sheets(
    month: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """Google Sheets에서 월간 기획을 삭제합니다.

    Args:
        month: 월 (YYYY-MM 형식)
        spreadsheet_name: 스프레드시트 이름

    Returns:
        {'success': True} or {'success': False, 'error': '...'}
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        for i, row in enumerate(all_values[1:], start=2):  # 헤더 제외
            if row and row[0] == month:
                worksheet.delete_rows(i)
                return {'success': True, 'month': month}

        return {'success': True, 'month': month, 'note': 'not found'}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_all_saved_months(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> list:
    """저장된 모든 월 목록을 반환합니다.

    Returns:
        [{'month': '2026-03', 'created_at': '...'}, ...]
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        months = []
        for row in all_values[1:]:  # 헤더 제외
            if row and row[0]:
                months.append({
                    'month': row[0],
                    'created_at': row[1] if len(row) > 1 else ''
                })

        return sorted(months, key=lambda x: x['month'], reverse=True)

    except Exception as e:
        return []


# === 테스트용 ===
if __name__ == "__main__":
    print("Google Sheets 연동 테스트")
    print("=" * 50)

    try:
        # 스프레드시트 생성/열기
        spreadsheet = get_or_create_spreadsheet()
        print(f"✅ 스프레드시트: {spreadsheet.title}")
        print(f"   URL: {spreadsheet.url}")

        # 테스트 데이터 추가
        result = append_content(
            topic="🧪 테스트 주제",
            target_date="2026-03-26",
            level1_text="1️⃣ Test level 1\n\n테스트 레벨1",
            level2_text="1️⃣ Test level 2\n\n테스트 레벨2",
            level3_text="1️⃣ Test level 3\n\n테스트 레벨3"
        )

        if result['success']:
            print(f"✅ 행 추가 성공: Row {result['row']}")
        else:
            print(f"❌ 행 추가 실패: {result['error']}")

    except Exception as e:
        print(f"❌ 에러: {e}")
