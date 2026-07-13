import base64
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models import ItemCategory
from app.services.found_content import (
    build_found_content_facts,
    build_found_image_facts,
    generate_found_post_content,
    generate_found_post_content_from_image,
)
from app.services.llm import rank_with_llm


def test_ollama_native_json_matching(monkeypatch, app):
    captured = {}
    result_body = {
        "matches": [
            {
                "foundPostId": 2,
                "categoryScore": 30,
                "colorScore": 15,
                "locationScore": 18,
                "timeScore": 15,
                "featureScore": 20,
                "reasons": ["동일한 카테고리 태그와 특징입니다."],
            }
        ]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": "",
                    "thinking": json.dumps(result_body, ensure_ascii=False),
                }
            }

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            captured["url"] = url
            captured["body"] = json
            return FakeResponse()

    lost = SimpleNamespace(
        id=1,
        category=ItemCategory.CARD,
        color="BLUE",
        location="강당",
        lost_at=datetime(2026, 7, 13, 14, 0, tzinfo=timezone.utc),
        features="학교 로고",
        description="학생증",
    )
    found = SimpleNamespace(
        id=2,
        category=ItemCategory.CARD,
        color="BLUE",
        location="강당 입구",
        found_at=datetime(2026, 7, 13, 14, 10, tzinfo=timezone.utc),
        features="학교 로고",
        description="학생증",
    )

    monkeypatch.setattr("app.services.llm.httpx.Client", FakeClient)
    app.config.update(
        OLLAMA_ENABLED=True,
        OLLAMA_BASE_URL="http://100.102.0.2:11434",
        OLLAMA_MODEL="qwen3-vl:4b",
        OLLAMA_TIMEOUT_SECONDS=60,
    )
    with app.app_context():
        results, model_version = rank_with_llm(lost, [found])

    assert model_version == "ollama:qwen3-vl:4b"
    assert results[2]["score"] == 98
    assert captured["url"] == "http://100.102.0.2:11434/api/chat"
    assert captured["body"]["model"] == "qwen3-vl:4b"
    assert captured["body"]["stream"] is False
    assert captured["body"]["think"] is False
    assert captured["body"]["format"] == "json"


def test_ollama_generates_grounded_found_post_content(monkeypatch, app):
    captured = {}
    result_body = {
        "title": "강당 입구에서 파란색 학생증을 주웠습니다",
        "features": "파란색 학생증이며 앞면에 학교 로고가 있습니다.",
        "description": "2026년 7월 13일 14시 20분에 강당 입구에서 발견했습니다.",
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": "",
                    "thinking": json.dumps(result_body, ensure_ascii=False),
                }
            }

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            captured["url"] = url
            captured["body"] = json
            return FakeResponse()

    facts = build_found_content_facts(
        ItemCategory.CARD,
        "BLUE",
        "강당 입구",
        datetime(2026, 7, 13, 14, 20, tzinfo=timezone.utc),
        "앞면에 학교 로고",
    )
    monkeypatch.setattr("app.services.found_content.httpx.Client", FakeClient)
    app.config.update(
        OLLAMA_ENABLED=True,
        OLLAMA_BASE_URL="http://100.102.0.2:11434",
        OLLAMA_MODEL="qwen3-vl:4b",
        OLLAMA_CONTENT_TIMEOUT_SECONDS=20,
    )
    with app.app_context():
        content, generator = generate_found_post_content(facts)

    assert content == result_body
    assert generator == "ollama:qwen3-vl:4b"
    assert captured["timeout"] == 20
    assert captured["body"]["think"] is False
    assert captured["body"]["format"]["additionalProperties"] is False
    assert json.loads(captured["body"]["messages"][1]["content"]) == {
        "sourceFacts": facts
    }
    request_text = json.dumps(captured["body"], ensure_ascii=False)
    assert "학생회실" not in request_text
    assert "이름 초성" not in request_text


def test_found_content_passes_through_llm_output_without_fact_checking(monkeypatch, app):
    result_body = {
        "title": "강당 입구에서 파란색 학생증을 주웠습니다",
        "features": "파란색 학생증이며 안에 999만원이 있습니다.",
        "description": "2026년 7월 13일 14시 20분에 강당 입구에서 발견했습니다.",
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": json.dumps(result_body, ensure_ascii=False)}}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            return FakeResponse()

    facts = build_found_content_facts(
        ItemCategory.CARD,
        "BLUE",
        "강당 입구",
        datetime(2026, 7, 13, 14, 20, tzinfo=timezone.utc),
        "앞면에 학교 로고",
    )
    monkeypatch.setattr("app.services.found_content.httpx.Client", FakeClient)
    app.config.update(OLLAMA_ENABLED=True)
    with app.app_context():
        content, generator = generate_found_post_content(facts)

    assert generator == "ollama:qwen3-vl:4b"
    assert content["features"] == result_body["features"]


def test_ollama_analyzes_image_for_category_and_content(monkeypatch, app):
    captured = {}
    result_body = {
        "category": "WALLET",
        "color": "BROWN",
        "title": "강당 입구에서 발견된 갈색 지갑",
        "features": "갈색 지갑이며 앞면에 학교 로고가 있습니다.",
        "description": "2026년 7월 13일 14시 20분에 강당 입구에서 발견했습니다.",
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": json.dumps(result_body, ensure_ascii=False)}}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            captured["url"] = url
            captured["body"] = json
            return FakeResponse()

    facts = build_found_image_facts(
        "강당 입구",
        datetime(2026, 7, 13, 14, 20, tzinfo=timezone.utc),
        "앞면에 학교 로고",
    )
    monkeypatch.setattr("app.services.found_content.httpx.Client", FakeClient)
    app.config.update(
        OLLAMA_ENABLED=True,
        OLLAMA_BASE_URL="http://100.102.0.2:11434",
        OLLAMA_MODEL="qwen3-vl:4b",
        OLLAMA_CONTENT_TIMEOUT_SECONDS=20,
    )
    with app.app_context():
        content, generator = generate_found_post_content_from_image(b"raw-image-bytes", facts)

    assert content["category"] is ItemCategory.WALLET
    assert content["color"] == "BROWN"
    assert generator == "ollama-vision:qwen3-vl:4b"
    assert captured["body"]["messages"][1]["images"] == [
        base64.b64encode(b"raw-image-bytes").decode("ascii")
    ]
    assert json.loads(captured["body"]["messages"][1]["content"]) == {"sourceFacts": facts}


def test_found_image_content_falls_back_on_invalid_category(monkeypatch, app):
    result_body = {
        "category": "SHOE",
        "color": "BROWN",
        "title": "강당 입구에서 발견된 갈색 신발",
        "features": "갈색 신발입니다.",
        "description": "2026년 7월 13일 14시 20분에 강당 입구에서 발견했습니다.",
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": json.dumps(result_body, ensure_ascii=False)}}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            return FakeResponse()

    facts = build_found_image_facts(
        "강당 입구",
        datetime(2026, 7, 13, 14, 20, tzinfo=timezone.utc),
        "",
    )
    monkeypatch.setattr("app.services.found_content.httpx.Client", FakeClient)
    app.config.update(OLLAMA_ENABLED=True)
    with app.app_context():
        content, generator = generate_found_post_content_from_image(b"raw-image-bytes", facts)

    assert generator == "grounded-template-v1"
    assert content["category"] is ItemCategory.ETC
    assert content["color"] == "UNKNOWN"
