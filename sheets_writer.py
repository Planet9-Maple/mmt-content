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

# 시트 컬럼 구조 (원본 DB와 동일)
# level1/2/3에 전체 텍스트 저장 (영어+한국어+아이반응)
COLUMNS = ["No.", "date", "day", "situation", "level1", "level2", "level3", "mommyvoca"]


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

        # 첫 번째 시트에 헤더 추가 (원본 DB 형식: 8개)
        worksheet = spreadsheet.sheet1
        worksheet.update('A1:H1', [COLUMNS])

        # 헤더 스타일 (볼드)
        worksheet.format('A1:H1', {
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

        # 새 행 데이터 (원본 DB 형식: 8개)
        new_row = [
            next_no,           # No.
            target_date,       # date
            day_str,           # day
            topic,             # situation
            level1_text,       # level1 (전체 텍스트)
            level2_text,       # level2 (전체 텍스트)
            level3_text,       # level3 (전체 텍스트)
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

        contents = []
        for i, row in enumerate(data_rows, start=start_row):
            if not row or not row[0]:
                continue

            # 원본 DB 형식 (8개 컬럼)
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
    """특정 행의 콘텐츠를 업데이트합니다 (원본 DB 형식)."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1

        # 원본 형식으로 업데이트 (E~G 컬럼, 3개)
        worksheet.update(f'E{row_number}:G{row_number}', [[level1_text, level2_text, level3_text]])
        return {'success': True, 'row': row_number}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def migrate_to_original_format(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> dict:
    """분리된 컬럼 형식(13개)을 원본 DB 형식(8개)으로 마이그레이션합니다.

    분리 형식: No.|date|day|situation|level1_en|level1_kr|...|mommyvoca (13개)
    원본 형식: No.|date|day|situation|level1|level2|level3|mommyvoca (8개)
    """
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1
        all_values = worksheet.get_all_values()

        if len(all_values) == 0:
            return {'success': True, 'migrated': 0, 'message': '데이터 없음'}

        # 현재 형식 확인
        header = all_values[0]
        is_split_format = len(header) >= 13 and "level1_en" in header

        if not is_split_format:
            return {'success': True, 'migrated': 0, 'message': '이미 원본 형식입니다'}

        # 데이터 추출 및 변환
        converted_rows = []
        for row in all_values[1:]:
            if not row or not row[0]:
                continue

            no = row[0] if len(row) > 0 else ""
            date = row[1] if len(row) > 1 else ""
            day = row[2] if len(row) > 2 else ""
            situation = row[3] if len(row) > 3 else ""

            # 분리된 컬럼을 원본 형식으로 병합
            l1_en = row[4] if len(row) > 4 else ""
            l1_kr = row[5] if len(row) > 5 else ""
            l2_en = row[6] if len(row) > 6 else ""
            l2_kr = row[7] if len(row) > 7 else ""
            l2_child = row[8] if len(row) > 8 else ""
            l3_en = row[9] if len(row) > 9 else ""
            l3_kr = row[10] if len(row) > 10 else ""
            l3_child = row[11] if len(row) > 11 else ""
            mommyvoca = row[12] if len(row) > 12 else ""

            # 원본 형식으로 재구성
            def merge_level(en_parts, kr_parts, child_text=""):
                lines = []
                en_list = [s.strip() for s in en_parts.split("|")] if en_parts else []
                kr_list = [s.strip() for s in kr_parts.split("|")] if kr_parts else []

                for i, en in enumerate(en_list):
                    if en:
                        lines.append(f"{i+1}️⃣ {en}")
                lines.append("")
                for kr in kr_list:
                    if kr:
                        lines.append(kr)

                if child_text:
                    lines.append("")
                    lines.append("⭐ {아이이름}:")
                    # child_text 형식: "Yes! / 응! | Ready! / 준비됐어!"
                    pairs = [p.strip() for p in child_text.split("|")]
                    for pair in pairs:
                        if " / " in pair:
                            en_resp, kr_resp = pair.split(" / ", 1)
                            lines.append(en_resp.strip())
                            lines.append(kr_resp.strip())
                            lines.append("")

                return "\n".join(lines).strip()

            level1 = merge_level(l1_en, l1_kr, "")
            level2 = merge_level(l2_en, l2_kr, l2_child)
            level3 = merge_level(l3_en, l3_kr, l3_child)

            converted_rows.append([no, date, day, situation, level1, level2, level3, mommyvoca])

        # 시트 초기화 및 원본 형식으로 재작성
        worksheet.clear()
        worksheet.update('A1:H1', [COLUMNS])
        worksheet.format('A1:H1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
        })

        if converted_rows:
            worksheet.append_rows(converted_rows, value_input_option='USER_ENTERED')

        return {
            'success': True,
            'migrated': len(converted_rows),
            'message': f'{len(converted_rows)}개 행을 원본 형식으로 변환 완료'
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


def add_content_raw(
    no: int,
    date: str,
    day: str,
    topic: str,
    level1: str,
    level2: str,
    level3: str,
    mommyvoca: str = "",
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """원본 DB 형식으로 직접 콘텐츠를 추가합니다 (복구용)."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1

        new_row = [no, date, day, topic, level1, level2, level3, mommyvoca]

        worksheet.append_row(new_row, value_input_option='USER_ENTERED')

        return {'success': True, 'no': no}
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ============================================================
# 월간 기획 저장/로드 (Google Sheets 기반) - 새 구조
# 각 날짜별로 행 저장, 레벨별 맥락 컬럼 분리
# ============================================================

PLANS_SHEET_NAME = "monthly_plans"
# 새 컬럼 구조: 날짜별 행, 레벨별 맥락 분리
PLANS_COLUMNS = [
    "date",           # 날짜 (YYYY-MM-DD)
    "day",            # 요일 (월/화/수...)
    "topic",          # 주제명
    "status",         # pending/in_progress/completed
    "level1_context", # L1 맥락 (장면, 흐름, 엄마말, 아이반응, 학습포인트)
    "level2_context", # L2 맥락
    "level3_context", # L3 맥락
    "updated_at"      # 마지막 수정 시간
]


def get_or_create_plans_worksheet(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"):
    """월간 기획 시트를 가져오거나 생성합니다 (새 구조)."""
    spreadsheet = get_or_create_spreadsheet(spreadsheet_name)

    try:
        worksheet = spreadsheet.worksheet(PLANS_SHEET_NAME)
        # 기존 시트가 구 형식인지 확인 (3컬럼 = 구형식)
        header = worksheet.row_values(1)
        if len(header) <= 3 and header and header[0] == "month":
            # 구 형식 → 새 형식으로 마이그레이션
            migrate_plans_to_new_format(spreadsheet_name)
            worksheet = spreadsheet.worksheet(PLANS_SHEET_NAME)
    except gspread.WorksheetNotFound:
        # 새 시트 생성 (8컬럼)
        worksheet = spreadsheet.add_worksheet(title=PLANS_SHEET_NAME, rows=500, cols=8)
        worksheet.update('A1:H1', [PLANS_COLUMNS])
        worksheet.format('A1:H1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.85, 'green': 0.92, 'blue': 1.0}
        })

    return worksheet


def migrate_plans_to_new_format(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> dict:
    """구 형식(월별 JSON)을 새 형식(날짜별 행)으로 마이그레이션합니다."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.worksheet(PLANS_SHEET_NAME)
        all_values = worksheet.get_all_values()

        # 구 형식 데이터 추출
        old_data = []
        for row in all_values[1:]:
            if row and len(row) >= 3 and row[0]:
                try:
                    topics = json.loads(row[2])
                    old_data.extend(topics)
                except:
                    pass

        # 시트 초기화 (새 헤더)
        worksheet.clear()
        worksheet.update('A1:H1', [PLANS_COLUMNS])
        worksheet.format('A1:H1', {
            'textFormat': {'bold': True},
            'backgroundColor': {'red': 0.85, 'green': 0.92, 'blue': 1.0}
        })

        # 새 형식으로 데이터 추가
        if old_data:
            new_rows = []
            for t in old_data:
                new_rows.append([
                    t.get('date', ''),
                    t.get('day', ''),
                    t.get('topic', ''),
                    t.get('status', 'pending'),
                    t.get('level1_context', ''),
                    t.get('level2_context', ''),
                    t.get('level3_context', ''),
                    datetime.now().isoformat()
                ])
            if new_rows:
                worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')

        return {'success': True, 'migrated': len(old_data)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def save_monthly_plan_to_sheets(
    month: str,
    topics: list,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """월간 기획을 Google Sheets에 저장합니다 (새 구조: 날짜별 행).

    Args:
        month: 월 (YYYY-MM 형식)
        topics: 주제 리스트 [{date, day, topic, status, level1_context, ...}, ...]
        spreadsheet_name: 스프레드시트 이름

    Returns:
        {'success': True} or {'success': False, 'error': '...'}
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        # 해당 월의 기존 행 찾기 (삭제 후 재삽입)
        rows_to_delete = []
        for i, row in enumerate(all_values[1:], start=2):
            if row and row[0] and row[0].startswith(month):
                rows_to_delete.append(i)

        # 역순으로 삭제 (인덱스 밀림 방지)
        for row_num in reversed(rows_to_delete):
            worksheet.delete_rows(row_num)

        # 새 데이터 추가
        now = datetime.now().isoformat()
        new_rows = []
        for t in topics:
            new_rows.append([
                t.get('date', ''),
                t.get('day', ''),
                t.get('topic', ''),
                t.get('status', 'pending'),
                t.get('level1_context', ''),
                t.get('level2_context', ''),
                t.get('level3_context', ''),
                now
            ])

        if new_rows:
            worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')

        return {'success': True, 'month': month, 'count': len(new_rows)}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def load_monthly_plan_from_sheets(
    month: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> list:
    """Google Sheets에서 월간 기획을 로드합니다 (새 구조).

    Args:
        month: 월 (YYYY-MM 형식)
        spreadsheet_name: 스프레드시트 이름

    Returns:
        주제 리스트 (없으면 빈 리스트)
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        topics = []
        for row in all_values[1:]:  # 헤더 제외
            if row and row[0] and row[0].startswith(month):
                topics.append({
                    'date': row[0] if len(row) > 0 else '',
                    'day': row[1] if len(row) > 1 else '',
                    'topic': row[2] if len(row) > 2 else '',
                    'status': row[3] if len(row) > 3 else 'pending',
                    'level1_context': row[4] if len(row) > 4 else '',
                    'level2_context': row[5] if len(row) > 5 else '',
                    'level3_context': row[6] if len(row) > 6 else '',
                    'updated_at': row[7] if len(row) > 7 else ''
                })

        # 날짜순 정렬
        topics.sort(key=lambda x: x.get('date', ''))
        return topics

    except Exception as e:
        print(f"월간 기획 로드 실패: {e}")
        return []


def update_topic_context(
    date: str,
    level1_context: str = None,
    level2_context: str = None,
    level3_context: str = None,
    status: str = None,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """특정 날짜의 레벨별 맥락을 업데이트합니다.

    구조검토 승인 시 Claude 분석 내용 저장용.

    Args:
        date: 날짜 (YYYY-MM-DD)
        level1_context: L1 맥락 (장면, 흐름, 엄마말맥락, 아이반응, 학습포인트)
        level2_context: L2 맥락
        level3_context: L3 맥락
        status: 상태 변경 (선택)
        spreadsheet_name: 스프레드시트 이름
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        for i, row in enumerate(all_values[1:], start=2):
            if row and row[0] == date:
                # 업데이트할 값 준비
                updates = []
                if status is not None:
                    updates.append((f'D{i}', status))
                if level1_context is not None:
                    updates.append((f'E{i}', level1_context))
                if level2_context is not None:
                    updates.append((f'F{i}', level2_context))
                if level3_context is not None:
                    updates.append((f'G{i}', level3_context))
                updates.append((f'H{i}', datetime.now().isoformat()))

                # 일괄 업데이트
                for cell, value in updates:
                    worksheet.update(cell, value)

                return {'success': True, 'date': date, 'row': i}

        return {'success': False, 'error': f'{date} 날짜를 찾을 수 없습니다'}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def upsert_topic_status(
    date: str,
    topic: str,
    status: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """특정 날짜의 status를 업데이트합니다. 없으면 새로 추가합니다.

    Args:
        date: 날짜 (YYYY-MM-DD)
        topic: 주제명
        status: 상태 (pending, in_progress, completed)
        spreadsheet_name: 스프레드시트 이름

    Returns:
        {'success': True, 'action': 'updated'/'inserted'} or {'success': False, 'error': '...'}
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        # 해당 날짜 찾기
        for i, row in enumerate(all_values[1:], start=2):
            if row and row[0] == date:
                # 기존 행 업데이트 (status만)
                worksheet.update(f'D{i}', status)
                worksheet.update(f'H{i}', datetime.now().isoformat())
                return {'success': True, 'action': 'updated', 'date': date, 'row': i}

        # 없으면 새 행 추가
        dt = datetime.strptime(date, "%Y-%m-%d")
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        day_str = weekdays[dt.weekday()]

        new_row = [
            date,
            day_str,
            topic,
            status,
            '',  # level1_context
            '',  # level2_context
            '',  # level3_context
            datetime.now().isoformat()
        ]
        worksheet.append_row(new_row, value_input_option='USER_ENTERED')
        return {'success': True, 'action': 'inserted', 'date': date}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def delete_monthly_plan_from_sheets(
    month: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """Google Sheets에서 월간 기획을 삭제합니다 (새 구조: 해당 월의 모든 행 삭제).

    Args:
        month: 월 (YYYY-MM 형식)
        spreadsheet_name: 스프레드시트 이름

    Returns:
        {'success': True} or {'success': False, 'error': '...'}
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        # 해당 월의 모든 행 찾기
        rows_to_delete = []
        for i, row in enumerate(all_values[1:], start=2):
            if row and row[0] and row[0].startswith(month):
                rows_to_delete.append(i)

        # 역순으로 삭제
        for row_num in reversed(rows_to_delete):
            worksheet.delete_rows(row_num)

        return {'success': True, 'month': month, 'deleted_count': len(rows_to_delete)}

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_all_saved_months(spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> list:
    """저장된 모든 월 목록을 반환합니다 (새 구조: 날짜에서 월 추출).

    Returns:
        [{'month': '2026-03', 'count': 22}, ...]
    """
    try:
        worksheet = get_or_create_plans_worksheet(spreadsheet_name)
        all_values = worksheet.get_all_values()

        # 날짜에서 월 추출하여 집계
        month_counts = {}
        for row in all_values[1:]:  # 헤더 제외
            if row and row[0] and len(row[0]) >= 7:
                month = row[0][:7]  # "YYYY-MM" 추출
                month_counts[month] = month_counts.get(month, 0) + 1

        months = [{'month': m, 'count': c} for m, c in month_counts.items()]

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
