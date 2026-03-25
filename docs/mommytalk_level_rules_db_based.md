# 마미톡잉글리시 레벨별 기준 — DB 기반 최종판

> 100건의 실제 DB 분석에서 도출. 단어 수가 아닌 "정보 밀도 + 구조적 복잡성"이 핵심 기준.
> 이 문서가 Step 3(생성)과 Step 4(검수)의 레벨 판단 기준.

---

## 핵심 원칙: 단어 수는 규칙이 아니라 결과다

DB 분석 결과, L1(2-11w)과 L2(3-18w)의 단어 수 범위가 크게 겹친다.
5단어짜리 L1과 5단어짜리 L2가 둘 다 존재하지만, 읽어보면 레벨 차이가 명확하다.

```
L1 [5w]: Please don't pull Mommy's clothes.  ← 행동 지시 하나
L2 [5w]: It makes Mommy uncomfortable, okay? ← 감정 + 확인
```

레벨을 구분하는 진짜 기준은 **한 문장이 전달하는 정보의 층위**다.

---

## 레벨 1 (2-3세) — "한 번에 하나"

### 엄마 문장 핵심 규칙: 한 문장이 전달하는 정보가 1개
- 하나의 행동, 하나의 관찰, 하나의 요청만 담는다.
- 짧은 절 2개를 한 줄에 조합하는 건 허용 (실제 DB의 21%가 이 패턴).
  단, 두 절이 같은 정보의 연장선이어야 한다.
- 접속사(and, but, when, if, so) 허용 — 실제 DB에 60건+ 존재.
  "Sit and eat, please." "Nice and warm!" 같은 건 2-3세 아이에게 완전히 자연스러운 표현.

### ✅ DB에서 추출한 L1 전형적 패턴
```
행동 지시:     "Let's go eat breakfast." (4w)
관찰 + 감탄:  "Your hands are so cold." (5w)
짧은 2절 조합: "All done! Your hair is so fluffy." (7w)
행동 연결:     "Pick it up and put it in." (7w)
부드러운 전환: "I know you want to play, but it's bedtime." (9w)
```

### ❌ L1이 아닌 것
```
이유 설명이 포함: "Let's dry your hair now, or you might catch a cold." → L2
상황 묘사 + 행동: "We're heading out in ten minutes, so let's start getting ready." → L3
```

### 아이 반응: 없음
- `⭐ {아이이름}: 생략` — DB 100% 일치.

### 참고 단어 수 범위 (규칙이 아닌 참고)
- 중심대: 4-6w (전체의 58%)
- 실제 범위: 2-11w
- 평균 5.7w, 중위수 6w

---

## 레벨 2 (3-5세) — "감정·확인·구체성이 추가된 것"

### 엄마 문장 핵심 규칙: L1의 핵심 행동에 감정, 확인, 구체적 방법이 1-2개 추가
- L1이 "뭘 하자"라면, L2는 "뭘 하자 + 어떻게/왜/좋지?"
- 2절 조합이 표준 (DB의 46%가 2절 이상).
- 감탄사·전치사구·간단한 연결어 자유롭게 사용.

### ✅ L1 → L2 확장 패턴 (DB 실제 사례)
```
L1: "Dinner's almost ready."
L2: "Dinner's almost ready now."                    ← 시간 부사 추가

L1: "Can you set the spoons?"
L2: "Can you put the spoons out for me?"             ← 구체적 방법 + 관계("for me")

L1: "We're leaving in ten minutes."
L2: "We're leaving in ten minutes, okay?"            ← 확인 추가

L1: "Let's dry your hair."
L2: "Let's dry your hair now, or you might catch a cold." ← 가벼운 이유 추가

L1: "Let's build a tall tower!"
L2: "Let's stack the blocks and make a really tall tower!" ← 구체적 방법 추가
```

### ❌ L2가 아닌 것
```
정보 1개만 전달: "Let's go eat breakfast." → L1 (감정/확인/구체성 추가 없음)
상황 묘사 + 이유 + 행동 3개: "You feel nice and fresh after your bath, right? Let's dry..." → L3
```

### 아이 반응 (항상 2세트)
- **반응 수**: 항상 2세트 (DB 100/100 = 100%)
- **1단어 제한 규칙**: 2개 반응 중 **최대 1개만 1단어 가능. 나머지는 반드시 2단어 이상.**
  - DB 실측: 67%는 1단어 없음 / 26%는 1개만 1단어 / 7%는 둘 다 1단어
  - 둘 다 1단어인 7%는 피하는 것이 바람직 → "최대 1개" 규칙으로 품질 확보

### L2 아이 반응 허용 패턴 (DB 실측 기반)

**2-3단어 chunk (73% — 핵심 패턴)**
```
"All done!"  "So cold!"  "My turn!"  "Like this?"
"This is mine!"  "One more time!"  "Help me, Mommy!"
"It fell over!"  "I did it!"  "For you, Daddy!"
```

**감탄형 1단어 (20% — 허용, 단 2세트 중 최대 1개)**
```
"Yummy!"  "Pretty!"  "Ouch!"  "Promise!"  "Done!"  "Hot!"
"Here?"  "Next?"  "Okay?"  ← 질문형 1단어도 포함
```
- 1단어가 허용되는 조건: 상황 맥락에서 아이의 즉각적 반응이 자연스러울 때
- AI에게 주는 규칙: "1단어 반응은 전체의 약 1/3 이하. 2개 반응 중 최대 1개."

**조동사/want to 패턴 (7% — 조건부 허용)**
```
"I can do it!"  "I want to try!"  "I'll try."  "I can!"
```
- 매우 기본적인 패턴만. 전체의 ~7% 이내로 자연스럽게 등장하는 수준.
- 매 콘텐츠마다 넣는 게 아니라, 상황에 맞을 때만.

**❌ L2 아이 반응에서 비허용**
```
5단어 이상 의문문: "Can I put toys in?" → L3
확장된 want to: "I want to share this with you." → L3
```

### 참고 단어 수 범위 (규칙이 아닌 참고)
- 엄마: 중심대 7-10w (전체의 43%), 평균 9.2w, 중위수 9w
- 아이: 평균 2.2w

---

## 레벨 3 (4-6세) — "상황 묘사·이유·조건이 풍부해진 것"

### 엄마 문장 핵심 규칙: 이유, 상황 묘사, 조건, 감정의 깊이가 추가
- L2가 "뭘 하자 + 어떻게"라면, L3는 "왜 하는지 + 상황이 어떤지 + 그래서 뭘 하자"
- 2절 이상 조합이 표준 (DB의 64%).
- 종속절, 시간부사, 원인/결과 연결 자유.
- **핵심: 어휘가 어려워지는 것이 아니라, 문장 구조·길이·표현의 층위가 풍부해지는 것.**

### ✅ L2 → L3 확장 패턴 (DB 실제 사례)
```
L2: "Dinner's almost ready now."
L3: "Dinner's almost ready, sweetie—just a few more minutes!"
    ← 애칭 + 구체적 시간 정보

L2: "Can you put the spoons out for me?"
L3: "Can you help me by setting the spoons on the table?"
    ← 방법의 구체화("by ~ing") + 장소 추가

L2: "We're leaving in ten minutes, okay?"
L3: "We're heading out in ten minutes, so let's start getting ready."
    ← 이유("so") + 행동 유도 추가

L2: "Your hands are freezing—it was so cold outside."
L3: "Wow, your hands are completely frozen. They must feel so cold—it was freezing outside."
    ← 감탄 + 공감("must feel") + 상황 묘사 확장

L2: "I know you're upset. I hear you."
L3: "I know you're really upset. That must have felt really hard. I'm listening."
    ← 공감의 깊이 + 감정 인정 + 경청 표현
```

### 아이 반응 (항상 2세트)
- **반응 수**: 항상 2세트 (DB 99/100 = 99%)
- 문법적으로 완전한 문장. 주어+동사 형태.
- 조동사(can, will), to부정사(want to), 의문문(Can we~?) 자유.

### L3 아이 반응 패턴 (DB 실측)
```
3-4단어 (58% — 핵심대):
  "My coat is right here!"  "This one is mine!"
  "I'll stay still."  "The water feels warm!"

5-6단어 (30%):
  "Did you sleep well, Mommy?"  "I want to read this one!"
  "Can I dry your hair now?"  "My hands are so cold!"

7-8단어 (3% — 간혹):
  "Can you put the toys in too?"  "Good night, Mommy! I love you!"
```

### 참고 단어 수 범위 (규칙이 아닌 참고)
- 엄마: 중심대 10-15w (전체의 55%), 평균 12.9w, 중위수 13w
- 아이: 평균 4.0w

---

## 레벨 간 구분 — 구조적 체크리스트

### Step 4 검수 시 사용할 레벨 판별 기준

**이 문장은 L1인가?**
- [ ] 전달하는 핵심 정보가 1개인가?
- [ ] 이유 설명(because, so that)이 없는가?
- [ ] 감정 확인("okay?", "right?")이 부가 요소가 아니라 없는가?

**이 문장은 L2인가?**
- [ ] L1의 핵심 행동이 유지되면서, 감정/확인/구체적 방법이 1-2개 추가되었는가?
- [ ] 상황 묘사나 깊은 이유 설명 없이, 가벼운 연결이 자연스러운가?

**이 문장은 L3인가?**
- [ ] 이유, 상황 묘사, 조건, 시간 설명이 포함되어 문장이 풍부한가?
- [ ] 어휘가 어려워진 것이 아니라 구조가 확장된 것인가?

### 레벨 간 차별성 검수 기준
- ✅ 좋은 패턴: 같은 핵심 표현이 유지되면서 층위가 추가됨
  ```
  L1: "Let's go eat breakfast."
  L2: "Come on, let's go eat breakfast."
  L3: "Let's head to the kitchen and get some breakfast."
  ```
- ❌ 나쁜 패턴: 단어만 바뀌고 정보 층위는 같음
  ```
  L1: "Let's eat." / L2: "Let's eat now." / L3: "Let's eat breakfast." → 구조 차이 없음
  ```
- ❌ 나쁜 패턴: L1인데 이유 설명이 들어감
  ```
  L1: "Let's wash hands because they're dirty." → 이유 설명은 L2-L3 영역
  ```

---

## 한국어 확장 패턴 (동일 원칙 적용)

한국어도 단어 수가 아니라 정보 층위로 확장:
```
L1: "아침 먹으러 가자 🥰"             ← 행동 하나
L2: "자, 아침 먹으러 가자 🥰"          ← 부드러운 시작어 추가
L3: "이제 부엌으로 가서 아침 먹자 🥰"   ← 장소 + 구체적 동선
```

---

## 검수 항목 (DB 기반 재정립)

| # | 항목 | 기준 |
|---|------|------|
| 1 | 원어민 자연스러움 | 최우선. 교과서식·번역투 금지. |
| 2 | 문법 완전성 | 교육 자료이므로 오류 불가. 아이 반응 포함. |
| 3 | **L1 정보 밀도** | 핵심 정보 1개만 전달하는가? 이유/설명이 없는가? |
| 4 | **L2 정보 밀도** | L1 + 감정/확인/구체성이 1-2개 추가되었는가? |
| 5 | **L3 정보 밀도** | 이유/상황묘사/조건이 포함되어 구조가 풍부한가? |
| 6 | **레벨 간 차별성** | 같은 핵심 표현이 유지되면서 층위가 추가되는 패턴인가? |
| 7 | L2 아이 1단어 | 2개 반응 중 최대 1개만 1단어. 전체의 ~1/3 이하. |
| 8 | L2 아이 조동사 | 기본 패턴만 조건부 허용. 전체의 ~7% 이내. |
| 9 | L3 아이 완전문 | 주어+동사 형태인가? 3-6단어가 핵심대. |
| 10 | 아이 반응 세트 | L2-L3 항상 2세트. |
| 11 | 한국어 대응 | 직역 금지. 정보 층위도 레벨에 맞게 확장. |
| 12 | 문장 흐름 | 1→2→3 자연스러운 흐름. 갑작스러운 전환 없음. |
| 13 | UX 관점 | 유료 콘텐츠 가치. 불필요한 난이도 금지. |

---

## 적용 경로

이 문서의 기준을 아래 파일에 반영:
1. `docs/mommytalk_pipeline_prompts_v2_final.md` > Step 3 시스템 프롬프트 > "레벨별 생성 규칙" 섹션 전체 교체
2. `docs/mommytalk_pipeline_prompts_v2_final.md` > Step 4 시스템 프롬프트 > "검수 항목" 섹션 전체 교체
3. `docs/mommytalk_pipeline_prompts_v2_final.md` > Step 2 시스템 프롬프트 > "레벨별 설계 원칙" 섹션 교체
4. `CLAUDE.md` > "레벨별 핵심 규칙" 빠른 참조 테이블 교체
