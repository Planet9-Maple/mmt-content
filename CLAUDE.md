# CLAUDE.md — 마미톡잉글리시 콘텐츠 자동화 파이프라인

## 프로젝트 한줄 요약

한국 엄마-아이 일상 영어 대화 콘텐츠를 레벨별(L1/L2/L3)로 자동 생성하는 멀티스텝 AI 파이프라인 + Streamlit 웹 UI. 3개 프로바이더(Google, Anthropic, OpenAI)의 최적 모델을 스텝별로 배치.

## 비즈니스 맥락

마미톡잉글리시는 한국·일본 시장에서 4,500명 유료 구독자를 가진 영어교육 서비스. 매일 레벨별 3개 콘텐츠(엄마 영어 3문장 + 한국어 대응 + 아이 반응)를 제작해 메시징 앱으로 발송한다. 현재 담당자가 수동으로 GPT에 입력해 제작하고 있으며, 이 파이프라인으로 어드민 입력 전 단계까지를 자동화한다. 5,000명 이상 유저에게 배포되므로 토큰 비용은 무시하고 순수 품질 최적화 우선.

## 핵심 스펙 문서

- `docs/mommytalk_pipeline_prompts_v3_final.md` — **전체 파이프라인 설계서 (반드시 먼저 읽을 것)**
  - Step 0~4 시스템 프롬프트 전문
  - **DB 기반 레벨 규칙** (정보 밀도 중심, 단어 수는 참고만)
  - 출력 텍스트 형식 (이모지 넘버링, {아이이름} 플레이스홀더)
  - 재생성 로직, 모델 교체 전략
- `docs/mommytalk_level_rules_db_based.md` — **DB 100건 분석 기반 레벨 규칙 (최신 기준)**
- `docs/prompt_crosscheck_report.md` — DB vs 규칙 교차 점검 리포트
- `data/마미톡 컨텐츠 v.2.xlsx` — 실제 콘텐츠 DB (131건, No.290~420)

## 프로젝트 구조

```
mommytalk-pipeline/
├── CLAUDE.md                  ← 이 파일
├── app.py                     ← Streamlit 메인 UI
├── pipeline.py                ← 5스텝 파이프라인 엔진
├── db_loader.py               ← 엑셀 DB 파싱·검색·few-shot 추출
├── config/
│   ├── step0_suggest.yaml     ← 주제 제안 (model, temperature, system_prompt)
│   ├── step1_ranking.yaml     ← 주제 랭킹
│   ├── step2_structure.yaml   ← 구조 설계
│   ├── step3_generate.yaml    ← 문장 생성
│   └── step4_review.yaml      ← 검수
├── data/
│   └── 마미톡_컨텐츠_v_2.xlsx  ← 콘텐츠 DB
├── docs/
│   ├── mommytalk_pipeline_prompts_v2_final.md
│   └── prompt_crosscheck_report.md
├── output/                    ← 생성된 콘텐츠 CSV/JSON 저장
├── requirements.txt
└── .env                       ← API 키 3개 (ANTHROPIC, OPENAI, GOOGLE)
```

## DB 구조 (data/마미톡_컨텐츠_v_2.xlsx)

시트1이 메인 데이터. 131행, 9컬럼.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| No. | float | 콘텐츠 고유번호 (290~420) |
| date | datetime | 발송일 (2025-12-04 ~ 2026-04-12) |
| day | str | 요일 (월/화/수/목/금/토/일) |
| situation | str | 주제명, 이모지 포함 (예: "💗 다정한 아침 인사") |
| level1 | str | 레벨1 전체 텍스트 (이모지넘버링+영어+한국어+아이반응) |
| level2 | str | 레벨2 전체 텍스트 |
| level3 | str | 레벨3 전체 텍스트 |
| mommyvoca | str | Canva 카드 URL |
| Unnamed: 8 | - | 빈 컬럼, 무시 |

**중요 패턴:**
- 일요일(day=="일")은 복습일 — level1/2/3이 비어있음. 생성 대상 아님.
- 아이 반응은 `⭐ {아이이름}:` 뒤에 위치. 레벨1은 "생략", 레벨2-3은 반응 2세트.
- 콘텐츠 형식은 `1️⃣ ... \n\n 2️⃣ ... \n\n 3️⃣ ...` 이모지 넘버링.

## 파이프라인 아키텍처

```
Step 0 (주제 제안) → 담당자 선택 → Step 1 (랭킹) → Step 2 (구조) → Step 3 (생성 ×3안) → Step 4 (검수)
  [Gemini]                        [Gemini]        [Claude]       [Claude]           [GPT]
```

각 스텝은 독립된 API 호출. 이전 스텝의 JSON 출력이 다음 스텝의 user message로 전달된다.

### 멀티 프로바이더 모델 배치 (품질 최적화)

| Step | 역할 | 모델 | 프로바이더 | temp | 선정 이유 |
|------|------|------|-----------|------|----------|
| 0 | 주제 제안 | `gemini-3.1-pro` | Google | 0.5 | 분석력 #1 (Intelligence Index 공동 1위) + 2M 컨텍스트로 DB 전체를 한 번에 분석 가능 |
| 1 | 주제 랭킹 | `gemini-3.1-pro` | Google | 0.2 | Step 0과 동일 모델로 컨텍스트 재사용. 순수 데이터 분석 태스크에 최적 |
| 2 | 구조 설계 | `claude-opus-4-6` | Anthropic | 0.4 | 복잡한 제약 조건("영어 생성 금지") 준수력 최상. 교육적 깊이 설계에 적합 |
| 3 | 문장 생성 | `claude-opus-4-6` | Anthropic | 0.7 | 영어 자연 산문 품질 업계 #1. 원어민 엄마 톤의 따뜻한 대화체에 최적화. 128K 출력 |
| 4 | 검수 | `gpt-5.2` | OpenAI | 0.2 | **크로스 프로바이더 편향 차단**: Claude가 만든 콘텐츠를 다른 모델이 검수해야 진짜 "외부 검수자" 효과 |

### 크로스 프로바이더 편향 차단 전략

Step 3(생성)과 Step 4(검수)를 반드시 다른 프로바이더로 배치한다. 이유:
- 같은 모델 계열은 유사한 언어 패턴을 "자연스럽다"고 평가하는 경향이 있음
- Claude가 선호하는 문장 구조를 Claude 검수자가 무의식적으로 높게 평가하는 편향 존재
- 다른 프로바이더의 검수로 이 편향을 깨뜨림

**교체 시 규칙**: Step 3 모델을 바꾸면 Step 4도 반드시 다른 프로바이더로 교체.
- Step 3 = Claude → Step 4 = GPT 또는 Gemini
- Step 3 = GPT → Step 4 = Claude 또는 Gemini
- Step 3 = Gemini → Step 4 = Claude 또는 GPT

### 재생성 로직
- Step 4에서 reject → Step 3 재실행 (temp +0.1씩 증가)
- 3회 reject → Step 2부터 재실행
- 5회 reject → 담당자에게 알림

## 레벨별 핵심 규칙 (빠른 참조)

> **핵심 원칙**: 단어 수가 아니라 **정보 밀도**로 레벨을 구분한다.
> 단어 수는 결과이지 규칙이 아님. DB 100건 분석 기반.

### 엄마 문장 — 정보 밀도 기준
| | L1 (2-3세) | L2 (3-5세) | L3 (4-6세) |
|---|---|---|---|
| **정보 밀도** | 핵심 정보 1개 | L1 + 감정/확인/구체성 1-2개 | 이유/상황묘사/조건 풍부 |
| 핵심 | "한 번에 하나" | "어떻게/왜/좋지?" 추가 | "왜 + 상황 + 그래서" |
| 접속사 | and, but 허용 (DB 60건+) | 자유 | 종속절 자유 |
| 참고 단어 수 | 4-6w 중심 (2-11w) | 7-10w 중심 (3-18w) | 10-15w 중심 |
| 비허용 | 이유 설명 포함 시 L2로 | 깊은 상황묘사 시 L3로 | 어휘만 어렵게 하기 |

### 아이 반응
| | L1 | L2 | L3 |
|---|---|---|---|
| 유무 | 없음 ("생략") | 2세트 | 2세트 |
| 핵심 패턴 | - | 2-3w chunk (73%) | 3-6w 완전문 (88%) |
| 1단어 규칙 | - | **최대 1개만 1단어** (둘 다 1단어 금지) | - |
| 조동사 허용 | - | 기본 패턴만 (~7%): "I can do it!" | 자유: can, will, want to |
| 비허용 | - | 5w+ 의문문, 확장된 want to | - |

## 구현 시 주의사항

### API 호출 — 3개 프로바이더

```python
# 프로바이더별 클라이언트 초기화
import anthropic
import openai
import google.generativeai as genai

# Anthropic (Step 2, 3)
anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# OpenAI (Step 4)
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Google Gemini (Step 0, 1)
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
```

**모델 스트링 (2026년 3월 기준)**:
- Gemini: `gemini-3.1-pro` (최신 GA 버전 확인 필요)
- Claude: `claude-opus-4-6` (extended thinking 비활성화)
- GPT: `gpt-5.2` (json_object 모드 지원)

**중요: 모델 스트링은 릴리즈에 따라 변경될 수 있음. 각 프로바이더의 최신 문서를 확인하고, config YAML에서 관리.**

### 프로바이더별 API 호출 패턴

```python
def call_gemini(system_prompt: str, user_message: str, config: dict) -> dict:
    """Step 0, 1용 — Google Gemini API"""
    model = genai.GenerativeModel(
        model_name=config['model'],
        system_instruction=system_prompt
    )
    response = model.generate_content(
        user_message,
        generation_config=genai.GenerationConfig(
            temperature=config['temperature'],
            max_output_tokens=config['max_tokens'],
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

def call_claude(system_prompt: str, user_message: str, config: dict) -> dict:
    """Step 2, 3용 — Anthropic Claude API"""
    response = anthropic_client.messages.create(
        model=config['model'],
        max_tokens=config['max_tokens'],
        temperature=config['temperature'],
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    return json.loads(response.content[0].text)

def call_gpt(system_prompt: str, user_message: str, config: dict) -> dict:
    """Step 4용 — OpenAI GPT API"""
    response = openai_client.chat.completions.create(
        model=config['model'],
        temperature=config['temperature'],
        max_tokens=config['max_tokens'],
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )
    return json.loads(response.choices[0].message.content)
```

### DB 파싱 (db_loader.py)
- openpyxl/pandas로 엑셀 읽기.
- 일요일 행 필터링 제외.
- `extract_child_responses(level_text)`: ⭐ 이후 텍스트에서 영어/한국어 반응 추출.
- `get_recent_topics(months=3)`: 최근 N개월 주제 리스트.
- `get_fewshot_examples(category, level, n=5)`: few-shot 예시 추출.

### 카테고리 분류 (db_loader.py에 포함)
DB에 category 컬럼이 없으므로 situation에서 자동 추론:
- **식사/간식**: 수저, 먹, 밥, 과일, 채소, 간식, 반찬, 그릇, 식당
- **위생/몸 관리**: 씻, 목욕, 양치, 머리, 손톱, 로션, 샤워, 치약
- **놀이**: 블록, 그림, 퍼즐, 공, 숨바꼭질, 만들기, 색칠, 놀이, 풍선, 경주
- **외출/이동**: 나가, 외투, 신발, 차, 엘리베이터, 공원, 킥보드, 준비
- **정리/규칙**: 정리, 빨래, 소리, 뛰, 기다려, 잡아당기
- **취침**: 잘 시간, 잠, 자기 전, 잘자, 꿈
- **감정/성장**: 실수, 스스로, 격려, 친절, 괜찮, 고마워, 기분, 사랑
- **자연/관찰**: 날씨, 동물, 새싹, 꽃, 구름, 달, 별, 개미, 비행기, 세탁기

### Streamlit UI (app.py)
- 사용자: 논 IT 백그라운드 콘텐츠 담당자.
- 최소한의 인터페이스: 주제 입력 → 생성 버튼 → 진행 표시 → 결과 미리보기 → CSV 다운로드.
- Step 0 결과를 라디오 버튼/체크박스로 선택. 수정 가능한 텍스트 인풋.
- Step 3 결과를 A/B/C 탭으로 미리보기. Step 4 점수 표시.
- 사이드바: config YAML 편집 (선택적 고급 기능).
- 각 스텝 진행 시 어떤 모델이 작업 중인지 표시 (예: "🟣 Claude Opus가 문장을 생성하고 있어요...")

### 출력
- JSON: 내부 처리용 (output/YYYYMMDD_topic.json)
- admin_text: 어드민에 바로 붙여넣을 수 있는 포맷 (output/YYYYMMDD_topic_admin.txt)
- CSV: DB에 추가할 수 있는 행 형태 (output/YYYYMMDD_topic.csv)

## 개발 순서 (권장)

1. **db_loader.py** — 엑셀 파싱 + 카테고리 분류 + few-shot 추출 함수. 이게 모든 스텝의 기반.
2. **config/ YAML 파일 5개** — docs/mommytalk_pipeline_prompts_v2_final.md에서 시스템 프롬프트 추출. 모델·temperature 설정 포함.
3. **pipeline.py** — 5스텝 순차 실행 엔진. 프로바이더별 API 호출 함수 3개 + 스텝 디스패처.
4. **터미널에서 테스트** — `python pipeline.py --topic "손 씻기" --day "화"` 로 CLI 테스트.
5. **app.py** — Streamlit UI 감싸기. pipeline.py를 import해서 호출.

## 환경 설정

```bash
pip install anthropic openai google-generativeai pandas openpyxl streamlit pyyaml python-dotenv
```

```env
# .env
ANTHROPIC_API_KEY=sk-ant-...       # Step 2, 3 (Claude Opus 4.6)
OPENAI_API_KEY=sk-...              # Step 4 (GPT-5.2)
GOOGLE_API_KEY=AI...               # Step 0, 1 (Gemini 3.1 Pro)
```

## 코딩 컨벤션

- Python 3.10+
- 타입 힌트 사용
- 각 스텝 함수는 dict를 받아 dict를 반환 (JSON-serializable)
- 에러 시 retry 로직은 pipeline.py에서 관리
- 로깅: 각 스텝 시작/종료/사용 모델/토큰 사용량 출력
- 한국어 주석 허용 (담당자가 코드를 볼 수 있으므로)
- 프로바이더별 에러 핸들링 분리 (rate limit, timeout 등 프로바이더마다 다름)
