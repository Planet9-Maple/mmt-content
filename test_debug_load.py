"""
디버그 로드 테스트 - HTML 분석
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_debug():
    with sync_playwright() as p:
        print("=" * 70)
        print("디버그 로드 테스트")
        print("=" * 70)

        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})

        print("\n[1] 페이지 접속...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(5)  # 더 긴 대기 시간

        print("\n[2] 페이지 내용 분석...")

        # 주요 요소들 확인
        elements = {
            "제목 (h1)": page.locator("h1").count(),
            "헤더 (h2)": page.locator("h2").count(),
            "버튼 전체": page.locator("button").count(),
            "직접 입력하기 버튼": page.locator("button:has-text('직접 입력하기')").count(),
            "Gemini 버튼": page.locator("button:has-text('Gemini')").count(),
            "text input 전체": page.locator('input[type="text"]').count(),
            "주제 입력 필드": page.locator('input[placeholder="주제를 입력하세요"]').count(),
            "저장 버튼": page.locator('button:has-text("Sheets에 저장")').count(),
            "생성 버튼": page.locator('button:has-text("생성")').count(),
        }

        for name, count in elements.items():
            status = "✅" if count > 0 else "❌"
            print(f"    {status} {name}: {count}개")

        # 헤더 텍스트 출력
        print("\n[3] 헤더 내용...")
        headers = page.locator("h1, h2, h3")
        for i in range(min(headers.count(), 5)):
            print(f"    - {headers.nth(i).text_content()}")

        # 사이드바 상태
        print("\n[4] 사이드바 상태...")
        sidebar = page.locator('[data-testid="stSidebar"]')
        if sidebar.count() > 0:
            # 선택된 라디오 확인
            selected_radio = sidebar.locator('input[type="radio"]:checked')
            if selected_radio.count() > 0:
                label = page.evaluate('''(el) => {
                    const label = el.closest('label');
                    return label ? label.textContent : 'unknown';
                }''', selected_radio.first.element_handle())
                print(f"    선택된 메뉴: {label}")

        # 메인 영역 텍스트 샘플
        print("\n[5] 메인 영역 텍스트 샘플...")
        main_area = page.locator('[data-testid="stAppViewContainer"]')
        if main_area.count() > 0:
            text = main_area.text_content()[:500]
            print(f"    {text[:200]}...")

        page.screenshot(path="output/test_debug.png", full_page=True)
        print("\n[6] 스크린샷 저장: output/test_debug.png")

        browser.close()


if __name__ == "__main__":
    try:
        test_debug()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
