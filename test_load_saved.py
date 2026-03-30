"""
저장된 데이터 로드 테스트
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_load_saved():
    with sync_playwright() as p:
        print("=" * 70)
        print("저장된 데이터 로드 테스트")
        print("=" * 70)

        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})

        print("\n[1] 페이지 접속...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(4)

        print("\n[2] 로드된 데이터 확인...")

        # 주제 입력 필드 확인
        topic_inputs = page.locator('input[placeholder="주제를 입력하세요"]')
        topic_count = topic_inputs.count()
        print(f"    입력 필드 수: {topic_count}")

        if topic_count > 0:
            # 각 입력 필드의 값 출력
            print("\n    로드된 주제:")
            for i in range(min(topic_count, 5)):
                value = topic_inputs.nth(i).input_value()
                print(f"      {i+1}. {value if value else '(비어있음)'}")

            # 완료 상태 확인
            completed_markers = page.locator("text=✅")
            print(f"\n    ✅ 완료 표시: {completed_markers.count()}개")

            # 복습 표시 확인
            review_markers = page.locator("text=/📚.*복습/")
            print(f"    📚 복습 표시: {review_markers.count()}개")

            print("\n    ✅ 데이터 로드 성공!")
        else:
            # 직접 입력 버튼이 있으면 로드 안됨
            manual_btn = page.locator("button", has_text="직접 입력하기")
            if manual_btn.count() > 0:
                print("    ❌ 데이터 로드 실패 - 빈 화면")
            else:
                print("    ⚠️ 상태 불명확")

        page.screenshot(path="output/test_load_saved.png", full_page=True)
        print("\n    스크린샷: output/test_load_saved.png")

        browser.close()

        print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        test_load_saved()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
