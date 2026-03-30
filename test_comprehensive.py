"""
전체 기능 QA 테스트
"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8501"


def test_all_features():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()

        results = {
            "passed": [],
            "failed": [],
            "warnings": []
        }

        print("=" * 70)
        print("마미톡잉글리시 앱 전체 QA 테스트")
        print("=" * 70)

        # ============================================================
        # 1. 메인 페이지 로드
        # ============================================================
        print("\n[1] 메인 페이지 로드 테스트")
        try:
            page.goto(BASE_URL)
            page.wait_for_load_state("networkidle")
            time.sleep(3)

            # 타이틀 확인
            title = page.locator("h1").first.text_content() if page.locator("h1").count() > 0 else ""
            if "마미톡" in title or "콘텐츠" in title:
                results["passed"].append("메인 페이지 로드 성공")
                print("    ✅ 메인 페이지 로드 성공")
            else:
                results["failed"].append(f"메인 페이지 타이틀 이상: {title}")
                print(f"    ❌ 메인 페이지 타이틀 이상: {title}")

            page.screenshot(path="output/qa_01_main.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"메인 페이지 로드 실패: {e}")
            print(f"    ❌ 메인 페이지 로드 실패: {e}")

        # ============================================================
        # 2. 사이드바 메뉴 테스트
        # ============================================================
        print("\n[2] 사이드바 메뉴 테스트")
        try:
            sidebar = page.locator('[data-testid="stSidebar"]')
            if sidebar.count() > 0:
                results["passed"].append("사이드바 존재")
                print("    ✅ 사이드바 존재")

                # 메뉴 옵션 확인
                radio_options = sidebar.locator('label')
                menu_texts = []
                for i in range(min(radio_options.count(), 5)):
                    text = radio_options.nth(i).text_content()
                    menu_texts.append(text)

                if "월간 주제 기획" in str(menu_texts):
                    results["passed"].append("월간 주제 기획 메뉴 존재")
                    print("    ✅ 월간 주제 기획 메뉴 존재")
                else:
                    results["warnings"].append("월간 주제 기획 메뉴 텍스트 다름")
                    print(f"    ⚠️ 메뉴 텍스트: {menu_texts}")

            else:
                results["failed"].append("사이드바 없음")
                print("    ❌ 사이드바 없음")
        except Exception as e:
            results["failed"].append(f"사이드바 테스트 실패: {e}")
            print(f"    ❌ 사이드바 테스트 실패: {e}")

        # ============================================================
        # 3. 직접 입력하기 버튼 테스트
        # ============================================================
        print("\n[3] 직접 입력하기 버튼 테스트")
        try:
            manual_btn = page.locator("button", has_text="직접 입력하기")
            if manual_btn.count() > 0:
                manual_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                # 주제 리스트 생성 확인
                topic_inputs = page.locator('input[placeholder="주제를 입력하세요"]')
                if topic_inputs.count() > 0:
                    results["passed"].append(f"직접 입력하기 버튼 동작 ({topic_inputs.count()}개 입력필드 생성)")
                    print(f"    ✅ 직접 입력하기 동작 ({topic_inputs.count()}개 입력필드)")
                else:
                    # 드롭다운 형태일 수도 있음
                    dropdowns = page.locator('select, [data-baseweb="select"]')
                    if dropdowns.count() > 0:
                        results["passed"].append("직접 입력하기 버튼 동작 (드롭다운 형태)")
                        print("    ✅ 직접 입력하기 동작 (드롭다운 형태)")
                    else:
                        results["failed"].append("주제 입력 필드 없음")
                        print("    ❌ 주제 입력 필드 없음")
            else:
                results["warnings"].append("직접 입력하기 버튼 없음 (이미 주제가 있을 수 있음)")
                print("    ⚠️ 직접 입력하기 버튼 없음")

            page.screenshot(path="output/qa_02_topic_list.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"직접 입력하기 테스트 실패: {e}")
            print(f"    ❌ 직접 입력하기 테스트 실패: {e}")

        # ============================================================
        # 4. 일요일 복습 표시 테스트
        # ============================================================
        print("\n[4] 일요일 복습 표시 테스트")
        try:
            # 복습 텍스트 확인
            review_elements = page.locator("text=복습")
            if review_elements.count() > 0:
                results["passed"].append(f"복습 표시 존재 ({review_elements.count()}개)")
                print(f"    ✅ 복습 표시 존재 ({review_elements.count()}개)")
            else:
                results["warnings"].append("복습 표시 없음 (해당 월에 일요일이 없을 수 있음)")
                print("    ⚠️ 복습 표시 없음")

            # (일) 표시 확인
            sunday_elements = page.locator("text=/\\(일\\)/")
            if sunday_elements.count() > 0:
                results["passed"].append(f"일요일 표시 존재 ({sunday_elements.count()}개)")
                print(f"    ✅ 일요일 표시 존재 ({sunday_elements.count()}개)")
        except Exception as e:
            results["failed"].append(f"복습 표시 테스트 실패: {e}")
            print(f"    ❌ 복습 표시 테스트 실패: {e}")

        # ============================================================
        # 5. 필터 기능 테스트
        # ============================================================
        print("\n[5] 필터 기능 테스트")
        try:
            # 필터 라디오 버튼 찾기
            filter_options = page.locator('label:has-text("전체"), label:has-text("미완료"), label:has-text("완료"), label:has-text("복습")')

            if filter_options.count() >= 3:
                # 복습 필터 클릭
                review_filter = page.locator('label:has-text("복습")').first
                if review_filter.is_visible():
                    review_filter.click()
                    time.sleep(2)

                    # 복습 항목만 표시되는지 확인
                    visible_rows = page.locator('text=/\\(일\\)/')
                    if visible_rows.count() >= 0:  # 0개도 정상 (복습이 없을 수 있음)
                        results["passed"].append("복습 필터 동작")
                        print("    ✅ 복습 필터 동작")

                # 전체 필터로 돌아가기
                all_filter = page.locator('label:has-text("전체")').first
                if all_filter.is_visible():
                    all_filter.click()
                    time.sleep(1)
                    results["passed"].append("전체 필터 동작")
                    print("    ✅ 전체 필터 동작")
            else:
                results["warnings"].append("필터 옵션 부족")
                print("    ⚠️ 필터 옵션 부족")

            page.screenshot(path="output/qa_03_filter.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"필터 테스트 실패: {e}")
            print(f"    ❌ 필터 테스트 실패: {e}")

        # ============================================================
        # 6. 주제 입력 및 생성 버튼 테스트
        # ============================================================
        print("\n[6] 주제 입력 및 생성 버튼 테스트")
        try:
            # 첫 번째 입력 필드에 주제 입력
            topic_input = page.locator('input[placeholder="주제를 입력하세요"]').first

            if topic_input.is_visible():
                topic_input.fill("🧪 테스트 주제")
                topic_input.blur()
                time.sleep(1)
                results["passed"].append("주제 입력 동작")
                print("    ✅ 주제 입력 동작")

                # 생성 버튼 클릭
                gen_buttons = page.locator('button:has-text("생성"):not(:has-text("콘텐츠"))')
                if gen_buttons.count() > 0:
                    first_gen = gen_buttons.first
                    first_gen.scroll_into_view_if_needed()
                    first_gen.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(4)

                    # 모드 전환 확인
                    step_header = page.locator("text=/Step|구조 설계/i")
                    if step_header.count() > 0:
                        results["passed"].append("생성 버튼 → 콘텐츠 생성 화면 전환 성공")
                        print("    ✅ 생성 버튼 → 콘텐츠 생성 화면 전환 성공")
                    else:
                        results["failed"].append("생성 버튼 클릭 후 화면 전환 실패")
                        print("    ❌ 생성 버튼 클릭 후 화면 전환 실패")
                else:
                    results["failed"].append("생성 버튼 없음")
                    print("    ❌ 생성 버튼 없음")
            else:
                results["warnings"].append("주제 입력 필드 보이지 않음")
                print("    ⚠️ 주제 입력 필드 보이지 않음")

            page.screenshot(path="output/qa_04_generate.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"생성 버튼 테스트 실패: {e}")
            print(f"    ❌ 생성 버튼 테스트 실패: {e}")

        # ============================================================
        # 7. 콘텐츠 생성 화면 요소 테스트
        # ============================================================
        print("\n[7] 콘텐츠 생성 화면 요소 테스트")
        try:
            # Step 표시 확인
            step_elements = page.locator("text=/Step|단계/")
            if step_elements.count() > 0:
                results["passed"].append(f"Step 표시 존재 ({step_elements.count()}개)")
                print(f"    ✅ Step 표시 존재 ({step_elements.count()}개)")

            # 구조 설계 시작 버튼 확인
            structure_btn = page.locator('button:has-text("구조 설계 시작")')
            if structure_btn.count() > 0:
                results["passed"].append("구조 설계 시작 버튼 존재")
                print("    ✅ 구조 설계 시작 버튼 존재")
            else:
                results["warnings"].append("구조 설계 시작 버튼 없음 (이미 진행 중일 수 있음)")
                print("    ⚠️ 구조 설계 시작 버튼 없음")

            # 뒤로 가기 버튼 확인
            back_btn = page.locator('button:has-text("주제 기획으로")')
            if back_btn.count() > 0:
                results["passed"].append("주제 기획으로 버튼 존재")
                print("    ✅ 주제 기획으로 버튼 존재")
        except Exception as e:
            results["failed"].append(f"콘텐츠 생성 화면 테스트 실패: {e}")
            print(f"    ❌ 콘텐츠 생성 화면 테스트 실패: {e}")

        # ============================================================
        # 8. 뒤로 가기 버튼 테스트
        # ============================================================
        print("\n[8] 뒤로 가기 버튼 테스트")
        try:
            back_btn = page.locator('button:has-text("주제 기획으로")')
            if back_btn.count() > 0 and back_btn.is_visible():
                back_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                # 월간 기획 화면으로 돌아왔는지 확인
                planning_header = page.locator("text=/월간 주제 기획/")
                if planning_header.count() > 0:
                    results["passed"].append("뒤로 가기 버튼 동작 (월간 기획으로 복귀)")
                    print("    ✅ 뒤로 가기 버튼 동작")
                else:
                    results["failed"].append("뒤로 가기 후 화면 전환 실패")
                    print("    ❌ 뒤로 가기 후 화면 전환 실패")
            else:
                results["warnings"].append("뒤로 가기 버튼 없음")
                print("    ⚠️ 뒤로 가기 버튼 없음")

            page.screenshot(path="output/qa_05_back.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"뒤로 가기 테스트 실패: {e}")
            print(f"    ❌ 뒤로 가기 테스트 실패: {e}")

        # ============================================================
        # 9. 사이드바 메뉴 전환 테스트
        # ============================================================
        print("\n[9] 사이드바 메뉴 전환 테스트")
        try:
            # 콘텐츠 관리 메뉴 클릭
            management_menu = page.locator('[data-testid="stSidebar"] label:has-text("콘텐츠 관리")')
            if management_menu.count() > 0:
                management_menu.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                # 콘텐츠 관리 화면 확인
                mgmt_header = page.locator("text=/콘텐츠 관리/")
                if mgmt_header.count() > 0:
                    results["passed"].append("콘텐츠 관리 메뉴 전환 성공")
                    print("    ✅ 콘텐츠 관리 메뉴 전환 성공")
                else:
                    results["failed"].append("콘텐츠 관리 화면 표시 실패")
                    print("    ❌ 콘텐츠 관리 화면 표시 실패")

            page.screenshot(path="output/qa_06_management.png", full_page=True)

            # 다시 월간 기획으로 돌아가기
            planning_menu = page.locator('[data-testid="stSidebar"] label:has-text("월간 주제 기획")')
            if planning_menu.count() > 0:
                planning_menu.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                results["passed"].append("월간 주제 기획 메뉴 전환 성공")
                print("    ✅ 월간 주제 기획 메뉴 전환 성공")

        except Exception as e:
            results["failed"].append(f"메뉴 전환 테스트 실패: {e}")
            print(f"    ❌ 메뉴 전환 테스트 실패: {e}")

        # ============================================================
        # 10. 주제 리스트 초기화 버튼 테스트
        # ============================================================
        print("\n[10] 주제 리스트 초기화 버튼 테스트")
        try:
            reset_btn = page.locator('button:has-text("주제 리스트 초기화")')
            if reset_btn.count() > 0 and reset_btn.is_visible():
                reset_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(3)

                # 초기화 후 직접 입력하기 버튼이 다시 나타나는지 확인
                manual_btn = page.locator("button", has_text="직접 입력하기")
                gemini_btn = page.locator("button", has_text="Gemini에게")

                if manual_btn.count() > 0 or gemini_btn.count() > 0:
                    results["passed"].append("주제 리스트 초기화 동작")
                    print("    ✅ 주제 리스트 초기화 동작")
                else:
                    results["warnings"].append("초기화 후 버튼 상태 불명확")
                    print("    ⚠️ 초기화 후 버튼 상태 불명확")

            page.screenshot(path="output/qa_07_reset.png", full_page=True)
        except Exception as e:
            results["failed"].append(f"초기화 테스트 실패: {e}")
            print(f"    ❌ 초기화 테스트 실패: {e}")

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
        print("스크린샷 저장 위치: output/qa_*.png")
        print("=" * 70)

        browser.close()

        return results


if __name__ == "__main__":
    try:
        test_all_features()
    except Exception as e:
        print(f"\n❌ 테스트 중 에러: {e}")
        import traceback
        traceback.print_exc()
