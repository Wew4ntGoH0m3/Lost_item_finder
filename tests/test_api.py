import base64
import io
import json

from conftest import auth, login, signup

FOUND_PAYLOAD = {
    "category": "EARPHONE",
    "color": "BLACK",
    "location": "체육관 입구",
    "foundAt": "2026-07-13T14:20:00Z",
    "storageLocation": "학생회실",
    "observations": "작은 흰색 별 스티커",
    "privateFeature": "안쪽에 K 이니셜",
    "verificationQuestion": "스티커 모양은 무엇인가요?",
}

LOST_PAYLOAD = {
    "title": "검정 에어팟 케이스 잃어버림",
    "category": "EARPHONE",
    "color": "BLACK",
    "location": "체육관",
    "lostAt": "2026-07-13T14:00:00Z",
    "features": "작은 흰색 별 스티커",
    "privateFeature": "안쪽에 K 이니셜",
    "description": "체육 수업 후 잃어버림",
}


def create_users(client):
    signup(client, "user-a@example.com", "사용자A")
    signup(client, "user-b@example.com", "사용자B")
    return login(client, "user-a@example.com"), login(client, "user-b@example.com")


def create_found(client, token, **overrides):
    response = client.post(
        "/api/v1/found-posts",
        json={**FOUND_PAYLOAD, **overrides},
        headers=auth(token),
    )
    assert response.status_code == 201
    return response.get_json()["data"]["post"]


def create_lost(client, token, **overrides):
    response = client.post(
        "/api/v1/lost-posts",
        json={**LOST_PAYLOAD, **overrides},
        headers=auth(token),
    )
    assert response.status_code == 201
    return response.get_json()["data"]["post"]


def create_matching_posts(client, user_a_token, user_b_token):
    found = create_found(client, user_b_token)
    lost = create_lost(client, user_a_token)
    return lost, found


def get_lost_matches(client, lost_id, user_a_token):
    response = client.get(
        f"/api/v1/matches/lost-posts/{lost_id}",
        headers=auth(user_a_token),
    )
    assert response.status_code == 200
    return response.get_json()["data"]["items"]


def test_postman_signup_login_and_jwt_protection(client):
    user = signup(client, "postman-user@example.com", "포스트맨")
    token = login(client, "postman-user@example.com")

    unauthorized = client.post("/api/v1/lost-posts", json=LOST_PAYLOAD)
    authorized = client.post(
        "/api/v1/lost-posts",
        json=LOST_PAYLOAD,
        headers=auth(token),
    )
    assert unauthorized.status_code == 401
    assert authorized.status_code == 201
    assert "siteCode" not in authorized.get_json()["data"]["post"]
    assert "role" not in user
    assert "platform" not in user
    assert "siteCode" not in user


def test_logout_is_client_side_only(client):
    signup(client, "client-logout@example.com")
    token = login(client, "client-logout@example.com")

    response = client.post("/api/v1/auth/logout", headers=auth(token))

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "ROUTE_NOT_FOUND"

    push_response = client.patch(
        "/api/v1/users/me/push-token",
        json={"platform": "ANDROID", "pushToken": "unused-token"},
        headers=auth(token),
    )
    assert push_response.status_code == 404
    assert push_response.get_json()["error"]["code"] == "ROUTE_NOT_FOUND"


def test_one_user_can_create_both_lost_and_found_posts(client):
    signup(client, "both-posts@example.com", "통합사용자")
    token = login(client, "both-posts@example.com")

    lost = create_lost(client, token)
    found = create_found(
        client,
        token,
        foundAt="2026-07-13T14:30:00Z",
    )

    assert lost["userId"] == found["userId"]
    assert "siteCode" not in lost
    assert "siteCode" not in found
    assert get_lost_matches(client, lost["id"], token) == []


def test_found_post_content_is_generated_only_from_source_facts(client):
    signup(client, "generated-found@example.com")
    token = login(client, "generated-found@example.com")
    response = client.post(
        "/api/v1/found-posts",
        json={
            **FOUND_PAYLOAD,
            "location": "강당 입구",
            "observations": "앞면에 파란색 학교 로고",
            "privateFeature": "이름 초성 ㄱㅌㅇ",
            "verificationQuestion": "이름의 초성은?",
        },
        headers=auth(token),
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    post = data["post"]
    assert post["title"] == "강당 입구에서 검정색 이어폰/이어폰 케이스 습득"
    assert post["features"] == "앞면에 파란색 학교 로고"
    assert post["description"] == "2026-07-13 14:20 UTC에 강당 입구에서 발견했습니다."
    assert post["observations"] == "앞면에 파란색 학교 로고"
    assert post["contentGenerator"] == "grounded-template-v1"
    assert data["contentGeneration"] == {
        "generator": "grounded-template-v1",
        "sourceFields": ["category", "color", "location", "foundAt", "observations"],
    }

    public = client.get(f"/api/v1/found-posts/{post['id']}").get_json()["data"]
    assert "observations" not in public
    assert "privateFeature" not in public
    assert "verificationQuestion" not in public


def test_found_post_llm_never_receives_private_fields(client, app, monkeypatch):
    captured = {}
    generated = {
        "title": "체육관 입구에서 검정색 이어폰을 주웠습니다",
        "features": "검정색 이어폰이며 흰색 별 스티커가 있습니다.",
        "description": "2026년 7월 13일 14시 20분에 체육관 입구에서 발견했습니다.",
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": json.dumps(generated, ensure_ascii=False)}}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            captured["body"] = json
            return FakeResponse()

    signup(client, "private-grounding@example.com")
    token = login(client, "private-grounding@example.com")
    monkeypatch.setattr("app.services.found_content.httpx.Client", FakeClient)
    app.config.update(OLLAMA_ENABLED=True, OLLAMA_CONTENT_TIMEOUT_SECONDS=20)
    response = client.post(
        "/api/v1/found-posts",
        json={
            **FOUND_PAYLOAD,
            "storageLocation": "비공개 보관함 7번",
            "privateFeature": "비공개 이름 초성 ㅂㄱㅈ",
            "verificationQuestion": "비공개 질문은?",
            "imageUrl": "/uploads/private-image.jpg",
        },
        headers=auth(token),
    )

    assert response.status_code == 201
    assert response.get_json()["data"]["post"]["contentGenerator"].startswith("ollama:")
    request_text = json.dumps(captured["body"], ensure_ascii=False)
    assert "비공개 보관함" not in request_text
    assert "비공개 이름 초성" not in request_text
    assert "비공개 질문" not in request_text
    assert "private-image" not in request_text
    assert json.loads(captured["body"]["messages"][1]["content"]) == {
        "sourceFacts": {
            "category": "이어폰/이어폰 케이스",
            "color": "검정색",
            "location": "체육관 입구",
            "foundAt": "2026-07-13T14:20:00+00:00",
            "observations": "작은 흰색 별 스티커",
        }
    }


def test_found_post_content_regeneration_and_manual_edit_rejection(client):
    signup(client, "regenerate-found@example.com")
    token = login(client, "regenerate-found@example.com")
    post = create_found(client, token)

    rejected = client.patch(
        f"/api/v1/found-posts/{post['id']}",
        json={"title": "사용자가 직접 정한 제목"},
        headers=auth(token),
    )
    assert rejected.status_code == 422
    assert rejected.get_json()["error"]["code"] == "VALIDATION_FAILED"

    regenerated = client.patch(
        f"/api/v1/found-posts/{post['id']}",
        json={"location": "도서관 입구", "observations": "손잡이에 흰색 테이프"},
        headers=auth(token),
    )
    assert regenerated.status_code == 200
    data = regenerated.get_json()["data"]
    assert data["post"]["title"].startswith("도서관 입구에서")
    assert data["post"]["features"] == "손잡이에 흰색 테이프"
    assert data["post"]["observations"] == "손잡이에 흰색 테이프"
    assert data["analysisQueued"] is True


def _without_fields(*fields):
    return {key: value for key, value in FOUND_PAYLOAD.items() if key not in fields}


def _upload_image(client, token, filename="item.png", content=b"fake-png-content"):
    response = client.post(
        "/api/v1/uploads/images",
        data={"image": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
        headers=auth(token),
    )
    assert response.status_code == 201
    return response.get_json()["data"]["url"]


def test_found_post_without_category_requires_image(client):
    signup(client, "no-category@example.com")
    token = login(client, "no-category@example.com")
    payload = _without_fields("category", "color")

    response = client.post("/api/v1/found-posts", json=payload, headers=auth(token))

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_found_post_rejects_partial_category_color(client):
    signup(client, "partial-category@example.com")
    token = login(client, "partial-category@example.com")
    payload = {key: value for key, value in FOUND_PAYLOAD.items() if key != "color"}
    image_url = _upload_image(client, token)

    response = client.post(
        "/api/v1/found-posts",
        json={**payload, "imageUrl": image_url},
        headers=auth(token),
    )

    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_found_post_auto_fills_category_from_image_without_llm(client):
    signup(client, "auto-fallback@example.com")
    token = login(client, "auto-fallback@example.com")
    image_url = _upload_image(client, token)
    payload = _without_fields("category", "color")

    response = client.post(
        "/api/v1/found-posts",
        json={**payload, "imageUrl": image_url},
        headers=auth(token),
    )

    assert response.status_code == 201
    post = response.get_json()["data"]["post"]
    assert post["category"] == "ETC"
    assert post["color"] == "UNKNOWN"
    assert post["contentGenerator"] == "grounded-template-v1"
    assert post["imageUrl"] == image_url


def test_found_post_auto_detects_category_from_image_via_llm(client, app, monkeypatch):
    captured = {}
    generated = {
        "category": "WALLET",
        "color": "BROWN",
        "title": "체육관 입구에서 발견된 갈색 지갑",
        "features": "갈색 지갑이며 작은 흰색 별 스티커가 있습니다.",
        "description": "2026년 7월 13일 14시 20분에 체육관 입구에서 발견했습니다.",
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": json.dumps(generated, ensure_ascii=False)}}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, json):
            captured["body"] = json
            return FakeResponse()

    signup(client, "auto-llm@example.com")
    token = login(client, "auto-llm@example.com")
    image_content = b"fake-wallet-image-bytes"
    image_url = _upload_image(client, token, content=image_content)
    monkeypatch.setattr("app.services.found_content.httpx.Client", FakeClient)
    app.config.update(OLLAMA_ENABLED=True, OLLAMA_CONTENT_TIMEOUT_SECONDS=20)
    payload = _without_fields("category", "color")

    response = client.post(
        "/api/v1/found-posts",
        json={**payload, "imageUrl": image_url},
        headers=auth(token),
    )

    assert response.status_code == 201
    post = response.get_json()["data"]["post"]
    assert post["category"] == "WALLET"
    assert post["color"] == "BROWN"
    assert post["contentGenerator"] == "ollama-vision:qwen3-vl:4b"
    assert captured["body"]["messages"][1]["images"] == [
        base64.b64encode(image_content).decode("ascii")
    ]
    request_text = json.dumps(captured["body"], ensure_ascii=False)
    assert "학생회실" not in request_text
    assert "이름 초성" not in request_text


def test_category_enum_is_exposed_and_validated(client):
    response = client.get("/api/v1/categories")
    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert {item["code"] for item in items} == {
        "CARD",
        "WALLET",
        "EARPHONE",
        "BAG",
        "KEY",
        "ELECTRONICS",
        "CLOTHING",
        "UMBRELLA",
        "STATIONERY",
        "ETC",
    }

    signup(client, "enum@example.com")
    token = login(client, "enum@example.com")
    invalid = client.post(
        "/api/v1/lost-posts",
        json={**LOST_PAYLOAD, "category": "SHOE"},
        headers=auth(token),
    )
    assert invalid.status_code == 422
    assert invalid.get_json()["error"]["code"] == "INVALID_CATEGORY"


def test_private_fields_are_visible_only_to_owner(client):
    user_a_token, user_b_token = create_users(client)
    lost, found = create_matching_posts(client, user_a_token, user_b_token)

    public_lost = client.get(f"/api/v1/lost-posts/{lost['id']}").get_json()["data"]
    owner_lost = client.get(
        f"/api/v1/lost-posts/{lost['id']}", headers=auth(user_a_token)
    ).get_json()["data"]
    public_found = client.get(f"/api/v1/found-posts/{found['id']}").get_json()["data"]
    owner_found = client.get(
        f"/api/v1/found-posts/{found['id']}", headers=auth(user_b_token)
    ).get_json()["data"]

    assert "privateFeature" not in public_lost
    assert owner_lost["privateFeature"] == "안쪽에 K 이니셜"
    assert "privateFeature" not in public_found
    assert owner_found["privateFeature"] == "안쪽에 K 이니셜"
    assert owner_found["verificationQuestion"] == "스티커 모양은 무엇인가요?"


def test_registration_automatically_creates_same_tag_match(client):
    user_a_token, user_b_token = create_users(client)
    lost, found = create_matching_posts(client, user_a_token, user_b_token)

    items = get_lost_matches(client, lost["id"], user_a_token)
    assert len(items) == 1
    assert items[0]["foundPostId"] == found["id"]
    assert items[0]["score"] >= 85
    assert items[0]["scoreDetails"]["category"] == 30
    assert items[0]["modelVersion"] == "rule-v1"


def test_candidate_query_excludes_different_category_tag(client):
    user_a_token, user_b_token = create_users(client)
    wallet = create_found(
        client,
        user_b_token,
        category="WALLET",
    )
    earphone = create_found(client, user_b_token)
    lost = create_lost(client, user_a_token)

    items = get_lost_matches(client, lost["id"], user_a_token)
    found_ids = {item["foundPostId"] for item in items}
    assert found_ids == {earphone["id"]}
    assert wallet["id"] not in found_ids


def test_found_registration_queries_only_same_tag_lost_posts(client):
    user_a_token, user_b_token = create_users(client)
    card_lost = create_lost(
        client,
        user_a_token,
        category="CARD",
        title="학생증 잃어버림",
        features="파란색 학교 로고",
    )
    create_found(
        client,
        user_b_token,
        category="WALLET",
        observations="파란색 학교 로고",
    )
    assert get_lost_matches(client, card_lost["id"], user_a_token) == []

    card_found = create_found(
        client,
        user_b_token,
        category="CARD",
        observations="파란색 학교 로고",
    )
    items = get_lost_matches(client, card_lost["id"], user_a_token)
    assert {item["foundPostId"] for item in items} == {card_found["id"]}


def test_claim_verify_and_found_author_handover(client):
    user_a_token, user_b_token = create_users(client)
    lost, found = create_matching_posts(client, user_a_token, user_b_token)
    match = get_lost_matches(client, lost["id"], user_a_token)[0]

    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        json={"answer": "흰색 별 모양", "message": "제 물건 같습니다."},
        headers=auth(user_a_token),
    )
    assert claim.status_code == 200
    assert claim.get_json()["data"]["status"] == "CLAIM_REQUESTED"

    public_listing = client.get("/api/v1/found-posts?status=CLAIMED")
    assert found["id"] not in {item["id"] for item in public_listing.get_json()["data"]["items"]}
    verified = client.patch(
        f"/api/v1/matches/{match['id']}/verify",
        headers=auth(user_b_token),
    )
    assert verified.status_code == 200
    assert verified.get_json()["data"]["status"] == "VERIFIED"

    denied_handover = client.patch(
        f"/api/v1/matches/{match['id']}/handover",
        headers=auth(user_a_token),
    )
    assert denied_handover.status_code == 403

    handed_over = client.patch(
        f"/api/v1/matches/{match['id']}/handover",
        headers=auth(user_b_token),
    )
    assert handed_over.status_code == 200
    data = handed_over.get_json()["data"]
    assert data["status"] == "HANDED_OVER"
    assert data["lostPost"]["status"] == "RETURNED"
    assert data["foundPost"]["status"] == "RETURNED"


def test_image_upload_requires_jwt_and_writes_to_storage(client):
    unauthorized = client.post(
        "/api/v1/uploads/images",
        data={"image": (io.BytesIO(b"fake-png-content"), "wallet.png")},
        content_type="multipart/form-data",
    )
    assert unauthorized.status_code == 401

    signup(client, "uploader@example.com")
    token = login(client, "uploader@example.com")
    response = client.post(
        "/api/v1/uploads/images",
        data={"image": (io.BytesIO(b"fake-png-content"), "wallet.png")},
        content_type="multipart/form-data",
        headers=auth(token),
    )
    assert response.status_code == 201
    data = response.get_json()["data"]

    stored = client.get(data["url"])
    assert stored.status_code == 200
    assert stored.data == b"fake-png-content"


def test_public_lists_filter_by_exact_category_tag(client):
    user_a_token, user_b_token = create_users(client)
    create_lost(client, user_a_token, category="CARD", title="학생증 분실")
    create_lost(client, user_a_token, category="WALLET", title="지갑 분실")
    create_found(client, user_b_token, category="CARD")
    create_found(client, user_b_token, category="WALLET")

    lost_items = client.get("/api/v1/lost-posts?category=CARD").get_json()["data"]["items"]
    found_items = client.get("/api/v1/found-posts?category=CARD").get_json()["data"]["items"]
    assert {item["category"] for item in lost_items} == {"CARD"}
    assert {item["category"] for item in found_items} == {"CARD"}


def test_unresolved_path_parameter_returns_json_404(client):
    response = client.delete("/api/v1/found-posts/{{foundPostId}}")

    assert response.status_code == 404
    assert response.content_type == "application/json"
    assert response.get_json()["error"]["code"] == "ROUTE_NOT_FOUND"
