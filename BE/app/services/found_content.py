import base64
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from flask import current_app

from ..models import ITEM_CATEGORY_LABELS, ItemCategory

logger = logging.getLogger(__name__)

COLOR_LABELS = {
    "BLACK": "검정색",
    "WHITE": "흰색",
    "BLUE": "파란색",
    "RED": "빨간색",
    "GRAY": "회색",
    "GREY": "회색",
    "GREEN": "초록색",
    "YELLOW": "노란색",
    "PURPLE": "보라색",
    "PINK": "분홍색",
    "BROWN": "갈색",
    "ORANGE": "주황색",
}

CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "features": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["title", "features", "description"],
    "additionalProperties": False,
}

IMAGE_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [item.value for item in ItemCategory]},
        "color": {"type": "string"},
        "title": {"type": "string"},
        "features": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["category", "color", "title", "features", "description"],
    "additionalProperties": False,
}


def build_found_content_facts(
    category: ItemCategory,
    color: str,
    location: str,
    found_at: datetime,
    observations: str,
) -> dict[str, str]:
    normalized_color = color.strip().upper()
    facts = {
        "category": ITEM_CATEGORY_LABELS[category],
        "color": COLOR_LABELS.get(normalized_color, color.strip()),
        "location": location.strip(),
        "foundAt": found_at.astimezone(timezone.utc).isoformat(),
    }
    if observations:
        facts["observations"] = observations
    return facts


def _grounded_template(facts: dict[str, str]) -> dict[str, str]:
    title = f"{facts['location']}에서 {facts['color']} {facts['category']} 습득"
    features = facts.get("observations") or f"{facts['color']} {facts['category']}"
    found_at = datetime.fromisoformat(facts["foundAt"]).astimezone(timezone.utc)
    description = f"{found_at:%Y-%m-%d %H:%M UTC}에 {facts['location']}에서 발견했습니다."
    return {
        "title": title[:100].rstrip(),
        "features": features[:2000].rstrip(),
        "description": description[:2000].rstrip(),
    }


def _strip_code_fence(content: str) -> str:
    value = content.strip()
    if not value.startswith("```"):
        return value
    lines = value.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", value).lower()


def _validate_generated_content(raw, facts: dict[str, str]) -> dict[str, str] | None:
    if not isinstance(raw, dict) or set(raw) != {"title", "features", "description"}:
        return None
    if not all(isinstance(raw[field], str) for field in raw):
        return None

    content = {field: raw[field].strip() for field in raw}
    if not content["title"] or len(content["title"]) > 100:
        return None
    if not content["features"] or len(content["features"]) > 2000:
        return None
    if not content["description"] or len(content["description"]) > 2000:
        return None

    combined = _normalize(" ".join(content.values()))
    category_terms = [_normalize(item) for item in facts["category"].split("/")]
    required_terms = [_normalize(facts["location"]), _normalize(facts["color"])]
    if any(term and term not in combined for term in required_terms):
        return None
    if not any(term and term in combined for term in category_terms):
        return None

    source_numbers = {
        str(int(value)) for value in re.findall(r"\d+", " ".join(facts.values()))
    }
    generated_numbers = {
        str(int(value)) for value in re.findall(r"\d+", " ".join(content.values()))
    }
    if not generated_numbers.issubset(source_numbers):
        return None
    return content


def generate_found_post_content(facts: dict[str, str]) -> tuple[dict[str, str], str]:
    fallback = _grounded_template(facts)
    if not current_app.config["OLLAMA_ENABLED"]:
        return fallback, "grounded-template-v1"

    system_prompt = (
        "당신은 습득물 게시글 작성기입니다. sourceFacts JSON에 실제로 존재하는 정보만 "
        "사용해 한국어 title, features, description을 작성하세요. 브랜드, 모델, 소유자, "
        "물건 상태, 손상, 내용물, 발견 경위 등 제공되지 않은 사실을 추측하거나 추가하지 "
        "마세요. 값이 없는 정보는 언급하지 마세요. observations의 의미를 확대하지 마세요. "
        "JSON 외에는 출력하지 마세요."
    )
    request_body = {
        "model": current_app.config["OLLAMA_MODEL"],
        "stream": False,
        "think": False,
        "format": CONTENT_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps({"sourceFacts": facts}, ensure_ascii=False),
            },
        ],
    }
    url = f"{current_app.config['OLLAMA_BASE_URL'].rstrip('/')}/api/chat"
    try:
        with httpx.Client(timeout=current_app.config["OLLAMA_CONTENT_TIMEOUT_SECONDS"]) as client:
            response = client.post(url, json=request_body)
            response.raise_for_status()
        message = response.json()["message"]
        response_content = message.get("content") or message.get("thinking")
        raw = json.loads(_strip_code_fence(response_content))
        content = _validate_generated_content(raw, facts)
        if content:
            return content, f"ollama:{current_app.config['OLLAMA_MODEL']}"
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.exception("LLM found-post generation failed; using grounded template")
    return fallback, "grounded-template-v1"


def build_found_image_facts(location: str, found_at: datetime, observations: str) -> dict[str, str]:
    facts = {
        "location": location.strip(),
        "foundAt": found_at.astimezone(timezone.utc).isoformat(),
    }
    if observations:
        facts["observations"] = observations
    return facts


def _grounded_image_template(facts: dict[str, str]) -> dict:
    title = f"{facts['location']}에서 발견된 물품"
    features = facts.get("observations") or "사진을 확인해 주세요."
    found_at = datetime.fromisoformat(facts["foundAt"]).astimezone(timezone.utc)
    description = (
        f"{found_at:%Y-%m-%d %H:%M UTC}에 {facts['location']}에서 발견했습니다. "
        "사진을 참고해 주세요."
    )
    return {
        "category": ItemCategory.ETC,
        "color": "UNKNOWN",
        "title": title[:100].rstrip(),
        "features": features[:2000].rstrip(),
        "description": description[:2000].rstrip(),
    }


def _validate_generated_image_content(raw, facts: dict[str, str]) -> dict | None:
    if not isinstance(raw, dict) or set(raw) != {
        "category",
        "color",
        "title",
        "features",
        "description",
    }:
        return None
    if not all(isinstance(raw[field], str) for field in raw):
        return None

    try:
        category = ItemCategory(raw["category"].strip().upper())
    except ValueError:
        return None

    color = raw["color"].strip().upper()
    if not color or len(color) > 30 or not re.fullmatch(r"[0-9A-Z가-힣 ]+", color):
        return None

    text_fields = {field: raw[field].strip() for field in ("title", "features", "description")}
    if not text_fields["title"] or len(text_fields["title"]) > 100:
        return None
    if not text_fields["features"] or len(text_fields["features"]) > 2000:
        return None
    if not text_fields["description"] or len(text_fields["description"]) > 2000:
        return None

    combined = _normalize(" ".join(text_fields.values()))
    location_term = _normalize(facts["location"])
    if location_term and location_term not in combined:
        return None

    source_numbers = {
        str(int(value)) for value in re.findall(r"\d+", " ".join(facts.values()))
    }
    generated_numbers = {
        str(int(value)) for value in re.findall(r"\d+", " ".join(text_fields.values()))
    }
    if not generated_numbers.issubset(source_numbers):
        return None

    return {"category": category, "color": color, **text_fields}


def generate_found_post_content_from_image(
    image_bytes: bytes, facts: dict[str, str]
) -> tuple[dict, str]:
    fallback = _grounded_image_template(facts)
    if not current_app.config["OLLAMA_ENABLED"]:
        return fallback, "grounded-template-v1"

    category_options = ", ".join(item.value for item in ItemCategory)
    system_prompt = (
        "당신은 습득물 게시글 작성기입니다. 첨부된 사진과 sourceFacts JSON에 실제로 존재하는 "
        f"정보만 사용해 category({category_options} 중 하나), color, 한국어 title, features, "
        "description을 작성하세요. 사진에서 직접 확인할 수 없는 브랜드, 모델, 소유자, 손상, "
        "내용물, 발견 경위 등을 추측하거나 추가하지 마세요. sourceFacts에 없는 정보는 언급하지 "
        "마세요. JSON 외에는 출력하지 마세요."
    )
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    request_body = {
        "model": current_app.config["OLLAMA_MODEL"],
        "stream": False,
        "think": False,
        "format": IMAGE_CONTENT_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps({"sourceFacts": facts}, ensure_ascii=False),
                "images": [image_b64],
            },
        ],
    }
    url = f"{current_app.config['OLLAMA_BASE_URL'].rstrip('/')}/api/chat"
    try:
        with httpx.Client(timeout=current_app.config["OLLAMA_CONTENT_TIMEOUT_SECONDS"]) as client:
            response = client.post(url, json=request_body)
            response.raise_for_status()
        message = response.json()["message"]
        response_content = message.get("content") or message.get("thinking")
        raw = json.loads(_strip_code_fence(response_content))
        content = _validate_generated_image_content(raw, facts)
        if content:
            return content, f"ollama-vision:{current_app.config['OLLAMA_MODEL']}"
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.exception("LLM found-post image analysis failed; using grounded template")
    return fallback, "grounded-template-v1"
