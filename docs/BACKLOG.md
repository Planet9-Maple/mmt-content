# 마미톡잉글리시 콘텐츠 파이프라인 - 백로그

> 마지막 업데이트: 2026-03-30
> 코드 리뷰 기반 작성

---

## 🔴 Critical (즉시 수정 필요)

### CRIT-001: save_monthly_plan 전체 덮어쓰기 문제
- **파일**: `app.py:786-793`
- **상태**: 🔴 미해결
- **설명**: 월간 기획 페이지의 "☁️ Sheets에 저장" 버튼이 `save_monthly_plan()` 호출
- **문제**: 이 함수가 `save_monthly_plan_to_sheets()`를 호출하고, 해당 월의 모든 행을 삭제 후 재삽입
- **영향**: Gemini가 생성한 기존 주제들이 전부 날아갈 수 있음
- **해결방안**: 개별 `upsert_topic_status()` 호출로 변경
```python
# 현재 (문제)
if save_monthly_plan(month, topics):

# 수정안
for topic in topics:
    sheets_writer.upsert_topic_status(topic['date'], topic['topic'], topic['status'])
```

### CRIT-002: 순환 동기화 위험
- **파일**: `sheets_writer.py:338-386`, `app.py:267`
- **상태**: 🔴 미해결
- **설명**: `sync_monthly_plan_with_sheet()`가 앱 시작 시 호출되며 내부에서 `save_monthly_plan_to_sheets()` 호출
- **문제**: 예상치 못한 전체 덮어쓰기 발생 가능
- **영향**: 앱 재시작 시 데이터 손실 위험
- **해결방안**: 동기화 로직을 upsert 기반으로 재설계

---

## 🟠 Major (조기 수정 권장)

### MAJ-001: Google Sheets API 최적화 부족
- **파일**: `sheets_writer.py`
- **상태**: 🟠 미해결
- **설명**: 개별 셀 업데이트마다 API 호출
- **문제**: 네트워크 지연, API 쿼터 소모
- **해결방안**: `worksheet.batch_update()` 사용
```python
# 현재
worksheet.update(f'D{i}', status)
worksheet.update(f'H{i}', datetime.now().isoformat())

# 권장
worksheet.batch_update([
    {'range': f'D{i}', 'values': [[status]]},
    {'range': f'H{i}', 'values': [[datetime.now().isoformat()]]}
])
```

### MAJ-002: 중복 코드 - 요일 계산
- **파일**: `app.py`, `sheets_writer.py`, `pipeline.py`
- **상태**: 🟠 미해결
- **설명**: 동일한 요일 계산 코드가 6회 이상 반복
```python
weekdays = ["월", "화", "수", "목", "금", "토", "일"]
day_str = weekdays[dt.weekday()]
```
- **해결방안**: `utils.py` 생성 후 공통 함수 추출
```python
# utils.py
def get_weekday_kr(dt: datetime) -> str:
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return weekdays[dt.weekday()]
```

### MAJ-003: 타입 힌트 부재
- **파일**: 전체
- **상태**: 🟠 미해결
- **설명**: 거의 모든 함수에 타입 힌트가 없음
- **문제**: 유지보수성 저하, IDE 자동완성 불가
- **해결방안**: 점진적으로 타입 힌트 추가, mypy 도입 검토

### MAJ-004: 에러 처리 불일치
- **파일**: 전체
- **상태**: 🟠 미해결
- **설명**: 일부 함수는 `{'success': False, 'error': ...}` 반환, 일부는 예외 발생
- **문제**: 호출자 측에서 일관된 에러 처리 불가
- **해결방안**: Result 패턴 또는 예외 패턴 중 하나로 통일

### MAJ-005: DB 캐싱 없음
- **파일**: `db_loader.py`
- **상태**: 🟠 미해결
- **설명**: `load_db()` 호출 시마다 엑셀 파일 로드
- **문제**: 불필요한 I/O, 성능 저하
- **해결방안**:
```python
@functools.lru_cache(maxsize=1)
def load_db(path: Optional[Path] = None) -> pd.DataFrame:
    ...
```
또는 Streamlit 환경에서 `@st.cache_data` 사용

---

## 🟡 Minor (개선 권장)

### MIN-001: 하드코딩된 설정값
- **파일**: 여러 파일
- **상태**: 🟡 미해결
- **설명**:
  - DB 경로: `data/마미톡 컨텐츠 v.2.xlsx`
  - 스프레드시트 이름: `마미톡잉글리시 콘텐츠 DB`
  - 시트 이름: `monthly_plans`
- **해결방안**: `.env` 또는 `config/settings.yaml`로 분리

### MIN-002: 미사용 변수
- **파일**: `app.py:1472`
- **상태**: 🟡 미해결
- **설명**: `target_month` 변수가 선언 후 사용되지 않음
- **해결방안**: 삭제 또는 사용처 확인

### MIN-003: import 스타일 불일치
- **파일**: `app.py`
- **상태**: 🟡 미해결
- **설명**: 파일 상단 import와 함수 내부 import 혼재
- **해결방안**: 파일 상단에서 일괄 import

### MIN-004: 카테고리 키워드 하드코딩
- **파일**: `db_loader.py:21-30`
- **상태**: 🟡 미해결
- **설명**: `CATEGORY_KEYWORDS` 딕셔너리가 코드에 직접 정의
- **해결방안**: `config/categories.yaml`로 분리

### MIN-005: 긴 시스템 프롬프트
- **파일**: `config/step3_generate.yaml`, `config/step4_review.yaml`
- **상태**: 🟡 미해결
- **설명**: 프롬프트가 수백 줄에 달함
- **해결방안**: 모듈화 또는 include 방식 검토

---

## 🔵 Enhancement (향후 개선)

### ENH-001: 단위 테스트 추가
- **상태**: 🔵 미구현
- **설명**: 핵심 로직에 대한 테스트 없음
- **범위**:
  - `db_loader.py`: 파싱 로직 테스트
  - `pipeline.py`: JSON 추출 테스트
  - `sheets_writer.py`: CRUD 테스트 (mock 사용)
- **도구**: pytest, pytest-mock

### ENH-002: API 레이트 리미팅
- **상태**: 🔵 미구현
- **설명**: AI API 호출에 레이트 리미팅 없음
- **문제**: 대량 호출 시 429 에러 가능
- **해결방안**: tenacity 라이브러리 사용
```python
from tenacity import retry, wait_exponential, stop_after_attempt

@retry(wait=wait_exponential(min=1, max=60), stop=stop_after_attempt(5))
def call_api(...):
    ...
```

### ENH-003: 로깅 개선
- **상태**: 🔵 미구현
- **설명**: 현재 `logging` 모듈 사용하지만 파일 출력 없음
- **해결방안**: 파일 로깅 추가, 로그 레벨 설정 가능하게

### ENH-004: 환경별 설정 분리
- **상태**: 🔵 미구현
- **설명**: dev/staging/prod 환경 구분 없음
- **해결방안**: `config/dev.yaml`, `config/prod.yaml` 분리

### ENH-005: 백업/복구 기능
- **상태**: 🔵 미구현
- **설명**: Sheets 데이터 백업 기능 없음
- **해결방안**: 주기적 JSON 백업, 복구 UI 추가

---

## ✅ Resolved (해결됨)

### RES-001: 콘텐츠 저장 시 monthly_plans 덮어쓰기
- **해결일**: 2026-03-30
- **파일**: `app.py:1509-1515`
- **내용**: `save_monthly_plan()` 대신 `upsert_topic_status()` 사용으로 변경
- **커밋**: `a995cf6`

### RES-002: 콘텐츠 삭제 시 monthly_plans 미반영
- **해결일**: 2026-03-30
- **파일**: `app.py:1680-1682`
- **내용**: 삭제 후 `upsert_topic_status(date, topic, 'pending')` 호출 추가
- **커밋**: `a995cf6`

### RES-003: 아이 반응 레벨 호환성 규칙 추가
- **해결일**: 2026-03-30
- **파일**: `config/step3_generate.yaml`, `config/step4_review.yaml`
- **내용**: 1️⃣, 2️⃣ 문장 기반 아이 반응 생성, L2/L3 규칙 명시
- **커밋**: `36350d2`

### RES-004: 맥락(context) 기록 실패
- **해결일**: 2026-03-30
- **파일**: `sheets_writer.py:update_topic_context()`
- **문제**: 날짜가 monthly_plans 시트에 없으면 에러 반환, 새 행 삽입 안 됨
- **내용**: upsert 로직 추가 - 날짜 없으면 새 행 자동 삽입
- **커밋**: `970f1df`

### RES-005: 생성 버튼 클릭 시 주제 Sheets 동기화 안 됨
- **해결일**: 2026-03-30
- **파일**: `app.py` (생성 버튼 핸들러)
- **문제**: UI에서 주제 편집 → session_state만 업데이트, Sheets에는 반영 안 됨
- **내용**: "생성" 버튼 클릭 시 `upsert_topic_status()` 호출 추가
- **커밋**: `970f1df`

### RES-006: worksheet.update() API 포맷 오류
- **해결일**: 2026-03-30
- **파일**: `sheets_writer.py:upsert_topic_status()`, `update_topic_context()`
- **문제**: `worksheet.update(f'C{i}', topic)` - 2D array 필요한데 string 전달
- **내용**: `[[value]]` 형식으로 수정
- **커밋**: `970f1df`

---

## 우선순위 매트릭스

| 긴급도 \ 중요도 | 높음 | 중간 | 낮음 |
|---------------|------|------|------|
| **높음** | CRIT-001, CRIT-002 | MAJ-001 | - |
| **중간** | MAJ-002, MAJ-004 | MAJ-003, MAJ-005 | MIN-001~005 |
| **낮음** | - | ENH-001, ENH-002 | ENH-003~005 |

---

## 작업 순서 권장

1. **Phase 1 (즉시)**: CRIT-001, CRIT-002 해결
2. **Phase 2 (1주 내)**: MAJ-001, MAJ-002, MAJ-004
3. **Phase 3 (2주 내)**: MAJ-003, MAJ-005, MIN-*
4. **Phase 4 (이후)**: ENH-*

---

## 변경 이력

| 날짜 | 작성자 | 내용 |
|------|--------|------|
| 2026-03-30 | Claude | 초기 백로그 작성 (코드 리뷰 기반) |
| 2026-03-30 | Claude | RES-004~006 추가: 맥락 기록, 주제 동기화, API 포맷 수정 |
