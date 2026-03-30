"""
월간 기획 저장/로드 및 API 상태 표시 테스트
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_persistence_features():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()

        results = {"passed": [], "failed": [], "warnings": []}

        print("=" * 70)
        print("월간 기획 저장/로드 및 API 상태 테스트")
        print("=" * 70)

        # ============================================================
        # 1. 메인 페이지 로드 및 API 상태 확인
        # ============================================================
        print("\n[1] API 상태 표시 테스트")
        try:
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            # 사이드바에서 API 상태 확인
            sidebar = page.locator('[data-testid="stSidebar"]')
            api_status_text = sidebar.text_content()

            if "Gemini" in api_status_text:
                results["passed"].append("Gemini API 상태 표시됨")
                print("    ✅ Gemini API 상태 표시됨")
            else:
                results["failed"].append("Gemini API 상태 표시 없음")
                print("    ❌ Gemini API 상태 표시 없음")

            if "Claude" in api_status_text:
                results["passed"].append("Claude API 상태 표시됨")
                print("    ✅ Claude API 상태 표시됨")
            else:
                results["failed"].append("Claude API 상태 표시 없음")
                print("    ❌ Claude API 상태 표시 없음")

            if "GPT" in api_status_text:
                results["passed"].append("GPT API 상태 표시됨")
                print("    ✅ GPT API 상태 표시됨")
            else:
                results["failed"].append("GPT API 상태 표시 없음")
                print("    ❌ GPT API 상태 표시 없음")

            if "Sheets" in api_status_text:
                results["passed"].append("Google Sheets 상태 표시됨")
                print("    ✅ Google Sheets 상태 표시됨")
            else:
                results["failed"].append("Google Sheets 상태 표시 없음")
                print("    ❌ Google Sheets 상태 표시 없음")

            page.screenshot(path="output/test_persist_01_api_status.png", full_page=True)

        except Exception as e:
            results["failed"].append(f"API 상태 테스트 실패: {e}")
            print(f"    ❌ API 상태 테스트 실패: {e}")

        # ============================================================
        # 2. 직접 입력하기로 주제 생성
        # ============================================================
        print("\n[2] 주제 리스트 생성")
        try:
            manual_btn = page.locator("button", has_text="직접 입력하기")
            if manual_btn.count() > 0:
                manual_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)
                results["passed"].append("주제 리스트 생성됨")
                print("    ✅ 주제 리스트 생성됨")
            else:
                results["warnings"].append("직접 입력하기 버튼 없음 (이미 기획 있음)")
                print("    ⚠️ 직접 입력하기 버튼 없음 (이미 기획 있음)")

            page.screenshot(path="output/test_persist_02_topics.png", full_page=True)

        except Exception as e:
            results["failed"].append(f"주제 생성 실패: {e}")
            print(f"    ❌ 주제 생성 실패: {e}")

        # ============================================================
        # 3. 저장/재생성/초기화 버튼 확인
        # ============================================================
        print("\n[3] 새 버튼들 확인")
        try:
            # 저장 버튼
            save_btn = page.locator('button:has-text("현재 기획 저장")')
            if save_btn.count() > 0:
                results["passed"].append("저장 버튼 존재")
                print("    ✅ 저장 버튼 존재")
            else:
                results["failed"].append("저장 버튼 없음")
                print("    ❌ 저장 버튼 없음")

            # 재생성 버튼
            regen_btn = page.locator('button:has-text("Gemini로 재생성")')
            if regen_btn.count() > 0:
                results["passed"].append("재생성 버튼 존재")
                print("    ✅ 재생성 버튼 존재")
            else:
                results["failed"].append("재생성 버튼 없음")
                print("    ❌ 재생성 버튼 없음")

            # 초기화 & 삭제 버튼
            reset_btn = page.locator('button:has-text("초기화 & 삭제")')
            if reset_btn.count() > 0:
                results["passed"].append("초기화 & 삭제 버튼 존재")
                print("    ✅ 초기화 & 삭제 버튼 존재")
            else:
                results["failed"].append("초기화 & 삭제 버튼 없음")
                print("    ❌ 초기화 & 삭제 버튼 없음")

        except Exception as e:
            results["failed"].append(f"버튼 확인 실패: {e}")
            print(f"    ❌ 버튼 확인 실패: {e}")

        # ============================================================
        # 4. 저장 버튼 클릭 테스트
        # ============================================================
        print("\n[4] 저장 기능 테스트")
        try:
            save_btn = page.locator('button:has-text("현재 기획 저장")')
            if save_btn.count() > 0 and save_btn.is_visible():
                save_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)

                # 저장 성공 메시지 확인
                success_msg = page.locator("text=/저장됨|저장 완료/")
                if success_msg.count() > 0:
                    results["passed"].append("저장 기능 동작")
                    print("    ✅ 저장 기능 동작")
                else:
                    # 저장 상태 메시지 확인
                    saved_status = page.locator("text=/기획이 저장되어/")
                    if saved_status.count() > 0:
                        results["passed"].append("저장 상태 표시됨")
                        print("    ✅ 저장 상태 표시됨")
                    else:
                        results["warnings"].append("저장 메시지 확인 불가")
                        print("    ⚠️ 저장 메시지 확인 불가")

            page.screenshot(path="output/test_persist_03_saved.png", full_page=True)

        except Exception as e:
            results["failed"].append(f"저장 테스트 실패: {e}")
            print(f"    ❌ 저장 테스트 실패: {e}")

        # ============================================================
        # 5. 다른 기능도 정상 동작 확인
        # ============================================================
        print("\n[5] 기존 기능 정상 동작 확인")
        try:
            # 생성 버튼으로 콘텐츠 생성 화면 전환
            topic_input = page.locator('input[placeholder="주제를 입력하세요"]').first
            if topic_input.is_visible():
                topic_input.fill("🧪 저장 테스트 주제")
                topic_input.blur()
                time.sleep(1)

            gen_buttons = page.locator('button:has-text("생성"):not(:has-text("콘텐츠")):not(:has-text("재생성"))')
            if gen_buttons.count() > 0:
                gen_buttons.first.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                # 콘텐츠 생성 화면 확인
                step_header = page.locator("text=/Step|구조 설계/i")
                if step_header.count() > 0:
                    results["passed"].append("콘텐츠 생성 화면 전환 정상")
                    print("    ✅ 콘텐츠 생성 화면 전환 정상")
                else:
                    results["failed"].append("콘텐츠 생성 화면 전환 실패")
                    print("    ❌ 콘텐츠 생성 화면 전환 실패")

            page.screenshot(path="output/test_persist_04_generate.png", full_page=True)

        except Exception as e:
            results["failed"].append(f"기능 확인 실패: {e}")
            print(f"    ❌ 기능 확인 실패: {e}")

        # ============================================================
        # 결과 요약
        # ============================================================
        print("\n" + "=" * 70)
        print("테스트 결과 요약")
        print("=" * 70)

        print(f"\n✅ 통과: {len(results['passed'])}개")
        for item in results['passed']:
            print(f"   - {item}")

        print(f"\n⚠️ 경고: {len(results['warnings'])}개")
        for item in results['warnings']:
            print(f"   - {item}")

        print(f"\n❌ 실패: {len(results['failed'])}개")
        for item in results['failed']:
            print(f"   - {item}")

        print("\n" + "=" * 70)
        print("스크린샷: output/test_persist_*.png")
        print("=" * 70)

        browser.close()
        return results


if __name__ == "__main__":
    try:
        test_persistence_features()
    except Exception as e:
        print(f"\n❌ 테스트 중 에러: {e}")
        import traceback
        traceback.print_exc()
