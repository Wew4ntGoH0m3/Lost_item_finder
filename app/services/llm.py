import json
import logging

import httpx
from flask import current_app

logger = logging.getLogger(__name__)
SCORE_LIMITS = {
    "category": 30.0,
    "color": 15.0,
    "location": 20.0,
    "time": 15.0,
    "feature": 20.0,
}


def _strip_code_fence(content: str) -> str:
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines)
    return value.strip()


def _post_data(post, lost: bool) -> dict:
    return {
        "id": post.id,
        "category": post.category,
        "color": post.color,
        "location": post.location,
        "occurredAt": (post.lost_at if lost else post.found_at).isoformat(),
        "features": post.features,
        "description": post.description or "",
    }


def _validate_result(raw: dict, allowed_ids: set[int]) -> dict[int, dict]:
    validated = {}
    for item in raw.get("matches", []):
        try:
            found_id = int(item["foundPostId"])
            if found_id not in allowed_ids:
                continue
            scores = {key: float(item[f"{key}Score"]) for key in SCORE_LIMITS}
            if any(value < 0 or value > SCORE_LIMITS[key] for key, value in scores.items()):
                continue
            reasons = [
                str(reason)[:200] for reason in item.get("reasons", []) if isinstance(reason, str)
            ][:5]
            validated[found_id] = {
                **scores,
                "score": round(sum(scores.values()), 2),
                "reasons": reasons,
            }
        except (KeyError, TypeError, ValueError):
            continue
    return validated


def rank_with_llm(lost_post, candidates) -> tuple[dict[int, dict], str] | None:
    api_key = current_app.config["LLM_API_KEY"]
    if not api_key or not candidates:
        return None

    payload = {
        "lostPost": _post_data(lost_post, lost=True),
        "foundCandidates": [_post_data(item, lost=False) for item in candidates],
        "scoreLimits": SCORE_LIMITS,
    }
    system_prompt = (
        "You match a lost-item post against found-item candidates. "
        "Return JSON only with a matches array. Each item must contain foundPostId, "
        "categoryScore, colorScore, locationScore, timeScore, featureScore, and reasons. "
        "Never invent candidate IDs. Respect every score limit. Do not expose private data."
    )
    request_body = {
        "model": current_app.config["LLM_MODEL"],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    url = f"{current_app.config['LLM_BASE_URL'].rstrip('/')}/chat/completions"
    try:
        with httpx.Client(timeout=current_app.config["LLM_TIMEOUT_SECONDS"]) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_body,
            )
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        raw = json.loads(_strip_code_fence(content))
        results = _validate_result(raw, {item.id for item in candidates})
        if not results:
            return None
        return results, f"llm:{current_app.config['LLM_MODEL']}"
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.exception("LLM matching failed; falling back to rule scoring")
        return None
