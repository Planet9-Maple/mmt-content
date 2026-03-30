"""
생성 버튼 클릭 테스트 - 모드 전환 확인
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_generate_button():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()

        print("=" * 60)
        print("생성 버튼 테스트 - 모드 전환 확인")
        print("=" * 60)

        # 1. 메인 페이지 로드
        print("\n[1] 메인 페이지 로드...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 현재 모드 확인
        headers = page.locator("h2, h3")
        print(f"    현재 화면 헤더: {headers.first.text_content() if headers.count() > 0 else 'N/A'}")

        # 2. 직접 입력하기 클릭
        print("\n[2] 직접 입력하기 클릭...")
        manual_btn = page.locator("button", has_text="직접 입력하기")
        if manual_btn.count() > 0:
            manual_btn.click()
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            print("    ✅ 주제 리스트 생성됨")

        page.screenshot(path="output/test_01_topic_list.png", full_page=True)

        # 3. 주제 입력
        print("\n[3] 주제 입력...")
        topic_input = page.locator('input[placeholder="주제를 입력하세요"]').first
        if topic_input.is_visible():
            topic_input.fill("🧹 방 정리하기")
            topic_input.blur()
            time.sleep(1)
            print("    ✅ 주제 입력: 🧹 방 정리하기")

        page.screenshot(path="output/test_02_topic_input.png", full_page=True)

        # 4. 생성 버튼 클릭 전 상태 확인
        print("\n[4] 생성 버튼 클릭 전 상태...")
        sidebar_radio = page.locator('[data-testid="stSidebar"] [role="radiogroup"]')
        if sidebar_radio.count() > 0:
            checked = page.locator('[data-testid="stSidebar"] input[type="radio"]:checked')
            label = page.evaluate('''(el) => {
                const label = el.closest('label') || el.nextElementSibling;
                return label ? label.textContent : 'unknown';
            }''', checked.element_handle()) if checked.count() > 0 else "N/A"
            print(f"    사이드바 선택: {label}")

        # 5. 생성 버튼 클릭
        print("\n[5] 생성 버튼 클릭...")
        gen_buttons = page.locator('button:has-text("생성"):not(:has-text("콘텐츠"))')
        print(f"    생성 버튼 수: {gen_buttons.count()}")

        if gen_buttons.count() > 0:
            first_gen = gen_buttons.first
            first_gen.scroll_into_view_if_needed()
            time.sleep(0.5)

            # 클릭
            first_gen.click()
            print("    버튼 클릭됨!")

            # 페이지 변화 대기
            page.wait_for_load_state("networkidle")
            time.sleep(4)

        page.screenshot(path="output/test_03_after_click.png", full_page=True)

        # 6. 클릭 후 상태 확인
        print("\n[6] 클릭 후 상태 확인...")

        # 현재 헤더 확인
        headers = page.locator("h2, h3")
        for i in range(min(headers.count(), 3)):
            print(f"    헤더 {i+1}: {headers.nth(i).text_content()}")

        # 사이드바 라디오 상태
        checked = page.locator('[data-testid="stSidebar"] input[type="radio"]:checked')
        if checked.count() > 0:
            label = page.evaluate('''(el) => {
                const label = el.closest('label') || el.nextElementSibling;
                return label ? label.textContent : 'unknown';
            }''', checked.element_handle())
            print(f"    사이드바 선택: {label}")

        # 콘텐츠 생성 관련 요소 확인
        step_indicators = page.locator("text=/Step|단계|구조/i")
        if step_indicators.count() > 0:
            print("    ✅ 콘텐츠 생성 화면으로 전환됨!")
        else:
            # 주제 기획 화면인지 확인
            planning_indicators = page.locator("text=/주제 기획|월간|직접 입력/i")
            if planning_indicators.count() > 0:
                print("    ❌ 아직 주제 기획 화면임 (전환 실패)")
            else:
                print("    ⚠️ 화면 상태 불명확")

        print("\n" + "=" * 60)
        print("스크린샷 저장됨:")
        print("  - output/test_01_topic_list.png")
        print("  - output/test_02_topic_input.png")
        print("  - output/test_03_after_click.png")
        print("=" * 60)

        browser.close()


if __name__ == "__main__":
    try:
        test_generate_button()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
