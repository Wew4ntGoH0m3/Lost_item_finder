import base64
import io
import json
import logging
from datetime import datetime, timezone

import httpx
from flask import current_app
from PIL import Image, UnidentifiedImageError

from ..models import ITEM_CATEGORY_LABELS, ItemCategory

logger = logging.getLogger(__name__)

LLM_IMAGE_MAX_DIMENSION = 768
LLM_IMAGE_JPEG_QUALITY = 80

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

KOREAN_COLOR_TO_CODE = {
    "검정색": "BLACK",
    "흰색": "WHITE",
    "파란색": "BLUE",
    "빨간색": "RED",
    "회색": "GRAY",
    "초록색": "GREEN",
    "노란색": "YELLOW",
    "보라색": "PURPLE",
    "분홍색": "PINK",
    "갈색": "BROWN",
    "주황색": "ORANGE",
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
    observations = observations.strip()

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


def _validate_generated_content(raw, facts: dict[str, str]) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None

    fallback = _grounded_template(facts)
    content = {}

    for field, limit in (("title", 100), ("features", 2000), ("description", 2000)):
        value = raw.get(field)
        text = str(value).strip() if value is not None else ""
        content[field] = text[:limit].rstrip() if text else fallback[field]

    return content


def _prepare_image_for_llm(image_bytes: bytes) -> bytes:
    """Downscale/re-encode so full-resolution phone photos don't blow the LLM timeout."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError):
        return image_bytes

    image.thumbnail((LLM_IMAGE_MAX_DIMENSION, LLM_IMAGE_MAX_DIMENSION))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=LLM_IMAGE_JPEG_QUALITY)
    return buffer.getvalue()


def _post_to_ollama(request_body: dict) -> dict:
    url = f"{current_app.config['OLLAMA_BASE_URL'].rstrip('/')}/api/chat"
    timeout = current_app.config["OLLAMA_CONTENT_TIMEOUT_SECONDS"]

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=request_body)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "Ollama request failed: status=%s body=%s",
                response.status_code,
                response.text[:1000],
            )
            raise

    return response.json()


def _read_ollama_message_content(response_json: dict) -> str:
    message = response_json.get("message")

    if not isinstance(message, dict):
        raise ValueError("Ollama response message is missing or invalid")

    # qwen3-vl ignores the "think": false request flag (Ollama issue #14798/#13353)
    # and always puts its answer in "thinking" instead of "content".
    content = message.get("content") or message.get("thinking")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama response message content/thinking is empty")

    return content


def generate_found_post_content(facts: dict[str, str]) -> tuple[dict[str, str], str]:
    fallback = _grounded_template(facts)

    if not current_app.config["OLLAMA_ENABLED"]:
        return fallback, "grounded-template-v1"

    system_prompt = (
        "당신은 습득물 게시글 작성기입니다. "
        "sourceFacts JSON에 실제로 존재하는 정보만 사용해 한국어 title, features, "
        "description을 작성하세요. "
        "브랜드, 모델, 소유자, 물건 상태, 손상, 내용물, 발견 경위 등 제공되지 않은 "
        "사실을 추측하거나 추가하지 마세요. "
        "값이 없는 정보는 언급하지 마세요. "
        "observations의 의미를 확대하지 마세요. "
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

    try:
        response_content = _read_ollama_message_content(_post_to_ollama(request_body))
        raw = json.loads(_strip_code_fence(response_content))

        content = _validate_generated_content(raw, facts)

        if content:
            return content, f"ollama:{current_app.config['OLLAMA_MODEL']}"

    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.exception("LLM found-post generation failed; using grounded template")

    return fallback, "grounded-template-v1"


def build_found_image_facts(
    location: str,
    found_at: datetime,
    observations: str,
) -> dict[str, str]:
    observations = observations.strip()

    facts = {
        "location": location.strip(),
        "foundAt": found_at.astimezone(timezone.utc).isoformat(),
    }

    if observations:
        facts["observations"] = observations

    return facts


def _grounded_image_template(facts: dict[str, str]) -> dict[str, str]:
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


def _normalize_category(value, fallback: ItemCategory) -> ItemCategory:
    raw = str(value or "").strip()

    if not raw:
        return fallback

    candidates = [
        raw,
        raw.upper(),
        raw.lower(),
    ]

    for candidate in candidates:
        try:
            return ItemCategory(candidate)
        except ValueError:
            pass

    member_name = raw.upper()

    if member_name in ItemCategory.__members__:
        return ItemCategory[member_name]

    return fallback


def _normalize_color(value, fallback: str) -> str:
    raw = str(value or "").strip()

    if not raw:
        return fallback

    upper = raw.upper()

    if upper in COLOR_LABELS:
        return upper

    if upper == "UNKNOWN":
        return "UNKNOWN"

    if raw in KOREAN_COLOR_TO_CODE:
        return KOREAN_COLOR_TO_CODE[raw]

    return fallback


def _validate_generated_image_content(raw, facts: dict[str, str]) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None

    fallback = _grounded_image_template(facts)

    category = _normalize_category(raw.get("category"), fallback["category"])
    color = _normalize_color(raw.get("color"), fallback["color"])

    text_fields = {}

    for field, limit in (("title", 100), ("features", 2000), ("description", 2000)):
        value = raw.get(field)
        text = str(value).strip() if value is not None else ""
        text_fields[field] = text[:limit].rstrip() if text else fallback[field]

    return {
        "category": category,
        "color": color,
        **text_fields,
    }


def generate_found_post_content_from_image(
    image_bytes: bytes,
    facts: dict[str, str],
) -> tuple[dict[str, str], str]:
    fallback = _grounded_image_template(facts)

    if not current_app.config["OLLAMA_ENABLED"]:
        return fallback, "grounded-template-v1"

    category_options = ", ".join(item.value for item in ItemCategory)
    color_options = ", ".join([*COLOR_LABELS.keys(), "UNKNOWN"])

    system_prompt = (
        "당신은 습득물 게시글 작성기입니다. "
        "첨부된 사진과 sourceFacts JSON에 실제로 존재하는 정보만 사용하세요. "
        f"category는 반드시 다음 중 하나만 사용하세요: {category_options}. "
        f"color는 가능하면 다음 중 하나만 사용하세요: {color_options}. "
        "색상을 판단하기 어려우면 UNKNOWN을 사용하세요. "
        "한국어 title, features, description을 작성하세요. "
        "사진에서 직접 확인할 수 없는 브랜드, 모델, 소유자, 손상, 내용물, "
        "발견 경위 등을 추측하거나 추가하지 마세요. "
        "sourceFacts에 없는 정보는 언급하지 마세요. "
        "observations의 의미를 확대하지 마세요. "
        "JSON 외에는 출력하지 마세요."
    )

    image_b64 = base64.b64encode(_prepare_image_for_llm(image_bytes)).decode("ascii")

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

    try:
        response_content = _read_ollama_message_content(_post_to_ollama(request_body))
        raw = json.loads(_strip_code_fence(response_content))

        content = _validate_generated_image_content(raw, facts)

        if content:
            return content, f"ollama-vision:{current_app.config['OLLAMA_MODEL']}"

    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.exception("LLM found-post image analysis failed; using grounded template")

    return fallback, "grounded-template-v1"