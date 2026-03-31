"""
마미톡잉글리시 콘텐츠 생성 파이프라인

5스텝 순차 실행 엔진 (3개 프로바이더 사용):
- Step 0, 1: Google Gemini (분석)
- Step 2, 3: Anthropic Claude (생성)
- Step 4: OpenAI GPT (검수 - 크로스 프로바이더 편향 차단)
"""

import argparse
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv

import db_loader

# 환경 변수 로드
load_dotenv()


def get_api_key(key_name: str) -> str:
    """API 키를 환경 변수 또는 Streamlit secrets에서 가져옵니다."""
    # 1. 환경 변수에서 시도
    value = os.getenv(key_name)
    if value:
        return value

    # 2. Streamlit secrets에서 시도
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key_name in st.secrets:
            return st.secrets[key_name]
    except Exception:
        pass

    return ""


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# 설정 디렉토리
CONFIG_DIR = Path(__file__).parent / "config"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 프로바이더 이모지
PROVIDER_EMOJI = {
    "gemini": "🔵",
    "claude": "🟣",
    "gpt": "🟢"
}


def load_config(step: int) -> dict:
    """스텝별 config YAML 로드."""
    step_names = {
        0: "step0_suggest",
        1: "step1_ranking",
        2: "step2_structure",
        3: "step3_generate",
        4: "step4_review"
    }
    config_path = CONFIG_DIR / f"{step_names[step]}.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# API 호출 함수 (3개 프로바이더)
# ============================================================

def call_gemini(
    system_prompt: str,
    user_message: str,
    model: str = "gemini-2.0-flash",
    temperature: float = 0.5,
    max_tokens: int = 4000
) -> str:
    """Google Gemini API 호출 (Step 0, 1) - REST API 직접 호출."""
    import requests

    api_key = get_api_key("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY가 설정되지 않았습니다.")

    # Fallback 모델 리스트 (503 에러 시 순차 시도)
    models_to_try = [model, "gemini-2.0-flash", "gemini-1.5-flash"]
    # 중복 제거
    models_to_try = list(dict.fromkeys(models_to_try))

    last_error = None

    for try_model in models_to_try:
        logger.info(f"{PROVIDER_EMOJI['gemini']} Gemini API 호출: {try_model}, temp={temperature}")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{try_model}:generateContent?key={api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n---\n\n{user_message}"}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            }
        }

        # gemini-2.5 모델만 thinkingConfig 지원
        if "2.5" in try_model:
            payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            break  # 성공하면 루프 종료
        except requests.exceptions.HTTPError as e:
            last_error = e
            if response.status_code in [503, 500, 429]:
                logger.warning(f"{try_model} 실패 ({response.status_code}), 다음 모델 시도...")
                continue
            raise  # 다른 에러는 즉시 발생

    else:
        # 모든 모델 실패
        raise last_error or ValueError("모든 Gemini 모델 호출 실패")

    result = response.json()

    # Gemini 2.5는 thinking과 text를 분리해서 반환할 수 있음
    parts = result["candidates"][0]["content"]["parts"]
    text = ""
    for part in parts:
        if "text" in part:
            text = part["text"]
            break

    # 토큰 사용량 로깅
    if "usageMetadata" in result:
        usage = result["usageMetadata"]
        logger.info(f"토큰 사용: input={usage.get('promptTokenCount', 0)}, output={usage.get('candidatesTokenCount', 0)}")

    # JSON 추출 (마크다운 코드블록 또는 직접 JSON)
    text = text.strip()
    if text.startswith("```"):
        # ```json ... ``` 형태에서 JSON 추출
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()

    return text


def call_claude(
    system_prompt: str,
    user_message: str,
    model: str = "claude-sonnet-4-20250514",
    temperature: float = 0.5,
    max_tokens: int = 4000
) -> str:
    """Anthropic Claude API 호출 (Step 2, 3)."""
    import anthropic

    client = anthropic.Anthropic(api_key=get_api_key("ANTHROPIC_API_KEY"))

    logger.info(f"{PROVIDER_EMOJI['claude']} Claude API 호출: {model}, temp={temperature}")

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    # 토큰 사용량 로깅
    usage = response.usage
    logger.info(f"토큰 사용: input={usage.input_tokens}, output={usage.output_tokens}")

    return response.content[0].text


def call_gpt(
    system_prompt: str,
    user_message: str,
    model: str = "gpt-4o",
    temperature: float = 0.5,
    max_tokens: int = 4000
) -> str:
    """OpenAI GPT API 호출 (Step 4)."""
    from openai import OpenAI

    client = OpenAI(api_key=get_api_key("OPENAI_API_KEY"))

    logger.info(f"{PROVIDER_EMOJI['gpt']} GPT API 호출: {model}, temp={temperature}")

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    )

    # 토큰 사용량 로깅
    usage = response.usage
    logger.info(f"토큰 사용: input={usage.prompt_tokens}, output={usage.completion_tokens}")

    return response.choices[0].message.content


def call_api(step: int, system_prompt: str, user_message: str, config: dict) -> str:
    """스텝에 따라 적절한 프로바이더 API 호출."""
    provider = config.get("provider", "claude")
    model = config.get("model", "")
    temperature = config.get("temperature", 0.5)
    max_tokens = config.get("max_tokens", 4000)

    if provider == "gemini":
        return call_gemini(system_prompt, user_message, model, temperature, max_tokens)
    elif provider == "claude":
        return call_claude(system_prompt, user_message, model, temperature, max_tokens)
    elif provider == "gpt":
        return call_gpt(system_prompt, user_message, model, temperature, max_tokens)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def extract_json(text: str) -> dict:
    """응답 텍스트에서 JSON 추출."""
    # ```json ... ``` 블록 추출 시도
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # 전체 텍스트가 JSON인 경우
        json_str = text.strip()

    # JSON 파싱 시도
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 파싱 실패 시: 문자열 내 줄바꿈을 이스케이프 처리
    try:
        # JSON 문자열 내부의 실제 줄바꿈을 \n으로 변환
        fixed = re.sub(
            r'(?<=["\'])\s*\n\s*(?=["\'])|(?<=:)\s*"([^"]*)"',
            lambda m: m.group(0).replace('\n', '\\n') if m.group(0) else m.group(0),
            json_str
        )
        # 문자열 값 내부의 줄바꿈 처리
        def fix_string_newlines(match):
            content = match.group(1)
            fixed_content = content.replace('\n', '\\n').replace('\r', '\\r')
            return f'"{fixed_content}"'

        fixed = re.sub(r'"((?:[^"\\]|\\.)*)(?:\n)((?:[^"\\]|\\.)*)"',
                       lambda m: f'"{m.group(1)}\\n{m.group(2)}"', json_str)

        # 여러 번 반복 적용
        for _ in range(5):
            prev = fixed
            fixed = re.sub(r'"((?:[^"\\]|\\.)*)(?:\n)((?:[^"\\]|\\.)*)"',
                          lambda m: f'"{m.group(1)}\\n{m.group(2)}"', fixed)
            if prev == fixed:
                break

        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # 최후의 수단: { } 사이의 내용만 추출
    try:
        brace_match = re.search(r'\{[\s\S]*\}', json_str)
        if brace_match:
            return json.loads(brace_match.group(0))
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {e}")
        logger.error(f"원본 텍스트: {text[:500]}...")
        raise ValueError(f"JSON 파싱 실패: {e}")


# ============================================================
# Step 0: 주제 제안 (Gemini)
# ============================================================

def step0_suggest(
    target_date: datetime,
    weather_note: str = "정보 없음",
    df=None,
    already_used: list = None
) -> dict:
    """Step 0: 주제 후보 5-7개 제안.

    Args:
        target_date: 발송 대상 날짜
        weather_note: 날씨 정보
        df: DB DataFrame
        already_used: 이번 월간 기획에서 이미 사용된 주제 리스트 (중복 방지용)
    """
    logger.info("=" * 50)
    logger.info("Step 0: 주제 제안 시작 (Gemini)")

    config = load_config(0)

    # 요일 계산
    weekdays_kr = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    day_of_week = weekdays_kr[target_date.weekday()]

    # 계절 계산
    month = target_date.month
    season_map = {
        12: "겨울, 크리스마스 시즌",
        1: "겨울, 새해, 설날 준비",
        2: "겨울 끝, 새 학기 준비",
        3: "봄 시작, 개학/입학",
        4: "봄, 벚꽃, 소풍",
        5: "봄, 어린이날, 가정의 달",
        6: "초여름, 더위 시작",
        7: "여름, 장마, 물놀이",
        8: "한여름, 휴가",
        9: "가을 시작, 추석",
        10: "가을, 단풍, 소풍",
        11: "늦가을, 겨울 준비"
    }
    season_context = season_map.get(month, "")

    # 최근 2주 콘텐츠
    recent_2w = db_loader.get_recent_topics(months=0.5, df=df)
    recent_topics_str = ""
    if len(recent_2w) > 0:
        for _, row in recent_2w.iterrows():
            recent_topics_str += f"- {row['date'].strftime('%m/%d')} ({row['situation']}) [{row['category']}]\n"
    else:
        recent_topics_str = "(최근 2주 콘텐츠 없음)"

    # 최근 1개월 카테고리 분포
    cat_dist = db_loader.get_category_distribution(months=1, df=df)
    cat_dist_str = "\n".join([f"- {cat}: {cnt}건" for cat, cnt in cat_dist.items()])

    # 이번 달 이미 사용된 주제
    already_used_str = ""
    if already_used:
        already_used_str = "\n## ⚠️ 이번 달 이미 할당된 주제 (피해주세요!)\n"
        already_used_str += "\n".join([f"- {t}" for t in already_used])

    # 같은 월 과거 주제 (DB 학습용)
    same_month_topics = db_loader.get_same_month_topics(month, df=df)
    same_month_str = ""
    if len(same_month_topics) > 0:
        # 최대 10개까지만 (다양한 예시 제공)
        for _, row in same_month_topics.head(10).iterrows():
            year = row['date'].year if hasattr(row['date'], 'year') else ""
            same_month_str += f"- {year}년: {row['situation']} [{row['category']}]\n"
    else:
        same_month_str = "(해당 월 과거 데이터 없음)"

    # User message 구성
    user_message = f"""## 발송 정보
- 날짜: {target_date.strftime('%Y-%m-%d')}
- 요일: {day_of_week}
- 계절: {season_context}
- 날씨: {weather_note}

## 최근 2주 발송 콘텐츠
{recent_topics_str}

## 최근 1개월 카테고리 분포
{cat_dist_str}

## 📚 같은 월({month}월) 과거 DB 주제 (변형 아이디어 참고용)
{same_month_str}
{already_used_str}
"""

    # API 호출
    response = call_api(0, config["system_prompt"], user_message, config)
    result = extract_json(response)
    logger.info(f"Step 0 완료: {len(result.get('suggestions', []))}개 주제 제안")

    return result


# ============================================================
# Step 1: 주제 랭킹 (Gemini)
# ============================================================

def step1_ranking(
    selected_topics: list[str],
    target_date: datetime,
    df=None
) -> dict:
    """Step 1: 선택된 주제들의 랭킹 및 중복 체크."""
    logger.info("=" * 50)
    logger.info("Step 1: 주제 랭킹 시작 (Gemini)")

    config = load_config(1)

    # 요일, 계절
    weekdays_kr = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    day_of_week = weekdays_kr[target_date.weekday()]
    month = target_date.month
    season_map = {
        12: "겨울", 1: "겨울", 2: "겨울/봄",
        3: "봄", 4: "봄", 5: "봄/여름",
        6: "여름", 7: "여름", 8: "여름",
        9: "가을", 10: "가을", 11: "가을/겨울"
    }
    season = season_map.get(month, "")

    # 최근 3개월 콘텐츠
    recent_3m = db_loader.get_recent_topics(months=3, df=df)
    recent_str = ""
    for _, row in recent_3m.iterrows():
        recent_str += f"No.{int(row['No.'])} | {row['date'].strftime('%Y-%m-%d')} | {row['situation']}\n"

    # User message
    topics_str = "\n".join([f"- {t}" for t in selected_topics])
    user_message = f"""## 후보 주제
{topics_str}

## 발송 요일·계절
{day_of_week}, {season}

## 최근 3개월 콘텐츠 목록
{recent_str if recent_str else "(콘텐츠 없음)"}
"""

    response = call_api(1, config["system_prompt"], user_message, config)
    result = extract_json(response)
    logger.info(f"Step 1 완료: {len(result.get('rankings', []))}개 주제 랭킹")

    return result


# ============================================================
# Step 2: 구조 설계 (Claude)
# ============================================================

def step2_structure(topic: str) -> dict:
    """Step 2: 레벨별 한글 구조 설계."""
    logger.info("=" * 50)
    logger.info(f"Step 2: 구조 설계 시작 (Claude) - {topic}")

    config = load_config(2)

    user_message = f"""## 확정 주제
{topic}

위 주제에 대해 레벨 1, 2, 3 각각의 구조를 설계해주세요.
"""

    response = call_api(2, config["system_prompt"], user_message, config)
    result = extract_json(response)
    logger.info("Step 2 완료: 구조 설계 완료")

    return result


def step2_regenerate_targeted(
    topic: str,
    existing_result: dict,
    target_level: str,
    feedback: str,
    target_sentences: list
) -> dict:
    """Step 2 타겟 재생성: 특정 레벨의 특정 문장만 수정.

    Args:
        topic: 주제
        existing_result: 기존 Step 2 구조 설계 결과
        target_level: 수정할 레벨 ("level_1", "level_2", "level_3")
        feedback: 사용자 피드백
        target_sentences: 수정할 문장 번호 리스트 [1], [2], [1,2], [1,2,3] 등

    Returns:
        수정된 결과 (다른 레벨은 기존 유지)
    """
    logger.info("=" * 50)
    logger.info(f"Step 2 타겟 재생성: {target_level}, 문장 {target_sentences}")

    config = load_config(2)

    # 기존 레벨 데이터
    existing_levels = existing_result.get("levels", {})
    existing_level_data = existing_levels.get(target_level, {})

    # 기존 엄마 말 맥락 (새 형식: mom_sentences)
    existing_mom_sentences = existing_level_data.get("mom_sentences", [])
    if not existing_mom_sentences:
        # 이전 형식 호환
        existing_mom_sentences = existing_level_data.get("mom_flow", [])

    existing_mom_text = ""
    for i, line in enumerate(existing_mom_sentences, 1):
        if isinstance(line, dict):
            text = line.get(f"line_{i}", str(line))
        else:
            text = str(line)
        existing_mom_text += f"  {i}️⃣ {text}\n"

    # 레벨 번호
    level_num = target_level[-1]

    # 수정 대상 vs 유지 대상 결정
    all_sentences = [1, 2, 3]
    if not target_sentences or set(target_sentences) == set(all_sentences):
        preserve_sentences = []
        target_instruction = f"레벨 {level_num}의 모든 문장 맥락을 피드백에 따라 재설계하세요."
    else:
        preserve_sentences = [i for i in all_sentences if i not in target_sentences]
        target_instruction = f"""## 타겟 수정 지시
- 수정 대상 문장: {target_sentences}번
- 유지할 문장: {preserve_sentences}번 (절대 변경 금지!)
- 수정된 문장은 앞뒤 문장과 자연스럽게 연결되어야 합니다."""

    # 타겟 재생성 전용 시스템 프롬프트
    targeted_system_prompt = f"""{config["system_prompt"]}

---

## 타겟 재생성 모드

당신은 기존 구조 설계의 **특정 부분만** 수정합니다.

### 핵심 규칙
1. **지정된 문장만 수정**: 피드백에서 지정한 문장 번호의 맥락만 수정합니다.
2. **문맥 유지**: 앞뒤 문장과의 자연스러운 흐름을 유지해야 합니다.
3. **다른 부분 절대 변경 금지**: 지정되지 않은 문장, 다른 레벨은 한 글자도 바꾸지 마세요.
4. **아이 반응**: 피드백에서 언급하지 않으면 기존 그대로 유지합니다.
"""

    user_message = f"""## 주제
{topic}

## 수정 대상 레벨: {target_level} (Level {level_num})

## 기존 구조 (이 레벨)
장면: {existing_level_data.get('scene', '-')}
흐름: {existing_level_data.get('flow_logic', '-')}

엄마 말 맥락:
{existing_mom_text}

아이 반응1: {existing_level_data.get('child_response_1', '-')}
아이 반응2: {existing_level_data.get('child_response_2', '-')}

## 피드백
{feedback}

{target_instruction}

## 출력 형식
수정된 {target_level}만 JSON으로 출력하세요. 다른 레벨은 출력하지 마세요.
**수정 대상 문장만 변경하고, 나머지 문장은 기존 그대로 유지하세요.**

{{
  "levels": {{
    "{target_level}": {{
      "scene": "...",
      "mom_sentences": [
        "1번 문장 (한국어 맥락)",
        "2번 문장 (한국어 맥락)",
        "3번 문장 (한국어 맥락)"
      ],
      "child_response_1": "...",
      "child_response_2": "..."
    }}
  }}
}}
"""

    response = call_api(2, targeted_system_prompt, user_message, config)
    regenerated = extract_json(response)

    # 결과 병합: 다른 레벨은 기존 유지
    final_result = {
        "topic": existing_result.get("topic", topic),
        "common_situation": existing_result.get("common_situation", ""),
        "levels": {}
    }

    for level_key in ["level_1", "level_2", "level_3"]:
        if level_key == target_level:
            new_level_data = regenerated.get("levels", {}).get(target_level, {})
            if new_level_data:
                # 특정 문장만 수정하는 경우, 문장 단위로 병합
                if preserve_sentences:
                    merged_level = existing_level_data.copy()

                    # scene 업데이트 (피드백에서 요청한 경우만)
                    if new_level_data.get("scene"):
                        merged_level["scene"] = new_level_data["scene"]

                    # mom_sentences 문장별 병합
                    new_mom_sentences = new_level_data.get("mom_sentences", [])
                    merged_sentences = list(existing_mom_sentences)  # 복사

                    for i in target_sentences:
                        if i <= len(new_mom_sentences) and i <= 3:
                            idx = i - 1
                            if idx < len(merged_sentences):
                                merged_sentences[idx] = new_mom_sentences[idx]
                            elif idx < len(new_mom_sentences):
                                merged_sentences.append(new_mom_sentences[idx])

                    merged_level["mom_sentences"] = merged_sentences

                    # 아이 반응 (피드백에서 요청한 경우만 업데이트)
                    if new_level_data.get("child_response_1"):
                        merged_level["child_response_1"] = new_level_data["child_response_1"]
                    if new_level_data.get("child_response_2"):
                        merged_level["child_response_2"] = new_level_data["child_response_2"]

                    final_result["levels"][level_key] = merged_level
                else:
                    # 전체 수정인 경우 그대로 교체
                    final_result["levels"][level_key] = new_level_data
            else:
                final_result["levels"][level_key] = existing_levels.get(level_key, {})
        else:
            final_result["levels"][level_key] = existing_levels.get(level_key, {})

    logger.info(f"Step 2 타겟 재생성 완료: {target_level}")

    return final_result


# ============================================================
# Step 3: 문장 생성 (Claude)
# ============================================================

def step3_generate(
    structure: dict,
    category: Optional[str] = None,
    temperature_override: Optional[float] = None,
    df=None
) -> dict:
    """Step 3: A/B/C 3안 문장 생성."""
    logger.info("=" * 50)
    logger.info("Step 3: 문장 생성 시작 (Claude)")

    config = load_config(3)
    if temperature_override:
        config = config.copy()
        config["temperature"] = temperature_override

    # few-shot 예시 추출
    fewshot_text = ""
    for level in [1, 2, 3]:
        examples = db_loader.get_fewshot_examples(category=category, level=level, n=5, df=df)
        fewshot_text += f"\n### 레벨 {level} 예시\n"
        for ex in examples:
            fewshot_text += f"No.{ex['no']} ({ex['situation']}):\n"
            fewshot_text += f"{ex['level_text'][:300]}...\n\n"

    # System prompt에 few-shot 추가
    system_prompt = config["system_prompt"] + f"\n\n{fewshot_text}"

    user_message = f"""## Step 2 설계도
```json
{json.dumps(structure, ensure_ascii=False, indent=2)}
```

위 설계도를 바탕으로 레벨 1, 2, 3 각각에 대해 A/B/C 3안을 생성해주세요.
"""

    response = call_api(3, system_prompt, user_message, config)
    result = extract_json(response)
    logger.info(f"Step 3 완료 (temp={config['temperature']})")

    return result


def step3_regenerate_targeted(
    structure: dict,
    existing_result: dict,
    target_level: str,
    feedback: str,
    target_sentences: list,
    preserve_variant: str = "A",
    category: Optional[str] = None,
    df=None
) -> dict:
    """Step 3 타겟 재생성: 특정 레벨의 특정 문장만 수정.

    Args:
        structure: Step 2 구조 설계 결과
        existing_result: 기존 Step 3 생성 결과
        target_level: 수정할 레벨 ("level_1", "level_2", "level_3")
        feedback: 사용자 피드백
        target_sentences: 수정할 문장 번호 리스트 [1], [2], [1,2], [1,2,3] 등
        preserve_variant: 기준이 되는 변형 ("A", "B", "C")
        category: 주제 카테고리
        df: DB 데이터프레임

    Returns:
        수정된 결과 (다른 레벨은 기존 유지)
    """
    logger.info("=" * 50)
    logger.info(f"Step 3 타겟 재생성: {target_level}, 문장 {target_sentences}")

    config = load_config(3)

    # 기존 콘텐츠 가져오기
    existing_levels = existing_result.get("levels", {})
    existing_level_data = existing_levels.get(target_level, {})
    existing_variants = existing_level_data.get("variants", {})
    existing_variant = existing_variants.get(preserve_variant, {})
    existing_admin_text = existing_variant.get("admin_text", "")

    # 레벨 번호 추출
    level_num = target_level[-1]  # "level_1" -> "1"

    # 수정 대상 vs 유지 대상 결정
    all_sentences = [1, 2, 3]
    if not target_sentences or set(target_sentences) == set(all_sentences):
        # 전체 재생성
        preserve_sentences = []
        target_instruction = f"레벨 {level_num}의 모든 문장을 피드백에 따라 재생성하세요."
    else:
        # 부분 재생성
        preserve_sentences = [i for i in all_sentences if i not in target_sentences]
        target_instruction = f"""## 타겟 수정 지시
- 수정 대상 문장: {target_sentences}번
- 유지할 문장: {preserve_sentences}번 (절대 변경 금지!)
- 수정된 문장은 앞뒤 문장과 자연스럽게 연결되어야 합니다.
- 한국어 번역도 동일한 원칙을 적용하세요."""

    # 타겟 재생성 전용 시스템 프롬프트
    targeted_system_prompt = f"""{config["system_prompt"]}

---

## 타겟 재생성 모드

당신은 기존 콘텐츠의 **특정 부분만** 수정합니다.

### 핵심 규칙
1. **지정된 문장만 수정**: 피드백에서 지정한 문장 번호만 수정합니다.
2. **문맥 유지**: 앞뒤 문장과의 자연스러운 흐름을 유지해야 합니다.
3. **다른 부분 절대 변경 금지**: 지정되지 않은 문장은 한 글자도 바꾸지 마세요.
4. **아이 반응**: 피드백에서 언급하지 않으면 기존 그대로 유지합니다.
"""

    # 사용자 메시지 구성
    user_message = f"""## 수정 대상 레벨: {target_level} (Level {level_num})

## 기존 콘텐츠 ({preserve_variant}안)
```
{existing_admin_text}
```

## 피드백
{feedback}

{target_instruction}

## Step 2 설계도 (해당 레벨만 참고)
```json
{json.dumps(structure.get("levels", {}).get(target_level, {}), ensure_ascii=False, indent=2)}
```

## 출력 형식
수정된 {target_level}의 A/B/C 3안을 JSON으로 출력하세요.
- 지정된 문장만 수정하고, 나머지는 기존 내용 그대로 유지
- 다른 레벨은 출력하지 마세요

{{
  "levels": {{
    "{target_level}": {{
      "variants": {{
        "A": {{
          "admin_text": "...",
          "mom_en": ["...", "...", "..."],
          "mom_kr": ["...", "...", "..."],
          ...
        }},
        "B": {{ ... }},
        "C": {{ ... }}
      }}
    }}
  }}
}}
"""

    response = call_api(3, targeted_system_prompt, user_message, config)
    regenerated = extract_json(response)

    # 결과 병합: 다른 레벨은 기존 유지
    final_result = {
        "topic": existing_result.get("topic", ""),
        "levels": {}
    }

    for level_key in ["level_1", "level_2", "level_3"]:
        if level_key == target_level:
            # 재생성된 레벨 사용
            new_level_data = regenerated.get("levels", {}).get(target_level, {})
            if new_level_data and preserve_sentences:
                # 특정 문장만 수정하는 경우, 문장 단위로 병합
                merged_level = {"variants": {}}
                new_variants = new_level_data.get("variants", {})

                for variant_key in ["A", "B", "C"]:
                    existing_var = existing_variants.get(variant_key, {})
                    new_var = new_variants.get(variant_key, {})

                    if not new_var:
                        merged_level["variants"][variant_key] = existing_var
                        continue

                    merged_var = existing_var.copy()

                    # mom_en 문장별 병합
                    existing_mom_en = existing_var.get("mom_en", [])
                    new_mom_en = new_var.get("mom_en", [])
                    merged_mom_en = list(existing_mom_en)
                    for i in target_sentences:
                        idx = i - 1
                        if idx < len(new_mom_en):
                            if idx < len(merged_mom_en):
                                merged_mom_en[idx] = new_mom_en[idx]
                            else:
                                merged_mom_en.append(new_mom_en[idx])
                    merged_var["mom_en"] = merged_mom_en

                    # mom_kr 문장별 병합
                    existing_mom_kr = existing_var.get("mom_kr", [])
                    new_mom_kr = new_var.get("mom_kr", [])
                    merged_mom_kr = list(existing_mom_kr)
                    for i in target_sentences:
                        idx = i - 1
                        if idx < len(new_mom_kr):
                            if idx < len(merged_mom_kr):
                                merged_mom_kr[idx] = new_mom_kr[idx]
                            else:
                                merged_mom_kr.append(new_mom_kr[idx])
                    merged_var["mom_kr"] = merged_mom_kr

                    # admin_text 재생성 (병합된 문장으로)
                    admin_lines = []
                    for i, (en, kr) in enumerate(zip(merged_mom_en, merged_mom_kr), 1):
                        admin_lines.append(f"{i}️⃣ {en}")
                    admin_lines.append("")
                    for kr in merged_mom_kr:
                        admin_lines.append(kr)

                    # 아이 반응 처리
                    child_en_1 = new_var.get("child_en_1") or existing_var.get("child_en_1")
                    child_kr_1 = new_var.get("child_kr_1") or existing_var.get("child_kr_1")
                    child_en_2 = new_var.get("child_en_2") or existing_var.get("child_en_2")
                    child_kr_2 = new_var.get("child_kr_2") or existing_var.get("child_kr_2")

                    if child_en_1:
                        admin_lines.append("")
                        admin_lines.append(f"⭐ {{아이이름}}:")
                        admin_lines.append(child_en_1)
                        admin_lines.append(child_kr_1 or "")
                        if child_en_2:
                            admin_lines.append("")
                            admin_lines.append(child_en_2)
                            admin_lines.append(child_kr_2 or "")
                    else:
                        admin_lines.append("")
                        admin_lines.append("⭐ {아이이름}: 생략")

                    merged_var["admin_text"] = "\n".join(admin_lines)
                    merged_var["child_en_1"] = child_en_1
                    merged_var["child_kr_1"] = child_kr_1
                    merged_var["child_en_2"] = child_en_2
                    merged_var["child_kr_2"] = child_kr_2

                    merged_level["variants"][variant_key] = merged_var

                final_result["levels"][level_key] = merged_level
            elif new_level_data:
                # 전체 수정인 경우 그대로 교체
                final_result["levels"][level_key] = new_level_data
            else:
                # 재생성 실패 시 기존 유지
                final_result["levels"][level_key] = existing_levels.get(level_key, {})
        else:
            # 기존 레벨 유지
            final_result["levels"][level_key] = existing_levels.get(level_key, {})

    logger.info(f"Step 3 타겟 재생성 완료: {target_level}")

    return final_result


# ============================================================
# Step 4: 검수 (GPT - 크로스 프로바이더)
# ============================================================

def step4_review(
    generated: dict,
    category: Optional[str] = None,
    df=None
) -> dict:
    """Step 4: 품질 검수 및 점수화 (GPT로 크로스 검수)."""
    logger.info("=" * 50)
    logger.info("Step 4: 검수 시작 (GPT - 크로스 프로바이더 편향 차단)")

    config = load_config(4)

    # 기존 콘텐츠 (같은 카테고리)
    existing_text = ""
    if category:
        content_df = db_loader.get_content_rows(df)
        content_df["category"] = content_df["situation"].apply(db_loader.categorize_topic)
        same_cat = content_df[content_df["category"] == category].tail(5)
        for _, row in same_cat.iterrows():
            existing_text += f"No.{int(row['No.'])} ({row['situation']})\n"

    user_message = f"""## Step 3 생성 결과
```json
{json.dumps(generated, ensure_ascii=False, indent=2)}
```

## 기존 콘텐츠 (같은 카테고리 최근 3개월)
{existing_text if existing_text else "(없음)"}
"""

    response = call_api(4, config["system_prompt"], user_message, config)
    result = extract_json(response)

    # verdict 집계
    verdicts = []
    review = result.get("review", {})
    for level_key in ["level_1", "level_2", "level_3"]:
        level_data = review.get(level_key, {})
        variants = level_data.get("variants", {})
        for var_key, var_data in variants.items():
            verdicts.append(var_data.get("verdict", "unknown"))

    passed = sum(1 for v in verdicts if v == "pass")
    logger.info(f"Step 4 완료: {passed}/{len(verdicts)} pass")

    return result


def detect_chopped_sentences(text: str) -> list[dict]:
    """한 줄에서 Chopped Sentences 패턴을 탐지합니다.

    Chopped Sentences: 한 줄 내에 1-3단어짜리 파편 문장 2개가 이어붙여진 것
    예: "Look! No more rain!" (1w + 3w), "Open the window. So fresh!" (3w + 2w)

    Returns:
        [{"original": "Look! No more rain!", "pattern": "1w + 3w"}]
    """
    issues = []

    # 한 줄에서 문장 분리 (마침표, 느낌표, 물음표 기준)
    # 대문자로 시작하는 문장 패턴 찾기
    sentence_pattern = re.compile(r'([A-Z][^.!?]*[.!?])')
    sentences = sentence_pattern.findall(text)

    if len(sentences) >= 2:
        # 연속된 두 문장의 단어 수 체크
        for i in range(len(sentences) - 1):
            s1 = sentences[i].strip()
            s2 = sentences[i + 1].strip()

            w1 = len(s1.split())
            w2 = len(s2.split())

            # 둘 다 4단어 미만이면 Chopped Sentences
            if w1 < 4 and w2 < 4:
                issues.append({
                    "original": f"{s1} {s2}",
                    "pattern": f"{w1}w + {w2}w",
                    "s1": s1,
                    "s2": s2
                })

    return issues


def detect_l1_issues(generated_result: dict) -> dict:
    """L1 콘텐츠에서 자동으로 문제를 탐지합니다.

    탐지 항목:
    1. Chopped Sentences
    2. 질문(?) 0개
    3. 총 단어 수 부족
    4. 느낌표만 있는 경우

    Returns:
        {"has_issues": bool, "feedback": str, "sentences": list}
    """
    issues = []
    sentences_to_fix = set()

    level_1 = generated_result.get("levels", {}).get("level_1", {})
    variants = level_1.get("variants", {})

    # A 변형 기준으로 체크
    var_a = variants.get("A", {})
    mom_en = var_a.get("mom_en", [])
    admin_text = var_a.get("admin_text", "")

    if not mom_en:
        return {"has_issues": False, "feedback": "", "sentences": []}

    # 1. Chopped Sentences 탐지
    for i, line in enumerate(mom_en, 1):
        chopped = detect_chopped_sentences(line)
        if chopped:
            for c in chopped:
                issues.append(
                    f"[{i}번 문장] Chopped Sentences 탐지: \"{c['original']}\" ({c['pattern']}). "
                    f"수정: 대시(—)로 연결하거나 완전문(5-8단어)으로 재작성"
                )
                sentences_to_fix.add(i)

    # 2. 질문(?) 0개 체크
    has_question = any("?" in line for line in mom_en)
    if not has_question:
        issues.append(
            "[전체] 질문(?) 0개 - 상호작용 부재. "
            "수정: 최소 1개 질문 포함 (예: 'Want to go outside?', 'Did you see that?')"
        )
        sentences_to_fix.add(2)  # 보통 2번째 문장을 질문으로

    # 3. 총 단어 수 체크
    total_words = sum(len(line.split()) for line in mom_en)
    if total_words < 14:
        issues.append(
            f"[전체] 총 {total_words}단어 - DB 최소(14단어)보다 부족. "
            f"수정: 17-23단어 목표로 문장 확장"
        )
        sentences_to_fix.update([1, 2, 3])

    # 4. 느낌표만 있는지 체크
    punctuation = {"!": 0, "?": 0, ".": 0}
    for line in mom_en:
        if line.endswith("!"):
            punctuation["!"] += 1
        elif line.endswith("?"):
            punctuation["?"] += 1
        else:
            punctuation["."] += 1

    if punctuation["!"] == 3 and punctuation["?"] == 0:
        issues.append(
            "[전체] 3문장 모두 느낌표(!) + 질문 0개 - 단조로움. "
            "수정: 최소 1개 질문(?) 또는 마침표(.) 포함"
        )
        sentences_to_fix.add(2)

    if issues:
        return {
            "has_issues": True,
            "feedback": "\n".join(issues),
            "sentences": list(sentences_to_fix) if sentences_to_fix else [1, 2, 3]
        }
    else:
        return {"has_issues": False, "feedback": "", "sentences": []}


def extract_must_fix_feedback(review_result: dict, generated_result: dict = None) -> dict:
    """검수 결과에서 must_fix 항목을 추출하여 레벨별 피드백으로 변환.

    추가로 L1에 대해 자동 탐지 로직을 실행하여 GPT가 놓친 문제도 잡아냅니다.

    Returns:
        {
            "level_1": {"has_issues": False, "feedback": "", "sentences": []},
            "level_2": {"has_issues": True, "feedback": "...", "sentences": [1, 2]},
            "level_3": {"has_issues": True, "feedback": "...", "sentences": [1]}
        }
    """
    feedback_by_level = {}
    review = review_result.get("review", {})

    for level_key in ["level_1", "level_2", "level_3"]:
        level_data = review.get(level_key, {})
        variants = level_data.get("variants", {})

        # 가장 많이 선택될 A 변형의 must_fix 확인
        best_pick = level_data.get("best_pick", "A")
        var_data = variants.get(best_pick, {})
        must_fix_list = var_data.get("must_fix", [])

        feedback_parts = []
        sentences = set()

        # GPT가 제공한 must_fix 처리
        if must_fix_list:
            for fix in must_fix_list:
                sentence_num = fix.get("sentence_num", 0)
                problem = fix.get("problem", "")
                original = fix.get("original", "")
                fix_instruction = fix.get("fix_instruction", "")
                suggested_fix = fix.get("suggested_fix", "")

                sentences.add(sentence_num)

                feedback_parts.append(
                    f"[{sentence_num}번 문장] {problem}. "
                    f"현재: \"{original}\" → 수정: {fix_instruction}"
                    + (f" (예: \"{suggested_fix}\")" if suggested_fix else "")
                )

        # L1에 대해 추가 자동 탐지 (GPT가 놓친 문제 잡기)
        if level_key == "level_1" and generated_result:
            auto_detected = detect_l1_issues(generated_result)
            if auto_detected["has_issues"]:
                # 기존 피드백에 추가
                feedback_parts.append("\n[자동 탐지된 문제]")
                feedback_parts.append(auto_detected["feedback"])
                sentences.update(auto_detected["sentences"])

        # verdict가 revise인 경우도 재생성 트리거
        verdict = var_data.get("verdict", "pass")
        if verdict == "revise" and not feedback_parts:
            # must_fix는 없지만 revise 판정인 경우
            issues_list = var_data.get("issues", [])
            if issues_list:
                feedback_parts.append("[revise 판정 이슈]")
                for issue in issues_list[:3]:  # 상위 3개만
                    feedback_parts.append(f"- {issue}")
                sentences.update([1, 2, 3])  # 전체 재생성

        if feedback_parts:
            feedback_by_level[level_key] = {
                "has_issues": True,
                "feedback": "\n".join(feedback_parts),
                "sentences": list(sentences) if sentences else [1, 2, 3]
            }
        else:
            feedback_by_level[level_key] = {
                "has_issues": False,
                "feedback": "",
                "sentences": []
            }

    return feedback_by_level


def step4_review_with_auto_fix(
    structure: dict,
    generated: dict,
    category: Optional[str] = None,
    df=None,
    max_fix_attempts: int = 3
) -> tuple[dict, dict, int]:
    """검수 + 자동 수정 루프.

    must_fix 항목이 있거나 verdict가 revise인 경우 자동으로 재생성하고 다시 검수합니다.
    L1에 대해 Chopped Sentences 등을 자동 탐지하여 GPT가 놓친 문제도 잡습니다.
    최대 max_fix_attempts 번까지 시도합니다.

    Args:
        structure: Step 2 구조 설계 결과
        generated: Step 3 생성 결과
        category: 카테고리
        df: DB DataFrame
        max_fix_attempts: 최대 수정 시도 횟수 (기본 3)

    Returns:
        (최종 생성 결과, 최종 검수 결과, 수정 횟수)
    """
    current_generated = generated
    fix_count = 0

    for attempt in range(max_fix_attempts + 1):
        # 검수 실행
        review_result = step4_review(current_generated, category=category, df=df)

        # must_fix 체크
        overall = review_result.get("overall_recommendation", {})
        auto_regen = overall.get("auto_regenerate_needed", False)

        # must_fix 항목 추출 (generated_result 전달하여 자동 탐지 활성화)
        feedback_by_level = extract_must_fix_feedback(review_result, current_generated)
        has_any_must_fix = any(f["has_issues"] for f in feedback_by_level.values())

        # verdict 체크 - revise도 재생성 대상
        review_data = review_result.get("review", {})
        has_revise_verdict = False
        for level_key in ["level_1", "level_2", "level_3"]:
            level_data = review_data.get(level_key, {})
            variants = level_data.get("variants", {})
            for var_key, var_data in variants.items():
                if var_data.get("verdict") == "revise":
                    has_revise_verdict = True
                    # revise인데 feedback이 없으면 추가
                    if not feedback_by_level[level_key]["has_issues"]:
                        issues = var_data.get("issues", [])
                        if issues:
                            # issues가 dict 리스트일 경우 문자열로 변환
                            issue_strs = []
                            for issue in issues[:3]:
                                if isinstance(issue, dict):
                                    issue_strs.append(str(issue.get("issue", issue.get("problem", str(issue)))))
                                else:
                                    issue_strs.append(str(issue))
                            feedback_by_level[level_key] = {
                                "has_issues": True,
                                "feedback": f"[revise 판정] " + ", ".join(issue_strs),
                                "sentences": [1, 2, 3]
                            }
                    break

        # 통과 조건: must_fix 없음 + auto_regen 아님 + revise verdict 없음
        if not has_any_must_fix and not auto_regen and not has_revise_verdict:
            logger.info(f"✅ 검수 통과 (수정 횟수: {fix_count})")
            return current_generated, review_result, fix_count

        if attempt >= max_fix_attempts:
            # 최대 시도 도달 - 그냥 반환
            logger.warning(f"⚠️ 최대 수정 시도({max_fix_attempts})에 도달. 현재 결과 반환")
            return current_generated, review_result, fix_count

        # 자동 수정 필요
        fix_count += 1
        logger.info(f"🔄 자동 수정 시작 (시도 {fix_count}/{max_fix_attempts})")

        # 각 레벨별로 문제가 있는 것만 재생성
        for level_key, level_feedback in feedback_by_level.items():
            if level_feedback["has_issues"]:
                logger.info(f"  - {level_key} 재생성: {level_feedback['feedback'][:80]}...")

                try:
                    current_generated = step3_regenerate_targeted(
                        structure=structure,
                        existing_result=current_generated,
                        target_level=level_key,
                        feedback=level_feedback["feedback"],
                        target_sentences=level_feedback["sentences"],
                        preserve_variant="A",
                        category=category,
                        df=df
                    )
                except Exception as e:
                    logger.error(f"  - {level_key} 재생성 실패: {e}")
                    continue

    return current_generated, review_result, fix_count


# ============================================================
# 전체 파이프라인 실행
# ============================================================

def run_pipeline(
    topic: Optional[str] = None,
    target_date: Optional[datetime] = None,
    day: Optional[str] = None,
    weather_note: str = "정보 없음",
    skip_suggest: bool = False
) -> dict:
    """전체 파이프라인 실행.

    Args:
        topic: 확정 주제 (없으면 Step 0에서 제안)
        target_date: 발송일 (기본: 내일)
        day: 요일 (선택)
        weather_note: 날씨 정보
        skip_suggest: Step 0 스킵 여부

    Returns:
        최종 결과 dict
    """
    logger.info("=" * 60)
    logger.info("마미톡잉글리시 파이프라인 시작")
    logger.info("🔵 Gemini → 🟣 Claude → 🟢 GPT")
    logger.info("=" * 60)

    # 날짜 설정
    if target_date is None:
        target_date = datetime.now() + timedelta(days=1)

    # DB 로드
    df = db_loader.load_db()
    content_df = db_loader.get_content_rows(df)

    results = {
        "target_date": target_date.strftime("%Y-%m-%d"),
        "topic": topic,
        "steps": {}
    }

    # Step 0: 주제 제안 (옵션)
    if not skip_suggest and topic is None:
        step0_result = step0_suggest(target_date, weather_note, df)
        results["steps"]["step0"] = step0_result

        # 첫 번째 제안 선택 (CLI에서는 자동, UI에서는 사용자 선택)
        suggestions = step0_result.get("suggestions", [])
        if suggestions:
            topic = suggestions[0].get("topic", "")
            logger.info(f"자동 선택된 주제: {topic}")

    if not topic:
        raise ValueError("주제가 필요합니다")

    results["topic"] = topic
    category = db_loader.categorize_topic(topic)

    # Step 1: 주제 랭킹 (Gemini)
    step1_result = step1_ranking([topic], target_date, df)
    results["steps"]["step1"] = step1_result

    # Step 2: 구조 설계 (Claude)
    step2_result = step2_structure(topic)
    results["steps"]["step2"] = step2_result

    # Step 3 & 4: 생성 + 검수 + 자동 수정 (재시도 로직 포함)
    MAX_RETRIES = 5
    STEP3_RETRY = 3

    for attempt in range(MAX_RETRIES):
        logger.info(f"생성 시도 {attempt + 1}/{MAX_RETRIES}")

        if attempt < STEP3_RETRY:
            # Step 3만 재실행 (temperature 증가)
            temp = 0.7 + (attempt * 0.1)
            step3_result = step3_generate(
                step2_result,
                category=category,
                temperature_override=min(temp, 1.0),
                df=df
            )
        else:
            # Step 2부터 재실행 (설계 자체 변경)
            logger.info("Step 2부터 재설계")
            step2_result = step2_structure(topic)
            results["steps"]["step2"] = step2_result
            step3_result = step3_generate(step2_result, category=category, df=df)

        # Step 4: 검수 + 자동 수정 루프 (GPT - 크로스 프로바이더)
        # must_fix 항목이나 revise verdict가 있으면 자동 재생성
        step3_result, step4_result, fix_count = step4_review_with_auto_fix(
            structure=step2_result,
            generated=step3_result,
            category=category,
            df=df,
            max_fix_attempts=3
        )

        results["steps"]["step3"] = step3_result
        results["steps"]["step4"] = step4_result

        if fix_count > 0:
            logger.info(f"자동 수정 {fix_count}회 수행됨")

        # verdict 체크
        overall = step4_result.get("overall_recommendation", {})
        confidence = overall.get("confidence", "low")

        if confidence in ["high", "medium"]:
            logger.info(f"검수 통과 (confidence: {confidence})")
            break
        else:
            logger.warning(f"검수 미통과 (confidence: {confidence}), 재시도...")
    else:
        logger.error("5회 시도 후에도 통과 실패. 수동 검토 필요.")
        results["manual_review_required"] = True

    # 출력 파일 생성
    _save_outputs(results, target_date, topic)

    logger.info("=" * 60)
    logger.info("파이프라인 완료")
    logger.info("=" * 60)

    return results


def _save_outputs(results: dict, target_date: datetime, topic: str):
    """결과를 파일로 저장."""
    date_str = target_date.strftime("%Y%m%d")
    # 파일명에 사용할 수 없는 문자 제거
    safe_topic = re.sub(r"[^\w가-힣]", "", topic)[:20]
    base_name = f"{date_str}_{safe_topic}"

    # JSON 저장
    json_path = OUTPUT_DIR / f"{base_name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON 저장: {json_path}")

    # admin_text 추출 및 저장
    step3 = results.get("steps", {}).get("step3", {})
    step4 = results.get("steps", {}).get("step4", {})
    overall = step4.get("overall_recommendation", {})
    best_combo = overall.get("best_combination", {})

    admin_text = f"# {topic}\n# 생성일: {date_str}\n\n"

    levels = step3.get("levels", {})
    for level_key in ["level_1", "level_2", "level_3"]:
        level_data = levels.get(level_key, {})
        variants = level_data.get("variants", {})

        # 추천 variant 선택
        best_var = best_combo.get(level_key, "A")
        var_data = variants.get(best_var, {})

        admin_text += f"## {level_key.upper()} (추천: {best_var}안)\n"
        admin_text += var_data.get("admin_text", "(생성 실패)") + "\n\n"

    txt_path = OUTPUT_DIR / f"{base_name}_admin.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(admin_text)
    logger.info(f"Admin 텍스트 저장: {txt_path}")

    # CSV 저장 (DB 추가용)
    import csv
    csv_path = OUTPUT_DIR / f"{base_name}.csv"

    next_no = db_loader.get_next_content_number()
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    day_str = weekdays[target_date.weekday()]

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["No.", "date", "day", "situation", "level1", "level2", "level3", "mommyvoca"])

        # 각 레벨의 admin_text 추출
        l1_text = levels.get("level_1", {}).get("variants", {}).get(best_combo.get("level_1", "A"), {}).get("admin_text", "")
        l2_text = levels.get("level_2", {}).get("variants", {}).get(best_combo.get("level_2", "A"), {}).get("admin_text", "")
        l3_text = levels.get("level_3", {}).get("variants", {}).get(best_combo.get("level_3", "A"), {}).get("admin_text", "")

        writer.writerow([
            next_no,
            target_date.strftime("%Y-%m-%d"),
            day_str,
            topic,
            l1_text,
            l2_text,
            l3_text,
            ""  # mommyvoca는 Canva에서 추가
        ])

    logger.info(f"CSV 저장: {csv_path}")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="마미톡잉글리시 콘텐츠 파이프라인")
    parser.add_argument("--topic", "-t", type=str, help="확정 주제 (없으면 자동 제안)")
    parser.add_argument("--date", "-d", type=str, help="발송일 (YYYY-MM-DD, 기본: 내일)")
    parser.add_argument("--weather", "-w", type=str, default="정보 없음", help="날씨 정보")
    parser.add_argument("--skip-suggest", action="store_true", help="Step 0 스킵")

    args = parser.parse_args()

    # 날짜 파싱
    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")

    # 파이프라인 실행
    results = run_pipeline(
        topic=args.topic,
        target_date=target_date,
        weather_note=args.weather,
        skip_suggest=args.skip_suggest
    )

    print("\n" + "=" * 60)
    print("결과 요약")
    print("=" * 60)
    print(f"주제: {results['topic']}")
    print(f"발송일: {results['target_date']}")

    step4 = results.get("steps", {}).get("step4", {})
    overall = step4.get("overall_recommendation", {})
    print(f"추천 조합: {overall.get('best_combination', {})}")
    print(f"신뢰도: {overall.get('confidence', 'unknown')}")
    print(f"담당자 검토 포인트: {overall.get('human_review_focus', '없음')}")

    if results.get("manual_review_required"):
        print("\n⚠️  5회 시도 후에도 통과 실패. 수동 검토 필요.")


if __name__ == "__main__":
    main()
