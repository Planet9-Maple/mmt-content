"""
세션 종료 후 재접속 시 데이터 로드 테스트
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_reload_flow():
    with sync_playwright() as p:
        print("=" * 70)
        print("세션 종료 후 재접속 데이터 로드 테스트")
        print("=" * 70)

        # ============================================================
        # 1단계: 첫 번째 세션 - 주제 생성 및 저장
        # ============================================================
        print("\n[1단계] 첫 번째 세션 - 주제 생성")

        browser1 = p.chromium.launch(headless=True)
        page1 = browser1.new_page(viewport={"width": 1400, "height": 1000})

        page1.goto(BASE_URL)
        page1.wait_for_load_state("networkidle")
        time.sleep(3)

        # 기존 기획이 있는지 확인
        existing_topics = page1.locator('input[placeholder="주제를 입력하세요"]')
        if existing_topics.count() > 0:
            print("    ✅ 기존 기획 있음")
            topic_count = existing_topics.count()
        else:
            # 직접 입력하기로 생성
            manual_btn = page1.locator("button", has_text="직접 입력하기")
            if manual_btn.count() > 0:
                manual_btn.click()
                page1.wait_for_load_state("networkidle")
                time.sleep(3)
            topic_count = page1.locator('input[placeholder="주제를 입력하세요"]').count()
            print(f"    ✅ 새 기획 생성됨 ({topic_count}개 입력 필드)")

        # 첫 번째 주제에 테스트 데이터 입력
        first_input = page1.locator('input[placeholder="주제를 입력하세요"]').first
        if first_input.is_visible():
            test_topic = f"🧪 리로드 테스트 {int(time.time())}"
            first_input.fill(test_topic)
            first_input.blur()
            time.sleep(1)
            print(f"    ✅ 테스트 주제 입력: {test_topic}")

        # 저장
        save_btn = page1.locator('button:has-text("Sheets에 저장")')
        if save_btn.count() > 0:
            save_btn.click()
            page1.wait_for_load_state("networkidle")
            time.sleep(3)
            print("    ✅ 저장 버튼 클릭")

        page1.screenshot(path="output/test_reload_01_saved.png", full_page=True)

        # 브라우저 완전히 종료 (세션 종료 시뮬레이션)
        browser1.close()
        print("    ✅ 브라우저 종료 (세션 종료)")

        # ============================================================
        # 2단계: 두 번째 세션 - 재접속하여 데이터 로드 확인
        # ============================================================
        print("\n[2단계] 두 번째 세션 - 재접속")

        time.sleep(2)  # 잠시 대기

        browser2 = p.chromium.launch(headless=True)
        page2 = browser2.new_page(viewport={"width": 1400, "height": 1000})

        page2.goto(BASE_URL)
        page2.wait_for_load_state("networkidle")
        time.sleep(4)

        page2.screenshot(path="output/test_reload_02_reloaded.png", full_page=True)

        # 데이터가 로드되었는지 확인
        loaded_topics = page2.locator('input[placeholder="주제를 입력하세요"]')

        if loaded_topics.count() > 0:
            print(f"    ✅ 기획 자동 로드됨! ({loaded_topics.count()}개 입력 필드)")

            # 첫 번째 주제 값 확인
            first_value = loaded_topics.first.input_value()
            if "테스트" in first_value or "리로드" in first_value:
                print(f"    ✅ 저장된 주제 복원됨: {first_value}")
            else:
                print(f"    ⚠️ 첫 번째 주제 값: {first_value}")

            # 저장 상태 메시지 확인
            page_text = page2.content()
            if "저장되어 있습니다" in page_text or "Google Sheets" in page_text:
                print("    ✅ 저장 상태 메시지 표시됨")
        else:
            # 직접 입력 버튼이 있으면 로드 실패
            if page2.locator("button", has_text="직접 입력하기").count() > 0:
                print("    ❌ 데이터 로드 실패 - 빈 상태로 표시됨")
            else:
                print("    ⚠️ 상태 불명확")

        browser2.close()

        # ============================================================
        # 3단계: 다른 월 선택 후 다시 3월 선택
        # ============================================================
        print("\n[3단계] 다른 월 → 3월 재선택 테스트")

        browser3 = p.chromium.launch(headless=True)
        page3 = browser3.new_page(viewport={"width": 1400, "height": 1000})

        page3.goto(BASE_URL)
        page3.wait_for_load_state("networkidle")
        time.sleep(3)

        # 현재 3월 데이터 확인
        initial_topics = page3.locator('input[placeholder="주제를 입력하세요"]')
        initial_count = initial_topics.count()
        print(f"    현재 상태: {initial_count}개 입력 필드")

        # 콘텐츠 관리 메뉴로 이동
        mgmt_menu = page3.locator('[data-testid="stSidebar"] label:has-text("콘텐츠 관리")')
        if mgmt_menu.count() > 0:
            mgmt_menu.click()
            page3.wait_for_load_state("networkidle")
            time.sleep(2)
            print("    ✅ 콘텐츠 관리로 이동")

        # 다시 월간 기획으로 돌아가기
        planning_menu = page3.locator('[data-testid="stSidebar"] label:has-text("월간 주제 기획")')
        if planning_menu.count() > 0:
            planning_menu.click()
            page3.wait_for_load_state("networkidle")
            time.sleep(3)
            print("    ✅ 월간 기획으로 복귀")

        # 데이터 유지 확인
        final_topics = page3.locator('input[placeholder="주제를 입력하세요"]')
        if final_topics.count() > 0:
            print(f"    ✅ 데이터 유지됨! ({final_topics.count()}개 입력 필드)")
        else:
            print("    ❌ 데이터 손실됨")

        page3.screenshot(path="output/test_reload_03_final.png", full_page=True)
        browser3.close()

        print("\n" + "=" * 70)
        print("테스트 완료!")
        print("스크린샷: output/test_reload_*.png")
        print("=" * 70)


if __name__ == "__main__":
    try:
        test_reload_flow()
    except Exception as e:
        print(f"\n❌ 테스트 중 에러: {e}")
        import traceback
        traceback.print_exc()
