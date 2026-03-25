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
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

import db_loader
import pipeline

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
    defaults = {
        # 앱 모드
        "app_mode": "planning",  # "planning", "generating", "management"

        # 월간 기획
        "planning_month": datetime.now().replace(day=1),
        "planned_topics": [],  # [{date, day, topic, status: planned/in_progress/completed}]

        # 콘텐츠 생성 (현재 작업 중인 주제)
        "current_topic_idx": None,
        "gen_step": 0,  # 0: 시작, 1: 구조검토, 2: 생성검토, 3: 검수검토, 4: 최종확정
        "step2_result": None,  # 구조 설계 결과
        "step2_feedback": "",
        "step3_result": None,  # 문장 생성 결과
        "step3_feedback": "",
        "step4_result": None,  # 검수 결과
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
        🔵 Gemini (분석) → 🟣 Claude (생성) → 🟢 GPT (검수)
    </div>
    """, unsafe_allow_html=True)

    # 사이드바
    with st.sidebar:
        st.header("📌 메뉴")
        mode = st.radio(
            "작업 선택",
            ["📅 월간 주제 기획", "✨ 콘텐츠 생성", "📋 콘텐츠 관리"],
            label_visibility="collapsed"
        )

        if "기획" in mode:
            st.session_state.app_mode = "planning"
        elif "생성" in mode:
            st.session_state.app_mode = "generating"
        else:
            st.session_state.app_mode = "management"

        st.divider()
        st.caption("🤖 AI 파이프라인")
        st.markdown("""
        <small>
        1️⃣ 🔵 <b>Gemini</b> - 주제 제안/분석<br>
        2️⃣ 🟣 <b>Claude</b> - 영어 문장 생성<br>
        3️⃣ 🟢 <b>GPT</b> - 품질 검수
        </small>
        """, unsafe_allow_html=True)

        # 진행 상황 표시
        if st.session_state.planned_topics:
            st.divider()
            st.caption("📊 진행 현황")
            total = len(st.session_state.planned_topics)
            completed = sum(1 for t in st.session_state.planned_topics if t.get("status") == "completed")
            st.progress(completed / total if total > 0 else 0)
            st.write(f"완료: {completed}/{total}")

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
        st.session_state.planning_month = datetime.combine(selected_month, datetime.min.time())

    with col2:
        weather = st.text_input(
            "계절/날씨 참고 (선택)",
            value=st.session_state.weather_note,
            placeholder="예: 봄, 따뜻함"
        )
        st.session_state.weather_note = weather

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
        render_topic_list()


def generate_monthly_topics():
    """Gemini로 월간 주제 생성."""
    month_start = st.session_state.planning_month.replace(day=1)

    # 해당 월의 날짜 계산 (일요일 제외)
    dates = []
    current = month_start
    while current.month == month_start.month:
        if current.weekday() != 6:  # 일요일 제외
            dates.append(current)
        current += timedelta(days=1)

    with st.spinner(f"🔵 Gemini가 {len(dates)}일치 주제를 제안하고 있어요..."):
        try:
            topics = []
            weekdays = ["월", "화", "수", "목", "금", "토", "일"]

            # 여러 날짜에 대해 주제 제안 (배치로 처리)
            for date in dates:
                result = pipeline.step0_suggest(
                    target_date=date,
                    weather_note=st.session_state.weather_note or "정보 없음"
                )
                suggestions = result.get("suggestions", [])

                # 첫 번째 추천 주제 사용
                topic_name = suggestions[0].get("topic", f"주제 {date.day}일") if suggestions else f"주제 {date.day}일"

                topics.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "day": weekdays[date.weekday()],
                    "topic": topic_name,
                    "status": "planned",
                    "suggestions": suggestions  # 다른 후보들도 저장
                })

            st.session_state.planned_topics = topics
            st.success(f"✅ {len(topics)}일치 주제 제안 완료!")
            st.rerun()

        except Exception as e:
            st.error(f"주제 제안 실패: {e}")


def create_empty_monthly_topics():
    """빈 월간 주제 리스트 생성."""
    month_start = st.session_state.planning_month.replace(day=1)

    dates = []
    current = month_start
    while current.month == month_start.month:
        if current.weekday() != 6:  # 일요일 제외
            dates.append(current)
        current += timedelta(days=1)

    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    topics = []

    for date in dates:
        topics.append({
            "date": date.strftime("%Y-%m-%d"),
            "day": weekdays[date.weekday()],
            "topic": "",
            "status": "planned",
            "suggestions": []
        })

    st.session_state.planned_topics = topics
    st.rerun()


def render_topic_list():
    """주제 리스트 편집 화면."""
    st.subheader("📝 주제 리스트")

    topics = st.session_state.planned_topics

    # 상태별 필터
    filter_status = st.radio(
        "필터",
        ["전체", "미완료", "완료"],
        horizontal=True
    )

    if filter_status == "미완료":
        filtered_topics = [(i, t) for i, t in enumerate(topics) if t["status"] != "completed"]
    elif filter_status == "완료":
        filtered_topics = [(i, t) for i, t in enumerate(topics) if t["status"] == "completed"]
    else:
        filtered_topics = list(enumerate(topics))

    # 주제 테이블
    for idx, topic in filtered_topics:
        status_emoji = {
            "planned": "⬜",
            "in_progress": "🔄",
            "completed": "✅"
        }.get(topic["status"], "⬜")

        col1, col2, col3, col4 = st.columns([1, 1, 3, 1])

        with col1:
            st.write(f"{status_emoji} **{topic['date']}**")

        with col2:
            st.write(f"({topic['day']})")

        with col3:
            # 주제 편집 가능
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
            if topic["status"] != "completed":
                if st.button("생성", key=f"gen_{idx}", type="primary"):
                    st.session_state.current_topic_idx = idx
                    st.session_state.gen_step = 0
                    st.session_state.app_mode = "generating"
                    st.rerun()

    st.divider()

    # 액션 버튼
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🗑️ 주제 리스트 초기화", type="secondary"):
            st.session_state.planned_topics = []
            st.rerun()

    with col2:
        # 빈 주제 확인
        empty_topics = [t for t in topics if not t["topic"].strip()]
        if empty_topics:
            st.warning(f"⚠️ {len(empty_topics)}개 주제가 비어있습니다")

    with col3:
        completed = sum(1 for t in topics if t["status"] == "completed")
        st.info(f"완료: {completed}/{len(topics)}")


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
    steps = ["시작", "구조 검토", "생성 검토", "검수 검토", "최종 확정"]
    current_step = st.session_state.gen_step

    st.markdown(f"### 📝 {topic}")
    st.caption(f"발송일: {target_date} ({topic_data['day']})")

    # 스텝 프로그레스
    cols = st.columns(5)
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
        render_gen_step2_content_review()
    elif current_step == 3:
        render_gen_step3_review_check()
    elif current_step == 4:
        render_gen_step4_final()


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
    """Step 1: 구조 검토 - 한글 맥락 확인."""
    st.subheader("📋 구조 검토 (한글 맥락)")
    st.info("⚠️ 영어 생성 전에 한글 맥락을 확인하세요. 잘못된 정보가 있으면 피드백을 주세요.")

    result = st.session_state.step2_result
    if not result:
        st.error("구조 설계 결과가 없습니다.")
        return

    # 공통 상황
    st.markdown(f"**공통 상황:** {result.get('common_situation', '-')}")

    # 레벨별 구조 표시
    levels = result.get("levels", {})

    for level_key, level_name in [("level_1", "Level 1 (2-3세)"), ("level_2", "Level 2 (3-5세)"), ("level_3", "Level 3 (4-6세)")]:
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

    st.divider()

    # 피드백 입력
    st.subheader("💬 피드백")
    feedback = st.text_area(
        "수정이 필요한 부분이 있으면 피드백을 입력하세요",
        placeholder="예: Level 2의 '씹으면 이가 튼튼해진다'는 근거 없음. '비타민이 많아서 건강에 좋다'로 변경해주세요.",
        height=100
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← 이전"):
            st.session_state.gen_step = 0
            st.rerun()

    with col2:
        if st.button("🔄 피드백 반영 재생성", disabled=not feedback.strip()):
            st.session_state.step2_feedback = feedback
            st.session_state.gen_step = 0
            st.rerun()

    with col3:
        if st.button("✅ 승인 → 영어 생성", type="primary"):
            st.session_state.step2_feedback = ""
            with st.spinner("🟣 Claude가 영어 문장을 생성하고 있어요..."):
                try:
                    topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
                    category = db_loader.categorize_topic(topic_data["topic"])
                    result = pipeline.step3_generate(st.session_state.step2_result, category=category)
                    st.session_state.step3_result = result
                    st.session_state.gen_step = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"영어 생성 실패: {e}")


def render_gen_step2_content_review():
    """Step 2: 생성된 콘텐츠 검토."""
    st.subheader("📝 영어 콘텐츠 검토")

    result = st.session_state.step3_result
    if not result:
        st.error("생성 결과가 없습니다.")
        return

    levels = result.get("levels", {})

    # 레벨별 A/B/C 변형 표시
    level_tabs = st.tabs(["Level 1 (2-3세)", "Level 2 (3-5세)", "Level 3 (4-6세)"])

    for level_key, tab in zip(["level_1", "level_2", "level_3"], level_tabs):
        with tab:
            level_data = levels.get(level_key, {})
            variants = level_data.get("variants", {})

            # A/B/C 선택
            selected = st.radio(
                "변형 선택",
                ["A", "B", "C"],
                horizontal=True,
                key=f"select_{level_key}",
                index=["A", "B", "C"].index(st.session_state.selected_variants.get(level_key, "A"))
            )
            st.session_state.selected_variants[level_key] = selected

            # 선택된 변형 표시
            var_data = variants.get(selected, {})
            admin_text = var_data.get("admin_text", "(없음)")
            st.code(admin_text, language=None)

    st.divider()

    # 피드백 입력
    st.subheader("💬 피드백")
    feedback = st.text_area(
        "영어 표현 수정이 필요하면 피드백을 입력하세요",
        placeholder="예: Level 2의 2번 문장이 너무 길어요. 더 짧게 해주세요.",
        height=100,
        key="step3_feedback_input"
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← 구조로 돌아가기"):
            st.session_state.gen_step = 1
            st.rerun()

    with col2:
        if st.button("🔄 피드백 반영 재생성", disabled=not feedback.strip(), key="regen_step3"):
            st.session_state.step3_feedback = feedback
            with st.spinner("🟣 Claude가 피드백을 반영하여 재생성 중..."):
                try:
                    topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
                    category = db_loader.categorize_topic(topic_data["topic"])

                    # 피드백을 포함한 구조
                    modified_structure = st.session_state.step2_result.copy()
                    modified_structure["feedback"] = feedback

                    result = pipeline.step3_generate(modified_structure, category=category)
                    st.session_state.step3_result = result
                    st.rerun()
                except Exception as e:
                    st.error(f"재생성 실패: {e}")

    with col3:
        if st.button("✅ 승인 → GPT 검수", type="primary"):
            with st.spinner("🟢 GPT가 품질을 검수하고 있어요..."):
                try:
                    topic_data = st.session_state.planned_topics[st.session_state.current_topic_idx]
                    category = db_loader.categorize_topic(topic_data["topic"])
                    result = pipeline.step4_review(st.session_state.step3_result, category=category)
                    st.session_state.step4_result = result
                    st.session_state.gen_step = 3
                    st.rerun()
                except Exception as e:
                    st.error(f"검수 실패: {e}")


def render_gen_step3_review_check():
    """Step 3: GPT 검수 결과 확인."""
    st.subheader("🔍 GPT 검수 결과")

    result = st.session_state.step4_result
    if not result:
        st.error("검수 결과가 없습니다.")
        return

    overall = result.get("overall_recommendation", {})
    best_combo = overall.get("best_combination", {})
    confidence = overall.get("confidence", "unknown")

    # 신뢰도 표시
    conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")
    st.markdown(f"### {conf_emoji} 신뢰도: {confidence.upper()}")

    if overall.get("human_review_focus"):
        st.warning(f"💡 검토 포인트: {overall.get('human_review_focus')}")

    # GPT 추천 vs 내 선택 비교
    st.subheader("📊 변형 선택")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Level 1**")
        gpt_pick = best_combo.get("level_1", "A")
        my_pick = st.session_state.selected_variants.get("level_1", "A")
        st.write(f"GPT 추천: {gpt_pick}안")
        new_pick = st.radio("선택", ["A", "B", "C"], index=["A", "B", "C"].index(my_pick), key="final_l1", horizontal=True)
        st.session_state.selected_variants["level_1"] = new_pick

    with col2:
        st.markdown("**Level 2**")
        gpt_pick = best_combo.get("level_2", "A")
        my_pick = st.session_state.selected_variants.get("level_2", "A")
        st.write(f"GPT 추천: {gpt_pick}안")
        new_pick = st.radio("선택", ["A", "B", "C"], index=["A", "B", "C"].index(my_pick), key="final_l2", horizontal=True)
        st.session_state.selected_variants["level_2"] = new_pick

    with col3:
        st.markdown("**Level 3**")
        gpt_pick = best_combo.get("level_3", "A")
        my_pick = st.session_state.selected_variants.get("level_3", "A")
        st.write(f"GPT 추천: {gpt_pick}안")
        new_pick = st.radio("선택", ["A", "B", "C"], index=["A", "B", "C"].index(my_pick), key="final_l3", horizontal=True)
        st.session_state.selected_variants["level_3"] = new_pick

    # 레벨별 점수 상세
    with st.expander("📈 점수 상세"):
        review = result.get("review", {})
        for level_key in ["level_1", "level_2", "level_3"]:
            level_review = review.get(level_key, {})
            variants_review = level_review.get("variants", {})

            st.markdown(f"**{level_key.upper()}**")
            for var_key in ["A", "B", "C"]:
                var_review = variants_review.get(var_key, {})
                total = var_review.get("total", 0)
                verdict = var_review.get("verdict", "?")
                st.write(f"  {var_key}안: {total}/80 ({verdict})")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("← 콘텐츠 수정"):
            st.session_state.gen_step = 2
            st.rerun()

    with col2:
        if st.button("✅ 최종 확정으로", type="primary"):
            st.session_state.gen_step = 4
            st.rerun()


def render_gen_step4_final():
    """Step 4: 최종 확정."""
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
        if st.button("← 검수 결과로"):
            st.session_state.gen_step = 3
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
    """다음 미완료 주제 인덱스 찾기."""
    for i, topic in enumerate(st.session_state.planned_topics):
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
    st.session_state.step3_feedback = ""
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
