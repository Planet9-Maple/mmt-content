# 마미톡잉글리시 파이프라인 - 남은 작업

> 마지막 업데이트: 2026-03-25
> 세션 리프레시 시 이 파일을 읽고 작업 이어가기

---

## ✅ 완료된 작업

- [x] db_loader.py - 엑셀 DB 파싱
- [x] config/*.yaml - 5개 스텝 설정 파일
- [x] pipeline.py - 5스텝 파이프라인 (Gemini → Claude → GPT)
- [x] app.py - Streamlit 웹 UI
- [x] GitHub 저장소 생성 (Planet9-Maple/mmt-content)
- [x] Streamlit Cloud 배포
- [x] Gemini REST API 직접 호출로 변경 (SDK 인증 문제 해결)

---

## 🔄 진행 중

- [ ] Streamlit Cloud 테스트 중 - 사용자가 콘텐츠 생성 테스트 진행

---

## 📋 남은 작업

### 1. Google Sheets 연동 (우선순위: 높음)

**목표:** 콘텐츠 생성 완료 시 기존 시트에 자동으로 행 추가

**구현 내용:**
- [ ] Google Sheets API 연동 설정
  - Google Cloud Console에서 서비스 계정 생성
  - Sheets API 활성화
  - 서비스 계정 키(JSON) 발급
- [ ] gspread 라이브러리 추가 (requirements.txt)
- [ ] sheets_writer.py 모듈 생성
  - 시트 연결 함수
  - 새 행 추가 함수 (기존 구조와 동일: No., date, day, situation, level1, level2, level3, mommyvoca)
- [ ] app.py에 "시트에 저장" 버튼 추가
- [ ] Streamlit secrets에 Google 서비스 계정 키 추가

**필요한 정보 (사용자에게 확인):**
- 기존 Google Sheets URL 또는 ID
- Google Cloud 프로젝트 접근 권한

### 2. API 키 재발급 (우선순위: 높음)

**노출된 키 목록 (sellean/.env.local에서):**
- [ ] OpenAI API Key
- [ ] Google Gemini API Key
- [ ] Google OAuth Client Secret
- [ ] Microsoft OAuth Client Secret
- [ ] Supabase Service Role Key
- [ ] Resend API Key
- [ ] GitHub Token
- [ ] Trigger.dev Secret Key
- [ ] Upstash Redis Token

### 3. 추가 개선사항 (우선순위: 낮음)

- [ ] 에러 핸들링 강화 (API 타임아웃, 재시도 로직)
- [ ] 로딩 시간 최적화
- [ ] 히스토리 기능 (이전 생성 콘텐츠 조회)

---

## 🔑 환경 변수 현황

| 키 | 상태 | 용도 |
|----|------|------|
| GOOGLE_API_KEY | ✅ 설정됨 | Gemini (Step 0, 1) |
| ANTHROPIC_API_KEY | ✅ 설정됨 | Claude (Step 2, 3) |
| OPENAI_API_KEY | ✅ 설정됨 | GPT (Step 4) |
| GOOGLE_SHEETS_CREDENTIALS | ❌ 필요 | Google Sheets 연동 |

---

## 📁 프로젝트 구조

```
mmt-content/
├── app.py              ← Streamlit UI
├── pipeline.py         ← 5스텝 파이프라인
├── db_loader.py        ← 엑셀 DB 파싱
├── sheets_writer.py    ← (TODO) Google Sheets 연동
├── config/             ← 스텝별 설정
├── data/               ← 엑셀 DB
├── output/             ← 생성 결과
├── .env                ← 로컬 API 키 (git 제외)
├── .streamlit/         ← Streamlit 설정
├── TASK.md             ← 이 파일
└── CLAUDE.md           ← 프로젝트 스펙
```

---

## 🚀 다음 세션에서 할 일

1. `TASK.md` 읽기
2. 사용자에게 Streamlit 테스트 결과 확인
3. Google Sheets 연동 구현 시작
   - 사용자에게 시트 URL/권한 요청
   - 서비스 계정 설정 안내
4. 키 재발급 진행
