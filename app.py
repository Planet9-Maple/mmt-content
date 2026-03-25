"""
마미톡잉글리시 콘텐츠 생성 UI

Streamlit 기반 웹 인터페이스
3개 프로바이더: Gemini(분석) → Claude(생성) → GPT(검수)
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

# 프로바이더 정보
PROVIDER_INFO = {
    "gemini": {"emoji": "🔵", "name": "Gemini", "color": "#4285F4"},
    "claude": {"emoji": "🟣", "name": "Claude", "color": "#7C3AED"},
    "gpt": {"emoji": "🟢", "name": "GPT", "color": "#10A37F"}
}


def init_session_state():
    """세션 상태 초기화."""
    defaults = {
        "step": 0,
        "target_date": datetime.now() + timedelta(days=1),
        "weather_note": "",
        "suggestions": [],
        "selected_topic": "",
        "pipeline_result": None,
        "is_generating": False,
        "app_mode": "create",  # "create" or "manage"
        "sheets_contents": [],
        "regenerate_date": None,
        "regenerate_topic": None
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main():
    init_session_state()

    st.title("👶 마미톡잉글리시 콘텐츠 생성기")
    st.caption("엄마-아이 영어 대화 콘텐츠를 자동으로 생성합니다")

    # 프로바이더 파이프라인 표시
    st.markdown("""
    <div style="background: linear-gradient(90deg, #4285F4 0%, #7C3AED 50%, #10A37F 100%);
                padding: 8px 16px; border-radius: 8px; color: white; text-align: center; margin-bottom: 20px;">
        🔵 Gemini (분석) → 🟣 Claude (생성) → 🟢 GPT (검수)
    </div>
    """, unsafe_allow_html=True)

    # 사이드바
    with st.sidebar:
        # 모드 선택
        st.header("📌 메뉴")
        mode = st.radio(
            "작업 선택",
            ["✨ 새 콘텐츠 생성", "📋 콘텐츠 관리"],
            label_visibility="collapsed"
        )
        st.session_state.app_mode = "create" if "생성" in mode else "manage"

        st.divider()
        st.caption("🤖 AI 파이프라인")
        st.markdown("""
        <small>
        1️⃣ 🔵 <b>Gemini</b> - 주제 제안/분석<br>
        2️⃣ 🟣 <b>Claude</b> - 영어 문장 생성<br>
        3️⃣ 🟢 <b>GPT</b> - 품질 검수
        </small>
        """, unsafe_allow_html=True)

    # 메인 영역
    if st.session_state.app_mode == "manage":
        render_content_management()
    elif st.session_state.step == 0:
        render_step0_input()
    elif st.session_state.step == 1:
        render_step1_topic_select()
    elif st.session_state.step == 2:
        render_step2_generating()
    elif st.session_state.step == 3:
        render_step3_results()


def render_step0_input():
    """Step 0: 날짜/주제 입력 화면."""
    st.header("📅 Step 1: 발송 정보 입력")

    col1, col2 = st.columns(2)

    with col1:
        target_date = st.date_input(
            "발송일",
            value=st.session_state.target_date,
            min_value=datetime.now().date()
        )
        st.session_state.target_date = datetime.combine(target_date, datetime.min.time())

        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        day_str = weekdays[st.session_state.target_date.weekday()]
        st.info(f"📆 {target_date.strftime('%Y년 %m월 %d일')} ({day_str}요일)")

        if day_str == "일":
            st.warning("⚠️ 일요일은 복습일입니다. 콘텐츠 생성 대상이 아닙니다.")

    with col2:
        weather = st.text_input(
            "날씨 정보 (선택)",
            value=st.session_state.weather_note,
            placeholder="예: 맑음, 18도"
        )
        st.session_state.weather_note = weather

    st.divider()

    topic_mode = st.radio(
        "주제 입력 방식",
        ["🔵 Gemini가 주제 제안", "✏️ 직접 주제 입력"],
        horizontal=True
    )

    if topic_mode == "✏️ 직접 주제 입력":
        direct_topic = st.text_input(
            "주제 입력",
            placeholder="예: 🌸 벚꽃이 예뻐요"
        )

        if st.button("🚀 콘텐츠 생성 시작", type="primary", disabled=not direct_topic):
            st.session_state.selected_topic = direct_topic
            st.session_state.step = 2
            st.rerun()

    else:
        if st.button("🔵 Gemini에게 주제 제안 받기", type="primary"):
            with st.spinner("🔵 Gemini가 주제를 분석하고 있어요..."):
                try:
                    result = pipeline.step0_suggest(
                        target_date=st.session_state.target_date,
                        weather_note=st.session_state.weather_note or "정보 없음"
                    )
                    st.session_state.suggestions = result.get("suggestions", [])
                    st.session_state.step = 1
                    st.rerun()
                except Exception as e:
                    st.error(f"주제 제안 실패: {e}")


def render_step1_topic_select():
    """Step 1: 주제 선택 화면."""
    st.header("💡 Step 2: 주제 선택")

    suggestions = st.session_state.suggestions

    if not suggestions:
        st.warning("제안된 주제가 없습니다.")
        if st.button("← 처음으로"):
            st.session_state.step = 0
            st.rerun()
        return

    st.write("🔵 Gemini가 제안한 주제 중 하나를 선택하거나 수정하세요:")

    topic_options = [s.get("topic", "") for s in suggestions]
    selected_idx = st.radio(
        "주제 선택",
        range(len(topic_options)),
        format_func=lambda i: topic_options[i],
        label_visibility="collapsed"
    )

    selected = suggestions[selected_idx]
    with st.expander("📋 주제 상세 정보", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**카테고리:** {selected.get('category', '-')}")
            st.write(f"**이유:** {selected.get('why', '-')}")
        with col2:
            st.write(f"**장면:** {selected.get('scene_hint', '-')}")
            st.write(f"**확장성:** {selected.get('expandability', '-')}")

    st.divider()
    edit_topic = st.text_input(
        "주제 수정 (선택)",
        value=selected.get("topic", ""),
        help="선택한 주제를 그대로 사용하거나 수정할 수 있습니다."
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 이전 단계"):
            st.session_state.step = 0
            st.rerun()

    with col2:
        if st.button("🚀 콘텐츠 생성 시작", type="primary"):
            st.session_state.selected_topic = edit_topic or selected.get("topic", "")
            st.session_state.step = 2
            st.rerun()


def render_step2_generating():
    """Step 2: 생성 중 화면."""
    st.header("⚙️ 콘텐츠 생성 중...")

    topic = st.session_state.selected_topic
    st.info(f"**주제:** {topic}")

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # Step 1: 랭킹 (Gemini)
        status_text.markdown("🔵 **Gemini**가 주제를 분석하고 있어요...")
        progress_bar.progress(10)

        step1_result = pipeline.step1_ranking(
            [topic],
            st.session_state.target_date
        )

        # Step 2: 구조 설계 (Claude)
        status_text.markdown("🟣 **Claude**가 구조를 설계하고 있어요...")
        progress_bar.progress(30)

        step2_result = pipeline.step2_structure(topic)

        # Step 3: 문장 생성 (Claude)
        status_text.markdown("🟣 **Claude**가 따뜻한 영어 문장을 만들고 있어요...")
        progress_bar.progress(50)

        category = db_loader.categorize_topic(topic)
        step3_result = pipeline.step3_generate(step2_result, category=category)

        # Step 4: 검수 (GPT)
        status_text.markdown("🟢 **GPT**가 품질을 검수하고 있어요...")
        progress_bar.progress(80)

        step4_result = pipeline.step4_review(step3_result, category=category)

        progress_bar.progress(100)
        status_text.markdown("✅ **완료!**")

        st.session_state.pipeline_result = {
            "topic": topic,
            "target_date": st.session_state.target_date.strftime("%Y-%m-%d"),
            "steps": {
                "step1": step1_result,
                "step2": step2_result,
                "step3": step3_result,
                "step4": step4_result
            }
        }

        st.session_state.step = 3
        st.rerun()

    except Exception as e:
        st.error(f"생성 실패: {e}")
        if st.button("← 처음으로"):
            st.session_state.step = 0
            st.rerun()


def render_step3_results():
    """Step 3: 결과 화면."""
    st.header("✅ 생성 완료!")

    result = st.session_state.pipeline_result
    if not result:
        st.warning("결과가 없습니다.")
        if st.button("← 처음으로"):
            st.session_state.step = 0
            st.rerun()
        return

    topic = result.get("topic", "")
    target_date = result.get("target_date", "")

    st.success(f"**{topic}** - {target_date}")

    # 검수 결과 요약
    step4 = result.get("steps", {}).get("step4", {})
    overall = step4.get("overall_recommendation", {})
    best_combo = overall.get("best_combination", {})
    confidence = overall.get("confidence", "unknown")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        conf_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(confidence, "⚪")
        st.metric("신뢰도", f"{conf_emoji} {confidence.upper()}")
    with col2:
        st.metric("L1 추천", best_combo.get("level_1", "A") + "안")
    with col3:
        st.metric("L2 추천", best_combo.get("level_2", "A") + "안")
    with col4:
        st.metric("L3 추천", best_combo.get("level_3", "A") + "안")

    if overall.get("human_review_focus"):
        st.warning(f"💡 **검토 포인트:** {overall.get('human_review_focus')}")

    st.divider()

    # 레벨별 결과 탭
    step3 = result.get("steps", {}).get("step3", {})
    levels = step3.get("levels", {})

    level_tabs = st.tabs(["Level 1 (2-3세)", "Level 2 (3-5세)", "Level 3 (4-6세)"])

    for i, (level_key, tab) in enumerate(zip(["level_1", "level_2", "level_3"], level_tabs)):
        with tab:
            render_level_variants(level_key, levels, step4, best_combo)

    st.divider()

    # Google Sheets 저장
    st.subheader("📊 Google Sheets에 저장")

    # 저장 상태 확인
    if "sheets_saved" not in st.session_state:
        st.session_state.sheets_saved = False

    if st.session_state.sheets_saved:
        st.success(f"✅ Google Sheets에 저장 완료! [시트 열기]({st.session_state.sheets_url})")
    else:
        if st.button("📊 Google Sheets에 저장", type="primary"):
            with st.spinner("Google Sheets에 저장 중..."):
                try:
                    import sheets_writer

                    # 추천 조합으로 텍스트 추출
                    l1_text = levels.get("level_1", {}).get("variants", {}).get(best_combo.get("level_1", "A"), {}).get("admin_text", "")
                    l2_text = levels.get("level_2", {}).get("variants", {}).get(best_combo.get("level_2", "A"), {}).get("admin_text", "")
                    l3_text = levels.get("level_3", {}).get("variants", {}).get(best_combo.get("level_3", "A"), {}).get("admin_text", "")

                    result_save = sheets_writer.append_content(
                        topic=topic,
                        target_date=target_date,
                        level1_text=l1_text,
                        level2_text=l2_text,
                        level3_text=l3_text
                    )

                    if result_save['success']:
                        st.session_state.sheets_saved = True
                        st.session_state.sheets_url = result_save['url']
                        st.success(f"✅ 저장 완료! No.{result_save['no']} 추가됨")
                        st.rerun()
                    else:
                        st.error(f"저장 실패: {result_save['error']}")
                except Exception as e:
                    st.error(f"Google Sheets 연동 실패: {e}")

    st.divider()

    # 다운로드 버튼
    st.subheader("📥 파일 다운로드")

    col1, col2, col3 = st.columns(3)

    with col1:
        json_str = json.dumps(result, ensure_ascii=False, indent=2)
        st.download_button(
            "📄 JSON",
            data=json_str,
            file_name=f"{target_date}_{topic[:10]}.json",
            mime="application/json"
        )

    with col2:
        admin_text = generate_admin_text(result)
        st.download_button(
            "📝 Admin 텍스트",
            data=admin_text,
            file_name=f"{target_date}_{topic[:10]}_admin.txt",
            mime="text/plain"
        )

    with col3:
        csv_content = generate_csv(result)
        st.download_button(
            "📊 CSV",
            data=csv_content,
            file_name=f"{target_date}_{topic[:10]}.csv",
            mime="text/csv"
        )

    st.divider()

    if st.button("🔄 새 콘텐츠 생성"):
        st.session_state.step = 0
        st.session_state.suggestions = []
        st.session_state.selected_topic = ""
        st.session_state.pipeline_result = None
        st.rerun()


def render_level_variants(level_key: str, levels: dict, step4: dict, best_combo: dict):
    """레벨별 A/B/C 변형 렌더링."""
    level_data = levels.get(level_key, {})
    variants = level_data.get("variants", {})

    review = step4.get("review", {}).get(level_key, {})
    review_variants = review.get("variants", {})
    best_pick = best_combo.get(level_key, "A")

    var_tabs = st.tabs([f"{'⭐ ' if v == best_pick else ''}{v}안" for v in ["A", "B", "C"]])

    for var_key, var_tab in zip(["A", "B", "C"], var_tabs):
        with var_tab:
            var_data = variants.get(var_key, {})
            var_review = review_variants.get(var_key, {})

            scores = var_review.get("scores", {})
            total = var_review.get("total", 0)
            verdict = var_review.get("verdict", "unknown")

            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                verdict_emoji = {"pass": "✅", "revise": "⚠️", "reject": "❌"}.get(verdict, "❓")
                st.metric("판정", f"{verdict_emoji} {verdict.upper()}")
            with col2:
                st.metric("총점", f"{total}/80")

            with st.expander("점수 상세"):
                score_names = {
                    "naturalness": "자연스러움",
                    "grammar": "문법",
                    "level_compliance": "레벨 준수",
                    "level_differentiation": "레벨 차별성",
                    "flow": "흐름",
                    "korean_match": "한국어 대응",
                    "overlap_risk": "중복 위험",
                    "format_compliance": "형식 준수"
                }
                for key, name in score_names.items():
                    score = scores.get(key, 0)
                    st.progress(score / 10, text=f"{name}: {score}/10")

            st.subheader("📋 콘텐츠")
            admin_text = var_data.get("admin_text", "(없음)")
            st.code(admin_text, language=None)

            issues = var_review.get("issues", [])
            if issues:
                st.subheader("⚠️ 이슈")
                for issue in issues:
                    severity = issue.get("severity", "minor")
                    emoji = {"critical": "🔴", "major": "🟠", "minor": "🟡"}.get(severity, "⚪")
                    st.write(f"{emoji} **[{severity}]** {issue.get('detail', '')}")


def generate_admin_text(result: dict) -> str:
    """Admin 붙여넣기용 텍스트 생성."""
    topic = result.get("topic", "")
    target_date = result.get("target_date", "")

    step3 = result.get("steps", {}).get("step3", {})
    step4 = result.get("steps", {}).get("step4", {})
    levels = step3.get("levels", {})
    overall = step4.get("overall_recommendation", {})
    best_combo = overall.get("best_combination", {})

    text = f"# {topic}\n# 생성일: {target_date}\n\n"

    for level_key in ["level_1", "level_2", "level_3"]:
        level_data = levels.get(level_key, {})
        variants = level_data.get("variants", {})
        best_var = best_combo.get(level_key, "A")
        var_data = variants.get(best_var, {})

        text += f"## {level_key.upper()} (추천: {best_var}안)\n"
        text += var_data.get("admin_text", "(생성 실패)") + "\n\n"

    return text


def render_content_management():
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
    for content in reversed(filtered):  # 최신순 표시
        row_num = content.get("row_number", 0)
        date = content.get("date", "-")
        day = content.get("day", "-")
        topic = content.get("situation", "-")
        no = content.get("no", "-")

        with st.expander(f"**{date}** ({day}) - {topic}  [No.{no}]"):
            # 레벨별 콘텐츠 미리보기
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

            # 액션 버튼
            col1, col2, col3 = st.columns(3)

            with col1:
                if st.button("🔄 재생성", key=f"regen_{row_num}"):
                    # 재생성 모드로 전환
                    st.session_state.app_mode = "create"
                    st.session_state.step = 0
                    try:
                        st.session_state.target_date = datetime.strptime(date, "%Y-%m-%d")
                    except:
                        st.session_state.target_date = datetime.now()
                    st.session_state.selected_topic = topic
                    st.session_state.regenerate_row = row_num
                    st.rerun()

            with col2:
                pass  # 빈 공간

            with col3:
                if st.button("🗑️ 삭제", key=f"del_{row_num}", type="secondary"):
                    st.session_state[f"confirm_delete_{row_num}"] = True
                    st.rerun()

            # 삭제 확인
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


def generate_csv(result: dict) -> str:
    """CSV 콘텐츠 생성."""
    import csv
    import io

    topic = result.get("topic", "")
    target_date = result.get("target_date", "")

    step3 = result.get("steps", {}).get("step3", {})
    step4 = result.get("steps", {}).get("step4", {})
    levels = step3.get("levels", {})
    overall = step4.get("overall_recommendation", {})
    best_combo = overall.get("best_combination", {})

    dt = datetime.strptime(target_date, "%Y-%m-%d")
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    day_str = weekdays[dt.weekday()]

    l1_text = levels.get("level_1", {}).get("variants", {}).get(best_combo.get("level_1", "A"), {}).get("admin_text", "")
    l2_text = levels.get("level_2", {}).get("variants", {}).get(best_combo.get("level_2", "A"), {}).get("admin_text", "")
    l3_text = levels.get("level_3", {}).get("variants", {}).get(best_combo.get("level_3", "A"), {}).get("admin_text", "")

    next_no = db_loader.get_next_content_number()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["No.", "date", "day", "situation", "level1", "level2", "level3", "mommyvoca"])
    writer.writerow([next_no, target_date, day_str, topic, l1_text, l2_text, l3_text, ""])

    return output.getvalue()


if __name__ == "__main__":
    main()
