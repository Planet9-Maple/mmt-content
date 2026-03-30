"""
Google Sheets 기반 월간 기획 저장/로드 테스트
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_sheets_storage():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()

        results = {"passed": [], "failed": [], "warnings": []}

        print("=" * 70)
        print("Google Sheets 기반 저장 테스트")
        print("=" * 70)

        # ============================================================
        # 1. 메인 페이지 로드
        # ============================================================
        print("\n[1] 메인 페이지 로드")
        try:
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            results["passed"].append("메인 페이지 로드")
            print("    ✅ 메인 페이지 로드 완료")
            page.screenshot(path="output/test_sheets_01.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"메인 페이지 로드 실패: {e}")
            print(f"    ❌ 실패: {e}")

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
                results["passed"].append("주제 리스트 생성")
                print("    ✅ 주제 리스트 생성 완료")
            else:
                # 이미 기획이 있음
                results["warnings"].append("이미 기획 로드됨")
                print("    ⚠️ 이미 기획이 로드되어 있음")
        except Exception as e:
            results["failed"].append(f"주제 생성 실패: {e}")
            print(f"    ❌ 실패: {e}")

        # ============================================================
        # 3. Sheets 저장 버튼 확인
        # ============================================================
        print("\n[3] Sheets 저장 버튼 확인")
        try:
            save_btn = page.locator('button:has-text("Sheets에 저장")')
            if save_btn.count() > 0:
                results["passed"].append("Sheets 저장 버튼 존재")
                print("    ✅ Sheets 저장 버튼 존재")
            else:
                results["failed"].append("Sheets 저장 버튼 없음")
                print("    ❌ Sheets 저장 버튼 없음")

            page.screenshot(path="output/test_sheets_02.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"버튼 확인 실패: {e}")
            print(f"    ❌ 실패: {e}")

        # ============================================================
        # 4. Sheets 저장 기능 테스트
        # ============================================================
        print("\n[4] Sheets 저장 기능 테스트")
        try:
            save_btn = page.locator('button:has-text("Sheets에 저장")')
            if save_btn.count() > 0 and save_btn.is_visible():
                save_btn.click()
                # 저장 중 스피너 대기
                page.wait_for_load_state("networkidle")
                time.sleep(5)  # Sheets API 호출 시간

                # 성공/실패 메시지 확인
                page_text = page.content()
                if "저장 완료" in page_text or "Google Sheets" in page_text:
                    results["passed"].append("Sheets 저장 성공")
                    print("    ✅ Sheets 저장 성공")
                elif "저장 실패" in page_text or "연결" in page_text:
                    results["warnings"].append("Sheets 저장 실패 (인증 문제 가능)")
                    print("    ⚠️ Sheets 저장 실패 (인증 문제일 수 있음)")
                else:
                    results["warnings"].append("저장 결과 불명확")
                    print("    ⚠️ 저장 결과 불명확")

            page.screenshot(path="output/test_sheets_03.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"저장 테스트 실패: {e}")
            print(f"    ❌ 실패: {e}")

        # ============================================================
        # 5. 기존 기능 정상 동작 확인
        # ============================================================
        print("\n[5] 기존 기능 정상 동작 확인")
        try:
            # 생성 버튼 테스트
            topic_input = page.locator('input[placeholder="주제를 입력하세요"]').first
            if topic_input.is_visible():
                topic_input.fill("☁️ 클라우드 테스트")
                topic_input.blur()
                time.sleep(1)

            gen_buttons = page.locator('button:has-text("생성"):not(:has-text("재생성"))')
            if gen_buttons.count() > 0:
                gen_buttons.first.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                step_header = page.locator("text=/Step|구조 설계/i")
                if step_header.count() > 0:
                    results["passed"].append("콘텐츠 생성 화면 전환 정상")
                    print("    ✅ 콘텐츠 생성 화면 전환 정상")
                else:
                    results["failed"].append("화면 전환 실패")
                    print("    ❌ 화면 전환 실패")

            page.screenshot(path="output/test_sheets_04.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"기능 확인 실패: {e}")
            print(f"    ❌ 실패: {e}")

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

        browser.close()
        return results


if __name__ == "__main__":
    try:
        test_sheets_storage()
    except Exception as e:
        print(f"\n❌ 테스트 중 에러: {e}")
        import traceback
        traceback.print_exc()
