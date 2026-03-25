"""
마미톡잉글리시 콘텐츠 DB 로더

엑셀 파일에서 콘텐츠를 파싱하고, few-shot 예시 추출, 중복 체크 등을 제공합니다.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


# DB 파일 경로
DB_PATH = Path(__file__).parent / "data" / "마미톡 컨텐츠 v.2.xlsx"


# 카테고리 분류용 키워드 매핑
# 주의: 키워드 순서와 가중치를 고려해서 배치
CATEGORY_KEYWORDS = {
    "식사/간식": ["밥 먹", "아침 먹", "점심 먹", "저녁 먹", "간식", "과일", "채소", "음료", "빵", "우유", "숟가락", "젓가락", "식사", "배고프", "배불러", "수저"],
    "위생/몸 관리": ["손 씻", "양치", "목욕", "머리 감", "손톱", "로션", "샴푸", "비누", "치약", "칫솔", "세수", "닦", "코 풀", "감기", "아프"],
    "놀이": ["블록", "그림", "퍼즐", "공놀이", "숨바꼭질", "만들기", "놀이", "장난감", "인형", "자동차", "게임", "색칠", "점토", "레고", "찾기"],
    "외출/이동": ["나가", "신발", "외투", "엘리베이터", "공원", "마트", "외출", "산책", "버스", "지하철", "나들이", "유치원", "등원", "하원", "준비해"],
    "정리/규칙": ["정리", "빨래", "차례", "규칙", "치우", "청소", "어질러", "제자리", "줄 서", "기다려", "순서"],
    "취침": ["잘 시간", "자기 전", "잘자", "꿈", "잠자", "침대", "이불", "베개", "자장가", "졸려", "눈 감", "잠들"],
    "감정/성장": ["실수", "괜찮", "스스로", "격려", "감사", "사랑", "칭찬", "행복", "슬프", "화나", "무서워", "기쁘", "고마워", "미안", "잘했어", "대견", "인사", "다정", "안아"],
    "자연/관찰": ["날씨", "동물", "식물", "하늘", "꽃", "비가", "눈이", "바람", "해", "달", "별", "나무", "새", "나비", "벌레", "단풍", "낙엽", "벚꽃", "무지개"],
}


def load_db(path: Optional[Path] = None) -> pd.DataFrame:
    """엑셀 DB 파일을 로드합니다.

    Args:
        path: 엑셀 파일 경로. None이면 기본 경로 사용.

    Returns:
        pandas DataFrame
    """
    db_path = path or DB_PATH
    df = pd.read_excel(db_path, engine="openpyxl")

    # 불필요한 컬럼 제거
    if "Unnamed: 8" in df.columns:
        df = df.drop(columns=["Unnamed: 8"])

    return df


def get_content_rows(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """일요일(복습일)을 제외한 콘텐츠 행만 반환합니다.

    Args:
        df: DataFrame. None이면 새로 로드.

    Returns:
        일요일 제외된 DataFrame
    """
    if df is None:
        df = load_db()

    # 일요일 제외
    content_df = df[df["day"] != "일"].copy()

    # level1이 NaN인 행 제외 (비정상 데이터)
    content_df = content_df.dropna(subset=["level1"])

    # No.가 NaN인 행 제외
    content_df = content_df.dropna(subset=["No."])

    return content_df


def extract_mom_sentences(level_text: str) -> dict:
    """레벨 텍스트에서 엄마 영어/한국어 문장을 추출합니다.

    Args:
        level_text: 레벨 전체 텍스트

    Returns:
        {
            "en": ["문장1", "문장2", "문장3"],
            "kr": ["한국어1", "한국어2", "한국어3"]
        }
    """
    if pd.isna(level_text):
        return {"en": [], "kr": []}

    # ⭐ 앞까지만 엄마 파트
    text = level_text.split("⭐")[0].strip()

    # 1️⃣, 2️⃣, 3️⃣로 영어 문장 분리 (정규식 사용)
    # 이모지 넘버링 패턴: 숫자 + keycap 조합
    emoji_pattern = re.compile(r"^[1-3]️⃣\s*")

    lines = text.split("\n")

    en_sentences = []
    kr_sentences = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 이모지 넘버링 체크 (정규식)
        if emoji_pattern.match(line):
            # 이모지 제거 후 영어 문장 추출
            en = emoji_pattern.sub("", line).strip()
            en_sentences.append(en)
        else:
            # 이모지 넘버링 없으면 한국어로 간주
            kr_sentences.append(line)

    return {"en": en_sentences, "kr": kr_sentences}


def extract_child_responses(level_text: str) -> dict:
    """레벨 텍스트에서 아이 반응(영어/한국어)을 추출합니다.

    Args:
        level_text: 레벨 전체 텍스트

    Returns:
        {
            "response_1": {"en": "...", "kr": "..."},
            "response_2": {"en": "...", "kr": "..."}
        }
        반응이 없으면 None 값.
    """
    if pd.isna(level_text):
        return {"response_1": None, "response_2": None}

    # ⭐ 이후 텍스트 추출
    parts = level_text.split("⭐")
    if len(parts) < 2:
        return {"response_1": None, "response_2": None}

    child_part = parts[1].strip()

    # "생략"이면 반응 없음
    if "생략" in child_part:
        return {"response_1": None, "response_2": None}

    # {아이이름}: 제거
    child_part = re.sub(r"\{아이이름\}:\s*", "", child_part)

    # 줄 단위로 분리
    lines = [l.strip() for l in child_part.split("\n") if l.strip()]

    # 패턴: 영어 / 한국어가 번갈아 나옴 (2세트)
    responses = {"response_1": None, "response_2": None}

    if len(lines) >= 2:
        responses["response_1"] = {
            "en": lines[0],
            "kr": lines[1] if len(lines) > 1 else ""
        }

    if len(lines) >= 4:
        responses["response_2"] = {
            "en": lines[2],
            "kr": lines[3] if len(lines) > 3 else ""
        }

    return responses


def categorize_topic(situation: str) -> str:
    """주제(situation)를 카테고리로 분류합니다.

    Args:
        situation: 주제명 (예: "💗 다정한 아침 인사")

    Returns:
        카테고리명 (예: "감정/성장")
    """
    if pd.isna(situation):
        return "기타"

    situation_lower = situation.lower()

    # 각 카테고리의 키워드 매칭
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in situation_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        return "기타"

    # 가장 높은 점수의 카테고리 반환
    return max(scores, key=scores.get)


def get_recent_topics(months: int = 3, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """최근 N개월 주제 리스트를 반환합니다.

    Args:
        months: 기준 개월 수
        df: DataFrame. None이면 새로 로드.

    Returns:
        최근 N개월 콘텐츠 DataFrame (No., date, day, situation, category 컬럼 포함)
    """
    if df is None:
        df = get_content_rows()

    # 기준 날짜 계산
    cutoff_date = datetime.now() - timedelta(days=months * 30)

    # 날짜 필터링
    recent = df[df["date"] >= cutoff_date].copy()

    # 카테고리 추가
    recent["category"] = recent["situation"].apply(categorize_topic)

    return recent[["No.", "date", "day", "situation", "category"]]


def get_category_distribution(months: int = 1, df: Optional[pd.DataFrame] = None) -> dict:
    """최근 N개월 카테고리별 콘텐츠 수를 집계합니다.

    Args:
        months: 기준 개월 수
        df: DataFrame. None이면 새로 로드.

    Returns:
        {"식사/간식": 5, "위생/몸 관리": 3, ...}
    """
    recent = get_recent_topics(months, df)
    return recent["category"].value_counts().to_dict()


def get_fewshot_examples(
    category: Optional[str] = None,
    level: int = 1,
    n: int = 5,
    df: Optional[pd.DataFrame] = None
) -> list[dict]:
    """few-shot 예시를 추출합니다.

    선택 기준:
    - 같은 카테고리 2개
    - 최근 2개
    - 우수 예시 1개 (다양한 카테고리에서)

    Args:
        category: 타겟 카테고리. None이면 카테고리 무관하게 추출.
        level: 1, 2, 또는 3
        n: 반환할 예시 수
        df: DataFrame. None이면 새로 로드.

    Returns:
        [
            {
                "no": 290,
                "situation": "💗 다정한 아침 인사",
                "category": "감정/성장",
                "level_text": "1️⃣ ...",
                "mom_en": ["...", "...", "..."],
                "mom_kr": ["...", "...", "..."],
                "child_responses": {...}
            },
            ...
        ]
    """
    if df is None:
        df = get_content_rows()

    level_col = f"level{level}"
    examples = []

    # 카테고리 컬럼 추가
    df = df.copy()
    df["category"] = df["situation"].apply(categorize_topic)

    # 1. 같은 카테고리에서 2개
    if category:
        same_cat = df[df["category"] == category].tail(2)
        for _, row in same_cat.iterrows():
            examples.append(_row_to_example(row, level_col))

    # 2. 최근 2개 (위에서 추가한 것과 중복 제외)
    added_nos = {ex["no"] for ex in examples}
    recent = df[~df["No."].isin(added_nos)].tail(2)
    for _, row in recent.iterrows():
        examples.append(_row_to_example(row, level_col))

    # 3. 다른 카테고리에서 1개 (다양성)
    added_nos = {ex["no"] for ex in examples}
    added_cats = {ex["category"] for ex in examples}
    other_cat = df[(~df["No."].isin(added_nos)) & (~df["category"].isin(added_cats))].tail(1)
    for _, row in other_cat.iterrows():
        examples.append(_row_to_example(row, level_col))

    return examples[:n]


def _row_to_example(row: pd.Series, level_col: str) -> dict:
    """DataFrame row를 few-shot 예시 dict로 변환합니다."""
    level_text = row[level_col]
    mom = extract_mom_sentences(level_text)
    child = extract_child_responses(level_text)

    # No.가 NaN인 경우 0 반환
    no_val = row["No."]
    no_int = int(no_val) if pd.notna(no_val) else 0

    return {
        "no": no_int,
        "situation": row["situation"],
        "category": categorize_topic(row["situation"]),
        "level_text": level_text,
        "mom_en": mom["en"],
        "mom_kr": mom["kr"],
        "child_responses": child
    }


def check_topic_overlap(
    new_topic: str,
    months: int = 3,
    df: Optional[pd.DataFrame] = None
) -> list[dict]:
    """새 주제와 기존 콘텐츠 간 중복/유사성을 체크합니다.

    Args:
        new_topic: 새 주제명
        months: 체크할 기간 (개월)
        df: DataFrame. None이면 새로 로드.

    Returns:
        [
            {
                "no": 300,
                "situation": "기존 주제",
                "similarity": "높음/중간/낮음",
                "reason": "이유 설명"
            },
            ...
        ]
    """
    recent = get_recent_topics(months, df)

    # 간단한 키워드 매칭 기반 중복 체크
    # 이모지 제거
    new_topic_clean = re.sub(r"[^\w\s]", "", new_topic).strip()
    new_words = set(new_topic_clean.split())

    overlaps = []

    for _, row in recent.iterrows():
        existing = str(row["situation"])
        existing_clean = re.sub(r"[^\w\s]", "", existing).strip()
        existing_words = set(existing_clean.split())

        # 공통 단어 수
        common = new_words & existing_words

        if len(common) >= 2:
            similarity = "높음"
            reason = f"공통 키워드: {', '.join(common)}"
        elif len(common) == 1:
            similarity = "중간"
            reason = f"공통 키워드: {', '.join(common)}"
        else:
            continue

        overlaps.append({
            "no": int(row["No."]),
            "date": row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else "",
            "situation": existing,
            "similarity": similarity,
            "reason": reason
        })

    return overlaps


def get_next_content_number(df: Optional[pd.DataFrame] = None) -> int:
    """다음 콘텐츠 번호를 반환합니다.

    Args:
        df: DataFrame. None이면 새로 로드.

    Returns:
        다음 번호 (현재 최대 + 1)
    """
    if df is None:
        df = load_db()

    max_no = df["No."].max()
    return int(max_no) + 1 if pd.notna(max_no) else 1


# === CLI 테스트용 ===
if __name__ == "__main__":
    print("=" * 60)
    print("마미톡잉글리시 DB 로더 테스트")
    print("=" * 60)

    # 1. DB 로드
    df = load_db()
    print(f"\n1. DB 로드: {len(df)}행")

    # 2. 콘텐츠 행 (일요일 제외)
    content = get_content_rows(df)
    print(f"2. 콘텐츠 행 (일요일 제외): {len(content)}행")

    # 3. 샘플 데이터 파싱
    sample = content.iloc[0]
    print(f"\n3. 샘플 파싱 (No.{int(sample['No.'])})")
    print(f"   주제: {sample['situation']}")
    print(f"   카테고리: {categorize_topic(sample['situation'])}")

    # 4. 엄마 문장 추출
    mom = extract_mom_sentences(sample["level2"])
    print(f"\n4. 레벨2 엄마 문장:")
    for i, (en, kr) in enumerate(zip(mom["en"], mom["kr"]), 1):
        print(f"   {i}. EN: {en}")
        print(f"      KR: {kr}")

    # 5. 아이 반응 추출
    child = extract_child_responses(sample["level2"])
    print(f"\n5. 레벨2 아이 반응:")
    for key, resp in child.items():
        if resp:
            print(f"   {key}: {resp['en']} / {resp['kr']}")

    # 6. 레벨1 아이 반응 (없어야 함)
    child_l1 = extract_child_responses(sample["level1"])
    print(f"\n6. 레벨1 아이 반응 (없어야 함): {child_l1}")

    # 7. 최근 주제
    recent = get_recent_topics(months=1)
    print(f"\n7. 최근 1개월 주제: {len(recent)}건")
    if len(recent) > 0:
        print(recent[["No.", "date", "situation", "category"]].head(3).to_string(index=False))

    # 8. 카테고리 분포
    dist = get_category_distribution(months=3)
    print(f"\n8. 최근 3개월 카테고리 분포:")
    for cat, count in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"   {cat}: {count}건")

    # 9. few-shot 예시
    examples = get_fewshot_examples(category="감정/성장", level=2, n=3)
    print(f"\n9. few-shot 예시 (감정/성장, 레벨2, 3개):")
    for ex in examples:
        print(f"   No.{ex['no']}: {ex['situation']} [{ex['category']}]")

    # 10. 중복 체크
    overlaps = check_topic_overlap("아침 인사 하기", months=3)
    print(f"\n10. 중복 체크 ('아침 인사 하기'):")
    if overlaps:
        for o in overlaps[:3]:
            print(f"   No.{o['no']}: {o['situation']} - {o['similarity']}")
    else:
        print("   중복 없음")

    # 11. 다음 번호
    next_no = get_next_content_number(df)
    print(f"\n11. 다음 콘텐츠 번호: {next_no}")

    print("\n" + "=" * 60)
    print("테스트 완료!")
