"""
생성 버튼 클릭 테스트 - 개선된 버전
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
        print("생성 버튼 클릭 테스트 (개선)")
        print("=" * 60)

        # 1. 메인 페이지 로드
        print("\n[1] 메인 페이지 로드...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(4)

        # 2. 직접 입력하기 클릭
        print("\n[2] 주제 리스트 생성...")
        manual_btn = page.locator("button", has_text="직접 입력하기")
        if manual_btn.count() > 0:
            manual_btn.click()
            page.wait_for_load_state("networkidle")
            time.sleep(4)
            print("    ✅ 리스트 생성됨")

        # 3. 첫 번째 주제 입력
        print("\n[3] 주제 입력...")
        text_inputs = page.locator('input[type="text"]')
        print(f"    텍스트 입력 필드 수: {text_inputs.count()}")

        # placeholder로 주제 입력 필드 찾기
        topic_input = page.locator('input[placeholder="주제를 입력하세요"]').first
        if topic_input.is_visible():
            topic_input.fill("🧹 방 정리하기")
            print("    ✅ 주제 입력: 🧹 방 정리하기")

            # 입력 후 blur (포커스 해제)
            topic_input.blur()
            time.sleep(1)

        page.screenshot(path="output/test_gen_02_input.png", full_page=True)

        # 4. 생성 버튼 클릭 - 여러 방법 시도
        print("\n[4] 생성 버튼 클릭...")

        # 첫 번째 생성 버튼 찾기
        gen_buttons = page.locator('button:has-text("생성"):not(:has-text("콘텐츠"))')
        print(f"    생성 버튼 수: {gen_buttons.count()}")

        if gen_buttons.count() > 0:
            first_gen = gen_buttons.first

            # 버튼으로 스크롤
            first_gen.scroll_into_view_if_needed()
            time.sleep(0.5)

            # 방법 1: 일반 클릭
            print("    시도 1: 일반 클릭")
            first_gen.click()
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            # 화면 확인
            current_header = page.locator("h2, h3").first.text_content() if page.locator("h2, h3").count() > 0 else ""
            print(f"    현재 헤더: {current_header}")

            if "구조" in current_header or "Step" in current_header:
                print("    ✅ 콘텐츠 생성 화면으로 전환됨!")
            else:
                # 방법 2: force 클릭
                print("    시도 2: force 클릭")
                first_gen.click(force=True)
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                current_header = page.locator("h2, h3").first.text_content() if page.locator("h2, h3").count() > 0 else ""
                print(f"    현재 헤더: {current_header}")

        page.screenshot(path="output/test_gen_03_after_click.png", full_page=True)

        # 5. 최종 화면 상태
        print("\n[5] 최종 화면 상태...")

        # 모든 헤더 출력
        headers = page.locator("h1, h2, h3")
        for i in range(min(headers.count(), 5)):
            print(f"    헤더 {i+1}: {headers.nth(i).text_content()}")

        # 사이드바 메뉴 상태 확인
        sidebar_labels = page.locator('[data-testid="stSidebar"] label')
        for i in range(min(sidebar_labels.count(), 4)):
            label_text = sidebar_labels.nth(i).text_content()
            if "●" in str(page.locator(f'[data-testid="stSidebar"] input').nth(i).get_attribute("checked") or ""):
                print(f"    선택된 메뉴: {label_text}")

        print("\n" + "=" * 60)
        browser.close()


if __name__ == "__main__":
    try:
        test_generate_button()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
