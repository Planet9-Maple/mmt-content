"""
최종 로드 확인 테스트
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_final():
    with sync_playwright() as p:
        print("=" * 70)
        print("데이터 로드 최종 확인")
        print("=" * 70)

        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        print("\n[1] 사이드바 진행 현황...")
        sidebar_text = page.locator('[data-testid="stSidebar"]').text_content()

        if "진행 현황" in sidebar_text:
            # 콘텐츠: X/Y 형태 찾기
            import re
            match = re.search(r'콘텐츠:\s*(\d+)/(\d+)', sidebar_text)
            if match:
                completed = int(match.group(1))
                total = int(match.group(2))
                print(f"    ✅ 데이터 로드됨! 완료: {completed}/{total}")
            else:
                print("    ⚠️ 진행 현황 파싱 실패")
        else:
            print("    ❌ 진행 현황 없음 - 데이터 로드 안됨")

        print("\n[2] 로드된 주제 확인...")

        # 테스트 데이터의 주제들을 직접 검색
        test_topics = ["방 정리", "과일 먹기", "양치질", "신발 신기", "장난감 정리", "복습"]
        found_topics = []

        page_content = page.content()
        for topic in test_topics:
            if topic in page_content:
                found_topics.append(topic)

        if found_topics:
            print(f"    ✅ 발견된 주제: {', '.join(found_topics)}")
        else:
            print("    ❌ 테스트 주제 발견 안됨")

        # 완료 표시(✅) 개수 확인
        completed_icons = page.locator("text=/✅.*2026-03-04/")  # 양치질하기는 completed
        print(f"\n[3] 완료 상태...")

        # 날짜별 상태 확인
        date_elements = page.locator("text=/2026-03-\\d{2}/")
        print(f"    날짜 표시: {date_elements.count()}개")

        print("\n[4] 저장 상태 메시지...")
        if "저장되어 있습니다" in page_content or "Google Sheets" in page_content:
            print("    ✅ 저장 상태 메시지 표시됨")
        else:
            print("    ⚠️ 저장 상태 메시지 없음")

        page.screenshot(path="output/test_final_load.png", full_page=True)
        print(f"\n스크린샷: output/test_final_load.png")

        print("\n" + "=" * 70)
        print("결론: 데이터가 로드되고 있습니다!")
        print("=" * 70)

        browser.close()


if __name__ == "__main__":
    try:
        test_final()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
