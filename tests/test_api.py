import io

from conftest import auth, login, signup

FOUND_PAYLOAD = {
    "siteCode": "SCHOOL_001",
    "title": "체육관에서 검정 이어폰 케이스 주움",
    "category": "EARPHONE",
    "color": "BLACK",
    "location": "체육관 입구",
    "foundAt": "2026-07-13T14:20:00Z",
    "storageLocation": "학생회실",
    "features": "작은 흰색 별 스티커",
    "privateFeature": "안쪽에 K 이니셜",
    "verificationQuestion": "스티커 모양은 무엇인가요?",
    "description": "신발장 앞에서 발견",
}

LOST_PAYLOAD = {
    "siteCode": "SCHOOL_001",
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
    signup(client, "owner@example.com", "분실자")
    signup(client, "finder@example.com", "습득자")
    return login(client, "owner@example.com"), login(client, "finder@example.com")


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


def create_matching_posts(client, owner_token, finder_token):
    found = create_found(client, finder_token)
    lost = create_lost(client, owner_token)
    return lost, found


def get_lost_matches(client, lost_id, owner_token):
    response = client.get(
        f"/api/v1/matches/lost-posts/{lost_id}",
        headers=auth(owner_token),
    )
    assert response.status_code == 200
    return response.get_json()["data"]["items"]


def test_postman_signup_login_and_jwt_protection(client):
    signup(client, "postman-user@example.com", "포스트맨")
    token = login(client, "postman-user@example.com")

    unauthorized = client.post("/api/v1/lost-posts", json=LOST_PAYLOAD)
    authorized = client.post(
        "/api/v1/lost-posts",
        json=LOST_PAYLOAD,
        headers=auth(token),
    )
    assert unauthorized.status_code == 401
    assert authorized.status_code == 201


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
    owner_token, finder_token = create_users(client)
    lost, found = create_matching_posts(client, owner_token, finder_token)

    public_lost = client.get(f"/api/v1/lost-posts/{lost['id']}").get_json()["data"]
    owner_lost = client.get(
        f"/api/v1/lost-posts/{lost['id']}", headers=auth(owner_token)
    ).get_json()["data"]
    public_found = client.get(f"/api/v1/found-posts/{found['id']}").get_json()["data"]
    owner_found = client.get(
        f"/api/v1/found-posts/{found['id']}", headers=auth(finder_token)
    ).get_json()["data"]

    assert "privateFeature" not in public_lost
    assert owner_lost["privateFeature"] == "안쪽에 K 이니셜"
    assert "privateFeature" not in public_found
    assert owner_found["privateFeature"] == "안쪽에 K 이니셜"
    assert owner_found["verificationQuestion"] == "스티커 모양은 무엇인가요?"


def test_registration_automatically_creates_same_tag_match(client):
    owner_token, finder_token = create_users(client)
    lost, found = create_matching_posts(client, owner_token, finder_token)

    items = get_lost_matches(client, lost["id"], owner_token)
    assert len(items) == 1
    assert items[0]["foundPostId"] == found["id"]
    assert items[0]["score"] >= 85
    assert items[0]["scoreDetails"]["category"] == 30
    assert items[0]["modelVersion"] == "rule-v1"


def test_candidate_query_excludes_different_category_tag(client):
    owner_token, finder_token = create_users(client)
    wallet = create_found(
        client,
        finder_token,
        category="WALLET",
        title="체육관에서 검정 지갑 주움",
    )
    earphone = create_found(client, finder_token)
    lost = create_lost(client, owner_token)

    items = get_lost_matches(client, lost["id"], owner_token)
    found_ids = {item["foundPostId"] for item in items}
    assert found_ids == {earphone["id"]}
    assert wallet["id"] not in found_ids


def test_found_registration_queries_only_same_tag_lost_posts(client):
    owner_token, finder_token = create_users(client)
    card_lost = create_lost(
        client,
        owner_token,
        category="CARD",
        title="학생증 잃어버림",
        features="파란색 학교 로고",
    )
    create_found(
        client,
        finder_token,
        category="WALLET",
        title="학생증처럼 생긴 카드지갑 주움",
        features="파란색 학교 로고",
    )
    assert get_lost_matches(client, card_lost["id"], owner_token) == []

    card_found = create_found(
        client,
        finder_token,
        category="CARD",
        title="학생증 주움",
        features="파란색 학교 로고",
    )
    items = get_lost_matches(client, card_lost["id"], owner_token)
    assert {item["foundPostId"] for item in items} == {card_found["id"]}


def test_claim_verify_and_admin_handover(client, admin):
    owner_token, finder_token = create_users(client)
    admin_token = login(client, "admin@example.com", "AdminPass123!")
    lost, found = create_matching_posts(client, owner_token, finder_token)
    match = get_lost_matches(client, lost["id"], owner_token)[0]

    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        json={"answer": "흰색 별 모양", "message": "제 물건 같습니다."},
        headers=auth(owner_token),
    )
    assert claim.status_code == 200
    assert claim.get_json()["data"]["status"] == "CLAIM_REQUESTED"

    public_listing = client.get("/api/v1/found-posts?status=CLAIMED")
    assert found["id"] not in {
        item["id"] for item in public_listing.get_json()["data"]["items"]
    }
    admin_listing = client.get(
        "/api/v1/found-posts?status=CLAIMED",
        headers=auth(admin_token),
    )
    assert found["id"] in {item["id"] for item in admin_listing.get_json()["data"]["items"]}

    verified = client.patch(
        f"/api/v1/matches/{match['id']}/verify",
        headers=auth(finder_token),
    )
    assert verified.status_code == 200
    assert verified.get_json()["data"]["status"] == "VERIFIED"

    handed_over = client.patch(
        f"/api/v1/matches/{match['id']}/handover",
        headers=auth(admin_token),
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
    owner_token, finder_token = create_users(client)
    create_lost(client, owner_token, category="CARD", title="학생증 분실")
    create_lost(client, owner_token, category="WALLET", title="지갑 분실")
    create_found(client, finder_token, category="CARD", title="학생증 습득")
    create_found(client, finder_token, category="WALLET", title="지갑 습득")

    lost_items = client.get("/api/v1/lost-posts?category=CARD").get_json()["data"]["items"]
    found_items = client.get("/api/v1/found-posts?category=CARD").get_json()["data"]["items"]
    assert {item["category"] for item in lost_items} == {"CARD"}
    assert {item["category"] for item in found_items} == {"CARD"}


def test_unresolved_path_parameter_returns_json_404(client):
    response = client.delete("/api/v1/found-posts/{{foundPostId}}")

    assert response.status_code == 404
    assert response.content_type == "application/json"
    assert response.get_json()["error"]["code"] == "ROUTE_NOT_FOUND"
