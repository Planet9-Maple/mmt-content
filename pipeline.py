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

    logger.info(f"{PROVIDER_EMOJI['gemini']} Gemini API 호출: {model}, temp={temperature}")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

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
            "thinkingConfig": {"thinkingBudget": 0}  # thinking 비활성화
        }
    }

    response = requests.post(url, json=payload, timeout=120)
    response.raise_for_status()

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
        max_tokens=max_tokens,
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
    df=None
) -> dict:
    """Step 0: 주제 후보 5-7개 제안."""
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

    # Step 3 & 4: 생성 + 검수 (재시도 로직 포함)
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

        results["steps"]["step3"] = step3_result

        # Step 4: 검수 (GPT - 크로스 프로바이더)
        step4_result = step4_review(step3_result, category=category, df=df)
        results["steps"]["step4"] = step4_result

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
