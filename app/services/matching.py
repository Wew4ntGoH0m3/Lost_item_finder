import re
from datetime import timezone
from decimal import Decimal
from difflib import SequenceMatcher

from flask import current_app

from ..extensions import db
from ..models import FoundPost, LostPost, Match
from .llm import rank_with_llm

COLOR_GROUPS = [
    {"BLACK", "검정", "검은색", "블랙"},
    {"WHITE", "흰색", "하양", "화이트"},
    {"BLUE", "파랑", "남색", "블루"},
    {"RED", "빨강", "레드"},
    {"GRAY", "GREY", "회색", "그레이"},
]


def _normalize(value: str | None) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", (value or "").lower())


def _same_group(left: str, right: str, groups: list[set[str]]) -> bool:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    return any(
        left_normalized in {_normalize(item) for item in group}
        and right_normalized in {_normalize(item) for item in group}
        for group in groups
    )


def _similarity(left: str | None, right: str | None) -> float:
    first = _normalize(left)
    second = _normalize(right)
    if not first or not second:
        return 0.0
    if first == second:
        return 1.0
    if first in second or second in first:
        return 0.9
    return SequenceMatcher(None, first, second).ratio()


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def rule_score(lost: LostPost, found: FoundPost) -> dict:
    category_score = 30.0 if lost.category == found.category else 0.0

    color_ratio = _similarity(lost.color, found.color)
    if color_ratio == 1:
        color_score = 15.0
    elif _same_group(lost.color, found.color, COLOR_GROUPS):
        color_score = 13.0
    else:
        color_score = round(15 * color_ratio, 2) if color_ratio >= 0.5 else 0.0

    location_ratio = _similarity(lost.location, found.location)
    location_score = round(20 * location_ratio, 2) if location_ratio >= 0.35 else 0.0

    hours = (_aware(found.found_at) - _aware(lost.lost_at)).total_seconds() / 3600
    if hours < 0:
        time_score = 0.0
    elif hours <= 0.5:
        time_score = 15.0
    elif hours <= 2:
        time_score = 13.0
    elif hours <= 6:
        time_score = 10.0
    elif hours <= 24:
        time_score = 7.0
    elif hours <= 24 * 7:
        time_score = 4.0
    else:
        time_score = 1.0

    lost_text = f"{lost.features} {lost.description or ''}"
    found_text = f"{found.features} {found.description or ''}"
    feature_ratio = max(
        _similarity(lost.features, found.features),
        _similarity(lost_text, found_text),
    )
    feature_score = round(20 * feature_ratio, 2) if feature_ratio >= 0.2 else 0.0

    reasons = []
    if category_score >= 20:
        reasons.append("물건 종류가 같거나 유사합니다.")
    if color_score >= 10:
        reasons.append("대표 색상이 일치하거나 유사합니다.")
    if location_score >= 12:
        reasons.append("분실 장소와 발견 장소가 가깝습니다.")
    if time_score >= 10:
        reasons.append(f"분실 후 {round(hours * 60)}분 이내에 발견되었습니다.")
    if feature_score >= 10:
        reasons.append("게시글의 특징과 설명이 유사합니다.")
    scores = {
        "category": category_score,
        "color": color_score,
        "location": location_score,
        "time": time_score,
        "feature": feature_score,
    }
    return {**scores, "score": round(sum(scores.values()), 2), "reasons": reasons}


def _candidate_query(lost: LostPost, candidate_ids=None):
    statement = (
        db.select(FoundPost)
        .where(
            FoundPost.site_code == lost.site_code,
            FoundPost.status == "STORED",
            FoundPost.category == lost.category,
            FoundPost.found_at >= lost.lost_at,
        )
        .order_by(FoundPost.found_at.asc())
        .limit(current_app.config["MATCH_CANDIDATE_LIMIT"])
    )
    if candidate_ids:
        statement = statement.where(FoundPost.id.in_(candidate_ids))
    return list(db.session.scalars(statement))


def analyze_lost_post(lost_post_id: int, candidate_ids=None) -> dict:
    lost = db.session.get(LostPost, lost_post_id)
    if not lost or lost.status != "OPEN":
        return {"lostPostId": lost_post_id, "matched": 0, "skipped": True}
    candidates = _candidate_query(lost, candidate_ids)
    rule_results = {item.id: rule_score(lost, item) for item in candidates}
    llm_result = rank_with_llm(lost, candidates)
    if llm_result:
        llm_results, model_version = llm_result
        results = {item.id: llm_results.get(item.id, rule_results[item.id]) for item in candidates}
    else:
        results = rule_results
        model_version = "rule-v1"

    saved = 0
    threshold = current_app.config["MATCH_MIN_SCORE"]
    for candidate in candidates:
        db.session.refresh(candidate)
        if candidate.status != "STORED":
            continue
        result = results[candidate.id]
        existing = db.session.scalar(
            db.select(Match).where(
                Match.lost_post_id == lost.id, Match.found_post_id == candidate.id
            )
        )
        if result["score"] < threshold:
            if existing and existing.status == "CANDIDATE":
                db.session.delete(existing)
            continue
        match = existing or Match(lost_post_id=lost.id, found_post_id=candidate.id)
        if existing and existing.status != "CANDIDATE":
            continue
        match.score = Decimal(str(result["score"]))
        match.category_score = Decimal(str(result["category"]))
        match.color_score = Decimal(str(result["color"]))
        match.location_score = Decimal(str(result["location"]))
        match.time_score = Decimal(str(result["time"]))
        match.feature_score = Decimal(str(result["feature"]))
        match.reasons = result["reasons"]
        match.model_version = model_version
        match.status = "CANDIDATE"
        if not existing:
            db.session.add(match)
        saved += 1
    db.session.commit()
    return {"lostPostId": lost.id, "candidates": len(candidates), "matched": saved}


def analyze_found_post(found_post_id: int) -> dict:
    found = db.session.get(FoundPost, found_post_id)
    if not found or found.status != "STORED":
        return {"foundPostId": found_post_id, "matched": 0, "skipped": True}
    statement = (
        db.select(LostPost.id)
        .where(
            LostPost.site_code == found.site_code,
            LostPost.status == "OPEN",
            LostPost.category == found.category,
            LostPost.lost_at <= found.found_at,
        )
        .order_by(LostPost.lost_at.desc())
        .limit(current_app.config["MATCH_CANDIDATE_LIMIT"])
    )
    lost_ids = list(db.session.scalars(statement))
    matched = sum(
        analyze_lost_post(lost_id, candidate_ids=[found.id])["matched"] for lost_id in lost_ids
    )
    return {"foundPostId": found.id, "lostPosts": len(lost_ids), "matched": matched}
