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

# 시트 컬럼 구조 (기존 DB와 동일)
COLUMNS = ["No.", "date", "day", "situation", "level1", "level2", "level3", "mommyvoca"]


def get_credentials() -> Credentials:
    """서비스 계정 인증 정보를 가져옵니다."""
    # 1. 환경 변수에서 JSON 문자열로 시도
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")

    if creds_json:
        creds_dict = json.loads(creds_json)
        return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)

    # 2. Streamlit secrets에서 시도
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'GOOGLE_SHEETS_CREDENTIALS' in st.secrets:
            creds_json = st.secrets['GOOGLE_SHEETS_CREDENTIALS']
            if isinstance(creds_json, str):
                creds_dict = json.loads(creds_json)
            else:
                creds_dict = dict(creds_json)
            return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except Exception:
        pass

    # 3. 로컬 파일에서 시도
    local_path = os.path.join(os.path.dirname(__file__), "docs", "klarity-482204-b2cb4fe72848.json")
    if os.path.exists(local_path):
        return Credentials.from_service_account_file(local_path, scopes=SCOPES)

    raise ValueError("Google Sheets 인증 정보를 찾을 수 없습니다.")


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

        # 첫 번째 시트에 헤더 추가
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
        next_row = len(all_values) + 1
        next_no = len(all_values)  # 헤더 제외

        # 요일 계산
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        day_str = weekdays[dt.weekday()]

        # 새 행 데이터
        new_row = [
            next_no,           # No.
            target_date,       # date
            day_str,           # day
            topic,             # situation
            level1_text,       # level1
            level2_text,       # level2
            level3_text,       # level3
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
    """시트의 모든 콘텐츠를 가져옵니다."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1
        all_values = worksheet.get_all_values()

        if len(all_values) <= 1:
            return []

        headers = all_values[0]
        contents = []
        for i, row in enumerate(all_values[1:], start=2):  # 행 번호는 2부터
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
        return []


def delete_content(row_number: int, spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB") -> dict:
    """특정 행의 콘텐츠를 삭제합니다."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1
        worksheet.delete_rows(row_number)
        return {'success': True, 'row': row_number}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def update_content(
    row_number: int,
    level1_text: str,
    level2_text: str,
    level3_text: str,
    spreadsheet_name: str = "마미톡잉글리시 콘텐츠 DB"
) -> dict:
    """특정 행의 콘텐츠를 업데이트합니다."""
    try:
        spreadsheet = get_or_create_spreadsheet(spreadsheet_name)
        worksheet = spreadsheet.sheet1
        worksheet.update(f'E{row_number}:G{row_number}', [[level1_text, level2_text, level3_text]])
        return {'success': True, 'row': row_number}
    except Exception as e:
        return {'success': False, 'error': str(e)}


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
