"""
마미톡잉글리시 콘텐츠 생성 UI

Streamlit 기반 웹 인터페이스
3개 프로바이더: Gemini(분석) → Claude(생성) → GPT(검수)

플로우:
1. 월간 주제 기획 - 한달치 주제 확정
2. 주제별 콘텐츠 생성 - 단계별 검토/피드백
3. 최종 확정 - Google Sheets 저장
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

import db_loader
import pipeline


# ============================================================
# 월간 기획 저장/로드 (Google Sheets 우선, 실패 시 로컬 파일)
# ============================================================

PLANS_DIR = Path(__file__).parent / "output" / "monthly_plans"
PLANS_DIR.mkdir(parents=True, exist_ok=True)


def _save_to_local(month: datetime, topics: list) -> bool:
    """로컬 파일로 저장 (백업용)."""
    try:
        filepath = PLANS_DIR / f"{month.strftime('%Y-%m')}.json"
        data = {
            "month": month.strftime("%Y-%m"),
            "created_at": datetime.now().isoformat(),
            "topics": topics
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _load_from_local(month: datetime) -> list:
    """로컬 파일에서 로드."""
    filepath = PLANS_DIR / f"{month.strftime('%Y-%m')}.json"
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("topics", [])
    except Exception:
        return []


def _delete_local(month: datetime) -> bool:
    """로컬 파일 삭제."""
    filepath = PLANS_DIR / f"{month.strftime('%Y-%m')}.json"
    if filepath.exists():
        filepath.unlink()
        return True
    return False


def save_monthly_plan(month: datetime, topics: list) -> bool:
    """월간 기획 저장 (Sheets 우선, 실패 시 로컬)."""
    month_str = month.strftime("%Y-%m")
    sheets_error = None

    # 1. Google Sheets 저장 시도
    try:
        import sheets_writer
        result = sheets_writer.save_monthly_plan_to_sheets(month_str, topics)
        if result.get("success"):
            # Sheets 성공 시 로컬에도 백업
            _save_to_local(month, topics)
            return True
        else:
            sheets_error = result.get("error", "알 수 없는 오류")
    except Exception as e:
        sheets_error = str(e)

    # 2. 로컬 저장 (폴백)
    if _save_to_local(month, topics):
        if sheets_error:
            st.warning(f"☁️ Sheets 연결 실패: {sheets_error}\n로컬에 저장됨 (이 컴퓨터에서만 접근 가능)")
        return True

    return False


def load_monthly_plan(month: datetime) -> list:
    """월간 기획 로드 (Sheets 우선, 실패 시 로컬)."""
    month_str = month.strftime("%Y-%m")

    # 1. Google Sheets에서 로드 시도
    try:
        import sheets_writer
        topics = sheets_writer.load_monthly_plan_from_sheets(month_str)
        if topics:
            return topics
    except Exception:
        pass  # Sheets 실패 시 로컬 시도

    # 2. 로컬에서 로드
    return _load_from_local(month)


def delete_monthly_plan(month: datetime) -> bool:
    """월간 기획 삭제 (Sheets + 로컬 모두)."""
    month_str = month.strftime("%Y-%m")

    # Sheets 삭제 시도
    try:
        import sheets_writer
        sheets_writer.delete_monthly_plan_from_sheets(month_str)
    except Exception:
        pass

    # 로컬 삭제
    _delete_local(month)
    return True


def check_plan_exists(month: datetime) -> bool:
    """해당 월의 저장된 기획이 있는지 확인."""
    topics = load_monthly_plan(month)
    return len(topics) > 0


# ============================================================
# API 상태 확인
# ============================================================

def check_api_status() -> dict:
    """각 API 키 설정 상태 확인."""
    status = {
        "gemini": {"configured": False, "key_preview": ""},
        "claude": {"configured": False, "key_preview": ""},
        "gpt": {"configured": False, "key_preview": ""},
        "sheets": {"configured": False, "key_preview": "", "working": False}
    }

    # Gemini (Google API)
    key = _get_api_key("GOOGLE_API_KEY")
    if key:
        status["gemini"]["configured"] = True
        status["gemini"]["key_preview"] = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"

    # Claude (Anthropic)
    key = _get_api_key("ANTHROPIC_API_KEY")
    if key:
        status["claude"]["configured"] = True
        status["claude"]["key_preview"] = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"

    # GPT (OpenAI)
    key = _get_api_key("OPENAI_API_KEY")
    if key:
        status["gpt"]["configured"] = True
        status["gpt"]["key_preview"] = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"

    # Google Sheets
    creds = _get_api_key("GOOGLE_SHEETS_CREDENTIALS")
    if creds:
        status["sheets"]["configured"] = True
        status["sheets"]["key_preview"] = "서비스 계정 설정됨"
    else:
        # 로컬 파일 확인
        local_path = Path(__file__).parent / "docs" / "klarity-482204-b2cb4fe72848.json"
        if local_path.exists():
            status["sheets"]["configured"] = True
            status["sheets"]["key_preview"] = "로컬 파일 사용"

    # Sheets 실제 연결 테스트 (캐싱)
    if status["sheets"]["configured"]:
        try:
            import sheets_writer
            # 간단한 연결 테스트 (시트 목록만 확인)
            sheets_writer.get_or_create_spreadsheet()
            status["sheets"]["working"] = True
        except Exception:
            status["sheets"]["working"] = False

    return status


def _get_api_key(key_name: str) -> str:
    """API 키를 환경 변수 또는 Streamlit secrets에서 가져옵니다."""
    # 1. 환경 변수에서 시도
    value = os.getenv(key_name)
    if value:
        return value

    # 2. Streamlit secrets에서 시도
    try:
        if hasattr(st, 'secrets') and key_name in st.secrets:
            return st.secrets[key_name]
    except Exception:
        pass

    return ""


def is_similar_topic(candidate: str, existing_topics: list) -> bool:
    """주제가 기존 주제들과 유사한지 체크.

    키워드 기반 간단한 유사도 체크.
    같은 핵심 키워드가 2개 이상 겹치면 유사로 판단.
    """
    if not existing_topics:
        return False

    # 이모지 제거하고 키워드 추출
    def extract_keywords(text):
        clean = re.sub(r'[^\w\s가-힣]', '', text)
        words = set(clean.split())
        # 짧은 단어 제외 (조사 등)
        return {w for w in words if len(w) >= 2}

    candidate_keywords = extract_keywords(candidate)

    for existing in existing_topics:
        existing_keywords = extract_keywords(existing)
        common = candidate_keywords & existing_keywords

        # 핵심 키워드 2개 이상 겹치면 유사
        if len(common) >= 2:
            return True

        # 정확히 같은 주제면 유사
        if candidate.strip() == existing.strip():
            return True

    return False


# 페이지 설정
st.set_page_config(
    page_title="마미톡잉글리시 콘텐츠 생성",
    page_icon="👶",
    layout="wide"
)

# 출력 디렉토리
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def init_session_state():
    """세션 상태 초기화."""
    # 앱 시작 시 Google Sheets에서 저장된 월 확인
    default_month = datetime.now().replace(day=1)
    default_topics = []

    if "planning_month" not in st.session_state:
        # 첫 로드 시 Sheets에서 가장 최근 저장된 월 로드
        try:
            import sheets_writer
            saved_months = sheets_writer.get_all_saved_months()
            if saved_months:
                # 가장 최근 저장된 월 사용
                latest = saved_months[-1]["month"]  # "2026-03" 형식
                default_month = datetime.strptime(latest, "%Y-%m")
                # 해당 월의 데이터도 미리 로드
                default_topics = sheets_writer.load_monthly_plan_from_sheets(latest)
        except Exception:
            pass  # Sheets 연결 실패 시 오늘 날짜 사용

    defaults = {
        # 앱 모드
        "app_mode": "planning",  # "planning", "generating", "management"

        # 월간 기획
        "planning_month": default_month,
        "planned_topics": default_topics,  # [{date, day, topic, status: planned/in_progress/completed}]

        # 콘텐츠 생성 (현재 작업 중인 주제)
        # 새 흐름: 0(시작) → 1(구조검토) → 2(콘텐츠+AI검수 검토) → 3(최종확정)
        "current_topic_idx": None,
        "gen_step": 0,  # 0: 시작, 1: 구조검토, 2: 콘텐츠+AI검수검토, 3: 최종확정
        "step2_result": None,  # 구조 설계 결과
        "step2_feedback": "",
        "step3_result": None,  # 문장 생성 결과
        "step4_result": None,  # AI 검수 결과 (영문 생성 직후 자동 실행)
        "selected_variants": {"level_1": "A", "level_2": "A", "level_3": "A"},

        # 기타
        "weather_note": "",
        "sheets_contents": [],
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main():
    init_session_state()

    st.title("👶 마미톡잉글리시 콘텐츠 생성기")

    # 프로바이더 파이프라인 표시
    st.markdown("""
    <div style="background: linear-gradient(90deg, #4285F4 0%, #7C3AED 50%, #10A37F 100%);
                padding: 8px 16px; border-radius: 8px; color: white; text-align: center; margin-bottom: 20px;">
        🔵 Gemini (주제) → 🟣 Claude (구조/생성) → 🟢 GPT (검수) → 👩‍💻 관리자 검토
    </div>
    """, unsafe_allow_html=True)

    # 사이드바
    with st.sidebar:
        st.header("📌 메뉴")

        mode_options = ["📅 월간 주제 기획", "✨ 콘텐츠 생성", "📋 콘텐츠 관리"]
        menu_to_mode = {
            "📅 월간 주제 기획": "planning",
            "✨ 콘텐츠 생성": "generating",
            "📋 콘텐츠 관리": "management"
        }
        mode_to_index = {
            "planning": 0,
            "generating": 1,
            "management": 2
        }

        # app_mode 기반으로 index 계산 (프로그래밍 방식 전환 지원)
        current_index = mode_to_index.get(st.session_state.app_mode, 0)

        # 라디오 버튼 (index 기반, key 사용 안함 - app_mode가 진실의 원천)
        selected_menu = st.radio(
            "작업 선택",
            mode_options,
            index=current_index,
            label_visibility="collapsed"
        )

        # 라디오 버튼 선택이 현재 모드와 다르면 업데이트
        new_mode = menu_to_mode.get(selected_menu, "planning")
        if new_mode != st.session_state.app_mode:
            st.session_state.app_mode = new_mode
            st.rerun()

        st.divider()

        # API 상태 표시
        st.caption("🔑 API 연결 상태")
        api_status = check_api_status()

        col_a, col_b = st.columns(2)
        with col_a:
            if api_status["gemini"]["configured"]:
                st.markdown("🔵 Gemini ✅")
            else:
                st.markdown("🔵 Gemini ❌")

            if api_status["claude"]["configured"]:
                st.markdown("🟣 Claude ✅")
            else:
                st.markdown("🟣 Claude ❌")

        with col_b:
            if api_status["gpt"]["configured"]:
                st.markdown("🟢 GPT ✅")
            else:
                st.markdown("🟢 GPT ❌")

            if api_status["sheets"]["configured"]:
                st.markdown("📊 Sheets ✅")
            else:
                st.markdown("📊 Sheets ❌")

        # API 미설정 경고
        missing_apis = []
        if not api_status["gemini"]["configured"]:
            missing_apis.append("GOOGLE_API_KEY")
        if not api_status["claude"]["configured"]:
            missing_apis.append("ANTHROPIC_API_KEY")
        if not api_status["gpt"]["configured"]:
            missing_apis.append("OPENAI_API_KEY")

        if missing_apis:
            with st.expander("⚠️ API 설정 필요", expanded=False):
                st.markdown(f"""
                **누락된 API 키:**
                {', '.join(missing_apis)}

                **설정 방법:**
                1. `.env` 파일에 추가
                2. 또는 Streamlit secrets 설정
                """)

        # 진행 상황 표시 (복습일 제외)
        if st.session_state.planned_topics:
            st.divider()
            st.caption("📊 진행 현황")
            # 복습일 제외한 콘텐츠만 계산
            content_topics = [t for t in st.session_state.planned_topics if not t.get("is_review", False)]
            total = len(content_topics)
            completed = sum(1 for t in content_topics if t.get("status") == "completed")
            st.progress(completed / total if total > 0 else 0)
            st.write(f"콘텐츠: {completed}/{total}")

    # 메인 영역
    if st.session_state.app_mode == "planning":
        render_planning_view()
    elif st.session_state.app_mode == "generating":
        render_generating_view()
    else:
        render_management_view()


# ============================================================
# 월간 주제 기획
# ============================================================

def render_planning_view():
    """월간 주제 기획 화면."""
    st.header("📅 월간 주제 기획")

    col1, col2 = st.columns([2, 1])

    with col1:
        # 월 선택
        selected_month = st.date_input(
            "기획할 월 선택",
            value=st.session_state.planning_month,
            help="해당 월의 첫째 날을 선택하세요"
        )
        new_month = datetime.combine(selected_month, datetime.min.time()).replace(day=1)

        # 월이 변경되면 저장된 기획 로드 시도
        if new_month != st.session_state.planning_month:
            st.session_state.planning_month = new_month
            # Google Sheets에서 저장된 기획 로드
            saved_topics = load_monthly_plan(new_month)
            if saved_topics:
                st.session_state.planned_topics = saved_topics
                st.toast(f"☁️ {new_month.strftime('%Y년 %m월')} Google Sheets에서 로드됨")
            else:
                st.session_state.planned_topics = []
            st.rerun()

    with col2:
        weather = st.text_input(
            "계절/날씨 참고 (선택)",
            value=st.session_state.weather_note,
            placeholder="예: 봄, 따뜻함"
        )
        st.session_state.weather_note = weather

    # 저장된 기획 존재 여부 확인 (Google Sheets에서)
    current_month = st.session_state.planning_month

    # 세션에 기획이 없으면 Sheets에서 로드 시도
    if not st.session_state.planned_topics:
        saved_topics = load_monthly_plan(current_month)
        if saved_topics:
            st.session_state.planned_topics = saved_topics

    st.divider()

    # 주제 리스트가 없으면 생성 버튼 표시
    if not st.session_state.planned_topics:
        st.info("📝 월간 주제를 생성하거나 직접 입력하세요.")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("🔵 Gemini에게 월간 주제 제안받기", type="primary", use_container_width=True):
                generate_monthly_topics()

        with col2:
            if st.button("✏️ 직접 입력하기", use_container_width=True):
                create_empty_monthly_topics()

    else:
        # Sheets에 저장되어 있는지 확인
        saved_plan_exists = check_plan_exists(current_month)
        if saved_plan_exists:
            st.success(f"☁️ {current_month.strftime('%Y년 %m월')} 기획이 Google Sheets에 저장되어 있습니다.")
        render_topic_list()


def generate_monthly_topics():
    """Gemini로 월간 주제 생성 (중복 방지 포함)."""
    month_start = st.session_state.planning_month.replace(day=1)

    # 해당 월의 모든 날짜 계산 (일요일 포함)
    all_dates = []
    current = month_start
    while current.month == month_start.month:
        all_dates.append(current)
        current += timedelta(days=1)

    # 일요일 제외한 날짜 (주제 제안 대상)
    content_dates = [d for d in all_dates if d.weekday() != 6]

    progress_bar = st.progress(0, text="🔵 Gemini가 주제를 제안하고 있어요...")
    status_text = st.empty()

    try:
        topics = []
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        already_used_topics = []
        errors = []

        # 일요일 제외하고 주제 제안
        for i, date in enumerate(content_dates):
            progress = (i + 1) / len(content_dates)
            progress_bar.progress(progress, text=f"🔵 {i+1}/{len(content_dates)} - {date.strftime('%m/%d')} 주제 생성 중...")

            try:
                result = pipeline.step0_suggest(
                    target_date=date,
                    weather_note=st.session_state.weather_note or "정보 없음",
                    already_used=already_used_topics
                )
                suggestions = result.get("suggestions", [])

                # 이미 사용된 주제와 겹치지 않는 첫 번째 주제 선택
                topic_name = f"주제 {date.day}일"
                for s in suggestions:
                    candidate = s.get("topic", "")
                    if candidate and not is_similar_topic(candidate, already_used_topics):
                        topic_name = candidate
                        break

                already_used_topics.append(topic_name)

                topics.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "day": weekdays[date.weekday()],
                    "topic": topic_name,
                    "status": "planned",
                    "is_review": False,
                    "suggestions": suggestions
                })

            except Exception as e:
                # 개별 날짜 실패 시 기본값으로 추가하고 계속 진행
                errors.append(f"{date.strftime('%m/%d')}: {str(e)[:50]}")
                topics.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "day": weekdays[date.weekday()],
                    "topic": f"📝 {date.day}일 주제 (직접 입력)",
                    "status": "planned",
                    "is_review": False,
                    "suggestions": []
                })

        progress_bar.progress(1.0, text="✅ 주제 생성 완료!")

        # 일요일은 복습으로 추가
        for date in all_dates:
            if date.weekday() == 6:  # 일요일
                topics.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "day": "일",
                    "topic": "📚 복습",
                    "status": "review",
                    "is_review": True,
                    "suggestions": []
                })

        # 날짜순 정렬
        topics.sort(key=lambda x: x["date"])

        st.session_state.planned_topics = topics

        # 자동 저장 (토큰 절약)
        if save_monthly_plan(month_start, topics):
            st.success(f"✅ {len(content_dates)}일치 주제 제안 완료! 💾 Google Sheets에 자동 저장됨")
        else:
            st.warning(f"⚠️ {len(content_dates)}일치 주제 제안 완료! 저장 실패 - 수동으로 저장하세요")

        # 에러가 있었다면 표시
        if errors:
            with st.expander(f"⚠️ {len(errors)}개 날짜에서 에러 발생 (기본값으로 대체됨)"):
                for err in errors:
                    st.caption(err)

        st.rerun()

    except Exception as e:
        st.error(f"주제 제안 실패: {e}")
        import traceback
        st.code(traceback.format_exc())


def create_empty_monthly_topics():
    """빈 월간 주제 리스트 생성 (일요일=복습 포함).

    직접 입력용 빈 템플릿. 저장은 수동으로 해야 함.
    """
    month_start = st.session_state.planning_month.replace(day=1)

    dates = []
    current = month_start
    while current.month == month_start.month:
        dates.append(current)
        current += timedelta(days=1)

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    topics = []

    for date in dates:
        is_sunday = date.weekday() == 6

        topics.append({
            "date": date.strftime("%Y-%m-%d"),
            "day": weekdays[date.weekday()],
            "topic": "📚 복습" if is_sunday else "",
            "status": "review" if is_sunday else "planned",
            "is_review": is_sunday,
            "suggestions": []
        })

    st.session_state.planned_topics = topics
    st.rerun()


def render_topic_list():
    """주제 리스트 편집 화면."""
    st.subheader("📝 주제 리스트")

    topics = st.session_state.planned_topics

    # 콘텐츠 수 계산 (복습일 제외)
    content_count = sum(1 for t in topics if not t.get("is_review", False))
    review_count = sum(1 for t in topics if t.get("is_review", False))

    st.caption(f"콘텐츠 {content_count}일 + 복습 {review_count}일 = 총 {len(topics)}일")

    # 상태별 필터
    filter_status = st.radio(
        "필터",
        ["전체", "미완료", "완료", "복습"],
        horizontal=True
    )

    if filter_status == "미완료":
        filtered_topics = [(i, t) for i, t in enumerate(topics)
                          if t["status"] not in ["completed", "review"]]
    elif filter_status == "완료":
        filtered_topics = [(i, t) for i, t in enumerate(topics) if t["status"] == "completed"]
    elif filter_status == "복습":
        filtered_topics = [(i, t) for i, t in enumerate(topics) if t.get("is_review", False)]
    else:
        filtered_topics = list(enumerate(topics))

    # 주제 테이블
    for idx, topic in filtered_topics:
        is_review = topic.get("is_review", False)

        status_emoji = {
            "planned": "⬜",
            "in_progress": "🔄",
            "completed": "✅",
            "review": "📚"
        }.get(topic["status"], "⬜")

        col1, col2, col3, col4 = st.columns([1, 1, 3, 1])

        with col1:
            st.write(f"{status_emoji} **{topic['date']}**")

        with col2:
            day_display = f"({topic['day']})" if not is_review else f"(**{topic['day']}**)"
            st.write(day_display)

        with col3:
            if is_review:
                # 복습일은 수정 불가
                st.markdown(f"📚 **복습** *(별도 제작)*")
            else:
                # suggestions가 있으면 드롭다운 + 직접입력 옵션
                suggestions = topic.get("suggestions", [])

                if suggestions:
                    # 제안된 주제 옵션 구성
                    options = [s.get("topic", "") for s in suggestions if s.get("topic")]
                    # "직접 입력" 옵션 추가
                    options.append("✏️ 직접 입력...")

                    # 현재 값이 옵션에 있는지 확인
                    current_val = topic["topic"]
                    if current_val in options:
                        default_idx = options.index(current_val)
                    elif current_val:
                        # 직접 입력된 값이면 "직접 입력" 선택
                        default_idx = len(options) - 1
                    else:
                        default_idx = 0

                    selected = st.selectbox(
                        "주제 선택",
                        options,
                        index=default_idx,
                        key=f"select_{idx}",
                        label_visibility="collapsed"
                    )

                    if selected == "✏️ 직접 입력...":
                        # 직접 입력 모드
                        new_topic = st.text_input(
                            "직접 입력",
                            value=current_val if current_val not in options[:-1] else "",
                            key=f"manual_{idx}",
                            label_visibility="collapsed",
                            placeholder="주제를 직접 입력하세요"
                        )
                        if new_topic and new_topic != topic["topic"]:
                            st.session_state.planned_topics[idx]["topic"] = new_topic
                    else:
                        # 드롭다운 선택
                        if selected != topic["topic"]:
                            st.session_state.planned_topics[idx]["topic"] = selected
                else:
                    # suggestions 없으면 기존 텍스트 입력
                    new_topic = st.text_input(
                        "주제",
                        value=topic["topic"],
                        key=f"topic_{idx}",
                        label_visibility="collapsed",
                        placeholder="주제를 입력하세요"
                    )
                    if new_topic != topic["topic"]:
                        st.session_state.planned_topics[idx]["topic"] = new_topic

        with col4:
            if is_review:
                # 복습일은 생성 버튼 없음
                st.caption("복습")
            elif topic["status"] != "completed":
                if st.button("생성", key=f"gen_{idx}", type="primary"):
                    # 현재 입력된 주제 값 저장 (위젯에서 직접 읽기)
                    if f"topic_{idx}" in st.session_state:
                        st.session_state.planned_topics[idx]["topic"] = st.session_state[f"topic_{idx}"]
                    elif f"select_{idx}" in st.session_state:
                        selected = st.session_state[f"select_{idx}"]
                        if selected != "✏️ 직접 입력...":
                            st.session_state.planned_topics[idx]["topic"] = selected
                        elif f"manual_{idx}" in st.session_state:
                            st.session_state.planned_topics[idx]["topic"] = st.session_state[f"manual_{idx}"]

                    # 생성 모드로 전환
                    st.session_state.current_topic_idx = idx
                    st.session_state.gen_step = 0
                    st.session_state.app_mode = "generating"
                    st.rerun()

    st.divider()

    # 액션 버튼
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("☁️ Sheets에 저장", use_container_width=True):
            month = st.session_state.planning_month
            with st.spinner("Google Sheets에 저장 중..."):
                if save_monthly_plan(month, topics):
                    st.success(f"☁️ {month.strftime('%Y년 %m월')} Google Sheets 저장 완료!")
                else:
                    st.error("저장 실패. Sheets 연결을 확인하세요.")
            st.rerun()

    with col2:
        if st.button("🔄 Gemini로 재생성", use_container_width=True):
            # 기존 기획 삭제 후 재생성
            st.session_state.planned_topics = []
            delete_monthly_plan(st.session_state.planning_month)
            st.rerun()

    with col3:
        if st.button("🗑️ 초기화 & 삭제", type="secondary", use_container_width=True):
            # 세션 및 Sheets에서 삭제
            st.session_state.planned_topics = []
            delete_monthly_plan(st.session_state.planning_month)
            st.toast("🗑️ 기획이 초기화되고 Sheets에서도 삭제되었습니다.")
            st.rerun()

    with col4:
        # 복습일 제외한 콘텐츠만 계산
        content_only = [t for t in topics if not t.get("is_review", False)]
        completed = sum(1 for t in content_only if t["status"] == "completed")
        st.info(f"완료: {completed}/{len(content_only)}")

    # 빈 주제 경고
    empty_topics = [t for t in topics if not t.get("is_review", False) and not t["topic"].strip()]
    if empty_topics:
        st.warning(f"⚠️ {len(empty_topics)}개 주제가 비어있습니다")


# ============================================================
# 콘텐츠 생성 (단계별 검토)
# ============================================================

def render_generating_view():
    """콘텐츠 생성 화면 (단계별 검토)."""

    # 현재 작업 중인 주제 확인
    if st.session_state.current_topic_idx is None:
        st.info("📅 월간 주제 기획에서 생성할 주제를 선택하세요.")
        if st.button("← 월간 기획으로"):
            st.session_state.app_mode = "planning"
            st.rerun()
        return

    topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
    topic = topic_data["topic"]
    target_date = topic_data["date"]

    # 진행 상황 표시
    # 새 흐름: 시작 → 구조 검토 → 콘텐츠 + AI 검수 검토 → 최종 확정
    steps = ["시작", "구조 검토", "콘텐츠 검토", "최종 확정"]
    current_step = st.session_state.gen_step

    st.markdown(f"### 📝 {topic}")
    st.caption(f"발송일: {target_date} ({topic_data['day']})")

    # 스텝 프로그레스
    cols = st.columns(4)
    for i, step_name in enumerate(steps):
        with cols[i]:
            if i < current_step:
                st.markdown(f"✅ {step_name}")
            elif i == current_step:
                st.markdown(f"🔵 **{step_name}**")
            else:
                st.markdown(f"⬜ {step_name}")

    st.divider()

    # 스텝별 렌더링
    if current_step == 0:
        render_gen_step0_start(topic, target_date)
    elif current_step == 1:
        render_gen_step1_structure_review()
    elif current_step == 2:
        render_gen_step2_content_with_review()  # 콘텐츠 + AI 검수 통합
    elif current_step == 3:
        render_gen_step3_final()  # 최종 확정


def render_gen_step0_start(topic: str, target_date: str):
    """Step 0: 시작 - 구조 설계 실행."""
    st.subheader("🔵 Step 1: 구조 설계")
    st.write("Claude가 한글로 콘텐츠 구조를 설계합니다.")
    st.info("💡 영어 생성 전에 맥락을 한글로 먼저 확인할 수 있습니다.")

    feedback = st.session_state.step2_feedback
    if feedback:
        st.warning(f"📝 이전 피드백: {feedback}")

    if st.button("🟣 구조 설계 시작", type="primary"):
        with st.spinner("🟣 Claude가 구조를 설계하고 있어요..."):
            try:
                # 피드백이 있으면 반영
                if feedback:
                    modified_topic = f"{topic}\n\n[관리자 피드백]: {feedback}"
                else:
                    modified_topic = topic

                result = pipeline.step2_structure(modified_topic)
                st.session_state.step2_result = result
                st.session_state.gen_step = 1
                st.rerun()
            except Exception as e:
                st.error(f"구조 설계 실패: {e}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 주제 기획으로"):
            st.session_state.current_topic_idx = None
            st.session_state.gen_step = 0
            st.session_state.step2_feedback = ""
            st.session_state.app_mode = "planning"
            st.rerun()


def render_gen_step1_structure_review():
    """Step 1: 구조 검토 - 한글 맥락 확인 (레벨별/문장별 타겟 피드백 지원)."""
    st.subheader("📋 구조 검토 (한글 맥락)")
    st.info("⚠️ 영어 생성 전에 한글 맥락을 확인하세요. 수정이 필요하면 해당 레벨에서 피드백을 입력하세요.")

    result = st.session_state.step2_result
    if not result:
        st.error("구조 설계 결과가 없습니다.")
        return

    topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
    topic = topic_data["topic"]

    # 공통 상황
    st.markdown(f"**공통 상황:** {result.get('common_situation', '-')}")

    # 레벨별 구조 표시 + 개별 피드백
    levels = result.get("levels", {})
    level_names = {"level_1": "Level 1 (2-3세)", "level_2": "Level 2 (3-5세)", "level_3": "Level 3 (4-6세)"}

    for level_key, level_name in level_names.items():
        level_data = levels.get(level_key, {})

        with st.expander(f"📖 {level_name}", expanded=True):
            st.markdown(f"**장면:** {level_data.get('scene', '-')}")
            st.markdown(f"**흐름:** {level_data.get('flow_logic', '-')}")

            st.markdown("**엄마 말 맥락:**")
            mom_flow = level_data.get("mom_flow", [])
            for i, line in enumerate(mom_flow, 1):
                if isinstance(line, dict):
                    text = line.get(f"line_{i}", str(line))
                else:
                    text = str(line)
                st.write(f"  {i}️⃣ {text}")

            # 아이 반응 (Level 2, 3만)
            if level_key != "level_1":
                st.markdown("**아이 반응:**")
                resp1 = level_data.get("child_response_1", "-")
                resp2 = level_data.get("child_response_2", "-")
                st.write(f"  ⭐ 반응1: {resp1}")
                st.write(f"  ⭐ 반응2: {resp2}")

            st.markdown(f"**학습 포인트:** {level_data.get('learning_point', '-')}")

            # ===== 레벨별 피드백 섹션 =====
            st.markdown("---")
            st.markdown(f"##### 💬 {level_name.split(' ')[0]} {level_name.split(' ')[1]} 피드백")

            # 문장 선택 체크박스
            st.caption("수정할 문장 선택:")
            sent_cols = st.columns(4)
            with sent_cols[0]:
                s1 = st.checkbox("1️⃣", key=f"struct_sent_{level_key}_1", value=False)
            with sent_cols[1]:
                s2 = st.checkbox("2️⃣", key=f"struct_sent_{level_key}_2", value=False)
            with sent_cols[2]:
                s3 = st.checkbox("3️⃣", key=f"struct_sent_{level_key}_3", value=False)
            with sent_cols[3]:
                all_sent = st.checkbox("전체", key=f"struct_sent_{level_key}_all", value=False)

            # 피드백 입력
            level_feedback = st.text_area(
                "피드백 내용",
                placeholder=f"예: 2번 문장의 맥락을 더 구체적으로 수정해주세요.",
                key=f"struct_feedback_{level_key}",
                height=80,
                label_visibility="collapsed"
            )

            # 이 레벨만 재생성 버튼
            if st.button(
                f"🔄 {level_name.split('(')[0].strip()}만 재생성",
                key=f"struct_regen_{level_key}",
                disabled=not level_feedback.strip(),
                use_container_width=True
            ):
                # 타겟 문장 결정
                if all_sent:
                    target_sentences = [1, 2, 3]
                else:
                    target_sentences = []
                    if s1:
                        target_sentences.append(1)
                    if s2:
                        target_sentences.append(2)
                    if s3:
                        target_sentences.append(3)

                if not target_sentences:
                    st.warning("⚠️ 수정할 문장을 선택하세요.")
                else:
                    with st.spinner(f"🟣 {level_name.split('(')[0].strip()} 재생성 중... (문장 {target_sentences})"):
                        try:
                            new_result = pipeline.step2_regenerate_targeted(
                                topic=topic,
                                existing_result=st.session_state.step2_result,
                                target_level=level_key,
                                feedback=level_feedback,
                                target_sentences=target_sentences
                            )
                            st.session_state.step2_result = new_result
                            st.success(f"✅ {level_name.split('(')[0].strip()} 재생성 완료!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"재생성 실패: {e}")

    st.divider()

    # 전체 액션 버튼
    st.subheader("📋 전체 액션")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← 이전", use_container_width=True):
            st.session_state.gen_step = 0
            st.rerun()

    with col2:
        if st.button("🔄 전체 재생성", use_container_width=True, help="모든 레벨을 처음부터 재설계"):
            with st.spinner("🟣 Claude가 전체 재설계 중..."):
                try:
                    new_result = pipeline.step2_structure(topic)
                    st.session_state.step2_result = new_result
                    st.rerun()
                except Exception as e:
                    st.error(f"재생성 실패: {e}")

    with col3:
        if st.button("✅ 승인 → 영어 생성 + AI 검수", type="primary", use_container_width=True):
            # Step 1: 영어 생성
            with st.spinner("🟣 Claude가 영어 문장을 생성하고 있어요..."):
                try:
                    category = db_loader.categorize_topic(topic)
                    gen_result = pipeline.step3_generate(st.session_state.step2_result, category=category)
                    st.session_state.step3_result = gen_result
                except Exception as e:
                    st.error(f"영어 생성 실패: {e}")
                    return

            # Step 2: AI 검수 (자동 실행)
            with st.spinner("🟢 GPT가 품질을 검수하고 있어요..."):
                try:
                    review_result = pipeline.step4_review(gen_result, category=category)
                    st.session_state.step4_result = review_result

                    # GPT 추천안으로 기본 선택 설정
                    best_combo = review_result.get("overall_recommendation", {}).get("best_combination", {})
                    for level_key in ["level_1", "level_2", "level_3"]:
                        if level_key in best_combo:
                            st.session_state.selected_variants[level_key] = best_combo[level_key]

                    st.session_state.gen_step = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"AI 검수 실패: {e}")


def render_gen_step2_content_with_review():
    """Step 2: 영어 콘텐츠 + AI 검수 결과 통합 검토.

    새 흐름: 영문 생성 → AI 검수 (자동) → 관리자 검토 → 피드백 시 재생성+재검수 루프
    """
    st.subheader("📝 콘텐츠 검토 (AI 검수 완료)")

    gen_result = st.session_state.step3_result
    review_result = st.session_state.step4_result

    if not gen_result:
        st.error("생성 결과가 없습니다.")
        return

    if not review_result:
        st.warning("AI 검수 결과가 없습니다. 검수를 실행합니다...")
        # 검수 자동 실행
        with st.spinner("🟢 GPT가 품질을 검수하고 있어요..."):
            try:
                topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
                category = db_loader.categorize_topic(topic_data["topic"])
                review_result = pipeline.step4_review(gen_result, category=category)
                st.session_state.step4_result = review_result
                st.rerun()
            except Exception as e:
                st.error(f"AI 검수 실패: {e}")
                return

    levels = gen_result.get("levels", {})
    topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
    category = db_loader.categorize_topic(topic_data["topic"])

    # AI 검수 요약 (상단에 표시)
    overall = review_result.get("overall_recommendation", {})
    confidence = overall.get("confidence", "unknown")
    conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")

    col_summary1, col_summary2 = st.columns([2, 3])
    with col_summary1:
        st.markdown(f"### {conf_emoji} AI 검수: {confidence.upper()}")
    with col_summary2:
        if overall.get("human_review_focus"):
            st.info(f"💡 검토 포인트: {overall.get('human_review_focus')}")

    st.divider()

    # 레벨별 콘텐츠 + AI 검수 점수 표시
    level_tabs = st.tabs(["Level 1 (2-3세)", "Level 2 (3-5세)", "Level 3 (4-6세)"])
    level_names = {"level_1": "Level 1", "level_2": "Level 2", "level_3": "Level 3"}

    review_data = review_result.get("review", {})

    for level_key, tab in zip(["level_1", "level_2", "level_3"], level_tabs):
        with tab:
            level_data = levels.get(level_key, {})
            variants = level_data.get("variants", {})
            level_review = review_data.get(level_key, {})
            variants_review = level_review.get("variants", {})

            # GPT 추천안 표시
            best_pick = level_review.get("best_pick", "A")
            best_reason = level_review.get("best_pick_reason", "")

            st.caption(f"🏆 GPT 추천: **{best_pick}안** - {best_reason}")

            # A/B/C 선택
            current_selected = st.session_state.selected_variants.get(level_key, "A")
            selected = st.radio(
                "변형 선택",
                ["A", "B", "C"],
                horizontal=True,
                key=f"var_select_{level_key}",
                index=["A", "B", "C"].index(current_selected)
            )
            st.session_state.selected_variants[level_key] = selected

            # 선택된 변형 + 점수 표시
            var_data = variants.get(selected, {})
            admin_text = var_data.get("admin_text", "(없음)")

            # 점수 정보
            var_review = variants_review.get(selected, {})
            total_score = var_review.get("total", 0)
            max_score = var_review.get("max_possible", 60)
            verdict = var_review.get("verdict", "?")
            verdict_emoji = {"pass": "✅", "revise": "⚠️", "reject": "❌"}.get(verdict, "❓")

            st.markdown(f"**점수: {total_score}/{max_score}** {verdict_emoji} ({verdict})")

            # 콘텐츠 표시
            st.code(admin_text, language=None)

            # 이슈 표시 (있으면)
            issues = var_review.get("issues", [])
            if issues:
                with st.expander(f"⚠️ 검수 이슈 ({len(issues)}개)", expanded=False):
                    for issue in issues:
                        if isinstance(issue, dict):
                            severity = issue.get("severity", "minor")
                            desc = issue.get("description", str(issue))
                            sev_emoji = {"critical": "🔴", "major": "🟠", "minor": "🟡"}.get(severity, "⚪")
                            st.write(f"{sev_emoji} [{severity}] {desc}")
                        else:
                            st.write(f"• {issue}")

            # 점수 상세 (접기)
            scores = var_review.get("scores", {})
            if scores:
                with st.expander("📊 점수 상세", expanded=False):
                    score_names = {
                        "naturalness": "원어민 자연스러움",
                        "grammar": "문법 완전성",
                        "info_density": "정보 밀도 준수",
                        "level_differentiation": "레벨 간 차별성",
                        "flow": "문장 흐름",
                        "korean_match": "한국어 대응"
                    }
                    for key, name in score_names.items():
                        score = scores.get(key, "-")
                        st.write(f"• {name}: {score}/10")

            # ===== 레벨별 피드백 섹션 =====
            st.markdown("---")
            st.markdown(f"##### 💬 {level_names[level_key]} 피드백 (재생성 시 AI 재검수 자동 실행)")

            # 문장 선택 체크박스
            st.caption("수정할 문장 선택:")
            sent_cols = st.columns(4)
            with sent_cols[0]:
                s1 = st.checkbox("1️⃣", key=f"sent_{level_key}_1", value=False)
            with sent_cols[1]:
                s2 = st.checkbox("2️⃣", key=f"sent_{level_key}_2", value=False)
            with sent_cols[2]:
                s3 = st.checkbox("3️⃣", key=f"sent_{level_key}_3", value=False)
            with sent_cols[3]:
                all_sent = st.checkbox("전체", key=f"sent_{level_key}_all", value=False)

            # 피드백 입력
            level_feedback = st.text_area(
                "피드백 내용",
                placeholder=f"예: 2번 문장을 더 구체적으로 수정해주세요. / 격려 톤을 추가해주세요.",
                key=f"feedback_{level_key}",
                height=80,
                label_visibility="collapsed"
            )

            # 이 레벨만 재생성 + 재검수 버튼
            if st.button(
                f"🔄 {level_names[level_key]} 재생성 + 재검수",
                key=f"regen_{level_key}",
                disabled=not level_feedback.strip(),
                use_container_width=True
            ):
                # 타겟 문장 결정
                if all_sent:
                    target_sentences = [1, 2, 3]
                else:
                    target_sentences = []
                    if s1:
                        target_sentences.append(1)
                    if s2:
                        target_sentences.append(2)
                    if s3:
                        target_sentences.append(3)

                if not target_sentences:
                    st.warning("⚠️ 수정할 문장을 선택하세요.")
                else:
                    # 1. 재생성
                    with st.spinner(f"🟣 {level_names[level_key]} 재생성 중... (문장 {target_sentences})"):
                        try:
                            new_gen_result = pipeline.step3_regenerate_targeted(
                                structure=st.session_state.step2_result,
                                existing_result=st.session_state.step3_result,
                                target_level=level_key,
                                feedback=level_feedback,
                                target_sentences=target_sentences,
                                preserve_variant=selected,
                                category=category
                            )
                            st.session_state.step3_result = new_gen_result
                        except Exception as e:
                            st.error(f"재생성 실패: {e}")
                            return

                    # 2. 재검수 (자동)
                    with st.spinner(f"🟢 GPT가 재검수하고 있어요..."):
                        try:
                            new_review_result = pipeline.step4_review(new_gen_result, category=category)
                            st.session_state.step4_result = new_review_result
                            st.success(f"✅ {level_names[level_key]} 재생성 + 재검수 완료!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"재검수 실패: {e}")

    st.divider()

    # 전체 액션 버튼
    st.subheader("📋 전체 액션")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← 구조로 돌아가기", use_container_width=True):
            st.session_state.gen_step = 1
            st.rerun()

    with col2:
        # 전체 재생성 + 재검수
        if st.button("🔄 전체 재생성 + 재검수", use_container_width=True, help="모든 레벨을 처음부터 재생성 후 재검수"):
            # 1. 전체 재생성
            with st.spinner("🟣 Claude가 전체 재생성 중..."):
                try:
                    new_gen_result = pipeline.step3_generate(
                        st.session_state.step2_result,
                        category=category
                    )
                    st.session_state.step3_result = new_gen_result
                except Exception as e:
                    st.error(f"재생성 실패: {e}")
                    return

            # 2. 전체 재검수
            with st.spinner("🟢 GPT가 재검수하고 있어요..."):
                try:
                    new_review_result = pipeline.step4_review(new_gen_result, category=category)
                    st.session_state.step4_result = new_review_result
                    st.success("✅ 전체 재생성 + 재검수 완료!")
                    st.rerun()
                except Exception as e:
                    st.error(f"재검수 실패: {e}")

    with col3:
        if st.button("✅ 승인 → 최종 확정", type="primary", use_container_width=True):
            st.session_state.gen_step = 3
            st.rerun()


def render_gen_step3_final():
    """Step 3: 최종 확정 - 선택된 콘텐츠 확인 및 Google Sheets 저장."""
    st.subheader("🎉 최종 확정")

    topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
    topic = topic_data["topic"]
    target_date = topic_data["date"]

    step3_result = st.session_state.step3_result
    levels = step3_result.get("levels", {})

    # 최종 선택된 콘텐츠 표시
    st.markdown("### 📄 최종 콘텐츠")

    final_texts = {}
    for level_key, level_name in [("level_1", "Level 1"), ("level_2", "Level 2"), ("level_3", "Level 3")]:
        selected_var = st.session_state.selected_variants.get(level_key, "A")
        level_data = levels.get(level_key, {})
        variants = level_data.get("variants", {})
        var_data = variants.get(selected_var, {})
        admin_text = var_data.get("admin_text", "")
        final_texts[level_key] = admin_text

        with st.expander(f"{level_name} ({selected_var}안)", expanded=True):
            st.code(admin_text, language=None)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("← 콘텐츠 검토로"):
            st.session_state.gen_step = 2
            st.rerun()

    with col2:
        if st.button("🎉 확정 & Google Sheets 저장", type="primary"):
            with st.spinner("Google Sheets에 저장 중..."):
                try:
                    import sheets_writer

                    result = sheets_writer.append_content(
                        topic=topic,
                        target_date=target_date,
                        level1_text=final_texts.get("level_1", ""),
                        level2_text=final_texts.get("level_2", ""),
                        level3_text=final_texts.get("level_3", "")
                    )

                    if result["success"]:
                        # 상태 업데이트
                        st.session_state.planned_topics[st.session_state.current_topic_idx]["status"] = "completed"

                        # 월간 기획 자동 저장 (완료 상태 반영)
                        target_month = datetime.strptime(target_date, "%Y-%m-%d").replace(day=1)
                        save_monthly_plan(target_month, st.session_state.planned_topics)

                        st.success(f"✅ 저장 완료! (No.{result['no']}, Row {result['row']})")
                        st.balloons()

                        # 다음 주제로 이동 또는 기획으로 돌아가기
                        next_idx = find_next_incomplete_topic()

                        if next_idx is not None:
                            if st.button("➡️ 다음 주제로"):
                                reset_generation_state()
                                st.session_state.current_topic_idx = next_idx
                                st.rerun()

                        if st.button("📅 월간 기획으로"):
                            reset_generation_state()
                            st.session_state.app_mode = "planning"
                            st.rerun()
                    else:
                        st.error(f"저장 실패: {result['error']}")

                except Exception as e:
                    st.error(f"저장 실패: {e}")


def find_next_incomplete_topic():
    """다음 미완료 주제 인덱스 찾기 (복습일 제외)."""
    for i, topic in enumerate(st.session_state.planned_topics):
        # 복습일은 건너뛰기
        if topic.get("is_review", False):
            continue
        if topic["status"] != "completed":
            return i
    return None


def reset_generation_state():
    """생성 관련 상태 초기화."""
    st.session_state.current_topic_idx = None
    st.session_state.gen_step = 0
    st.session_state.step2_result = None
    st.session_state.step2_feedback = ""
    st.session_state.step3_result = None
    st.session_state.step4_result = None
    st.session_state.selected_variants = {"level_1": "A", "level_2": "A", "level_3": "A"}


# ============================================================
# 콘텐츠 관리
# ============================================================

def render_management_view():
    """콘텐츠 관리 화면."""
    st.header("📋 콘텐츠 관리")

    try:
        import sheets_writer
    except ImportError:
        st.error("sheets_writer 모듈을 불러올 수 없습니다.")
        return

    # 새로고침 버튼
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 새로고침"):
            st.session_state.sheets_contents = []
            st.rerun()

    # 콘텐츠 로드
    if not st.session_state.sheets_contents:
        with st.spinner("Google Sheets에서 콘텐츠 로딩 중..."):
            try:
                contents = sheets_writer.get_all_contents()
                st.session_state.sheets_contents = contents
            except Exception as e:
                st.error(f"콘텐츠 로드 실패: {e}")
                return

    contents = st.session_state.sheets_contents

    if not contents:
        st.info("저장된 콘텐츠가 없습니다.")
        return

    # 날짜 필터
    dates = sorted(set(c.get("date", "") for c in contents if c.get("date")), reverse=True)

    if dates:
        selected_date = st.selectbox(
            "날짜 선택",
            ["전체"] + dates,
            format_func=lambda x: x if x == "전체" else f"{x} ({sum(1 for c in contents if c.get('date') == x)}건)"
        )
    else:
        selected_date = "전체"

    # 필터링
    filtered = contents if selected_date == "전체" else [c for c in contents if c.get("date") == selected_date]

    st.write(f"총 **{len(filtered)}건**의 콘텐츠")

    # 콘텐츠 표시
    for content in reversed(filtered):
        row_num = content.get("row_number", 0)
        date = content.get("date", "-")
        day = content.get("day", "-")
        topic = content.get("situation", "-")
        no = content.get("no", "-")

        with st.expander(f"**{date}** ({day}) - {topic}  [No.{no}]"):
            tab1, tab2, tab3 = st.tabs(["Level 1", "Level 2", "Level 3"])

            with tab1:
                l1 = content.get("level1", "(없음)")
                st.code(l1[:500] + "..." if len(l1) > 500 else l1, language=None)
            with tab2:
                l2 = content.get("level2", "(없음)")
                st.code(l2[:500] + "..." if len(l2) > 500 else l2, language=None)
            with tab3:
                l3 = content.get("level3", "(없음)")
                st.code(l3[:500] + "..." if len(l3) > 500 else l3, language=None)

            col1, col2 = st.columns(2)

            with col2:
                if st.button("🗑️ 삭제", key=f"del_{row_num}", type="secondary"):
                    st.session_state[f"confirm_delete_{row_num}"] = True
                    st.rerun()

            if st.session_state.get(f"confirm_delete_{row_num}"):
                st.warning(f"정말 이 콘텐츠를 삭제하시겠습니까? (No.{no}, {topic})")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ 삭제 확인", key=f"confirm_yes_{row_num}"):
                        result = sheets_writer.delete_content(row_num)
                        if result['success']:
                            st.success("삭제되었습니다.")
                            st.session_state.sheets_contents = []
                            del st.session_state[f"confirm_delete_{row_num}"]
                            st.rerun()
                        else:
                            st.error(f"삭제 실패: {result['error']}")
                with col_no:
                    if st.button("❌ 취소", key=f"confirm_no_{row_num}"):
                        del st.session_state[f"confirm_delete_{row_num}"]
                        st.rerun()


if __name__ == "__main__":
    main()
