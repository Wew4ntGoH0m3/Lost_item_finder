import io

from conftest import auth, login, signup

FOUND_PAYLOAD = {
    "siteCode": "SCHOOL_001",
    "title": "체육관에서 검정 이어폰 케이스 주움",
    "category": "EARPHONE_CASE",
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


def create_matching_posts(client, owner_token, finder_token):
    found_response = client.post(
        "/api/v1/found-posts", json=FOUND_PAYLOAD, headers=auth(finder_token)
    )
    assert found_response.status_code == 201
    found_id = found_response.get_json()["data"]["post"]["id"]
    lost_response = client.post("/api/v1/lost-posts", json=LOST_PAYLOAD, headers=auth(owner_token))
    assert lost_response.status_code == 201
    lost_id = lost_response.get_json()["data"]["post"]["id"]
    return lost_id, found_id


def test_signup_login_and_private_field_visibility(client):
    owner_token, finder_token = create_users(client)
    lost_id, _ = create_matching_posts(client, owner_token, finder_token)

    public = client.get(f"/api/v1/lost-posts/{lost_id}")
    assert public.status_code == 200
    assert "privateFeature" not in public.get_json()["data"]

    owner = client.get(f"/api/v1/lost-posts/{lost_id}", headers=auth(owner_token))
    assert owner.get_json()["data"]["privateFeature"] == "안쪽에 K 이니셜"


def test_registration_automatically_creates_match(client):
    owner_token, finder_token = create_users(client)
    lost_id, found_id = create_matching_posts(client, owner_token, finder_token)

    response = client.get(f"/api/v1/matches/lost-posts/{lost_id}", headers=auth(owner_token))
    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["foundPostId"] == found_id
    assert items[0]["score"] >= 85
    assert items[0]["modelVersion"] == "rule-v1"
    assert items[0]["reasons"]


def test_claim_excludes_found_item_from_public_query(client):
    owner_token, finder_token = create_users(client)
    lost_id, found_id = create_matching_posts(client, owner_token, finder_token)
    matches = client.get(
        f"/api/v1/matches/lost-posts/{lost_id}", headers=auth(owner_token)
    ).get_json()["data"]["items"]

    claim = client.post(
        f"/api/v1/matches/{matches[0]['id']}/claims",
        json={"answer": "흰색 별 모양", "message": "제 물건 같습니다."},
        headers=auth(owner_token),
    )
    assert claim.status_code == 200
    assert claim.get_json()["data"]["status"] == "CLAIM_REQUESTED"

    listing = client.get("/api/v1/found-posts?status=CLAIMED")
    assert listing.status_code == 200
    assert listing.get_json()["data"]["items"] == []

    detail = client.get(f"/api/v1/found-posts/{found_id}")
    assert detail.get_json()["data"]["status"] == "CLAIMED"


def test_verify_and_admin_handover(client, admin):
    owner_token, finder_token = create_users(client)
    admin_token = login(client, "admin@example.com", "AdminPass123!")
    lost_id, _ = create_matching_posts(client, owner_token, finder_token)
    match = client.get(
        f"/api/v1/matches/lost-posts/{lost_id}", headers=auth(owner_token)
    ).get_json()["data"]["items"][0]

    client.post(
        f"/api/v1/matches/{match['id']}/claims",
        json={"answer": "흰색 별 모양"},
        headers=auth(owner_token),
    )
    verified = client.patch(f"/api/v1/matches/{match['id']}/verify", headers=auth(finder_token))
    assert verified.status_code == 200
    assert verified.get_json()["data"]["status"] == "VERIFIED"

    handed_over = client.patch(f"/api/v1/matches/{match['id']}/handover", headers=auth(admin_token))
    assert handed_over.status_code == 200
    data = handed_over.get_json()["data"]
    assert data["status"] == "HANDED_OVER"
    assert data["lostPost"]["status"] == "RETURNED"
    assert data["foundPost"]["status"] == "RETURNED"


def test_image_upload_is_written_to_instance_storage(client, app):
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
    assert data["url"].startswith("/uploads/")

    stored = client.get(data["url"])
    assert stored.status_code == 200
    assert stored.data == b"fake-png-content"


def test_found_registration_also_triggers_matching(client):
    owner_token, finder_token = create_users(client)
    lost_response = client.post("/api/v1/lost-posts", json=LOST_PAYLOAD, headers=auth(owner_token))
    lost_id = lost_response.get_json()["data"]["post"]["id"]
    client.post("/api/v1/found-posts", json=FOUND_PAYLOAD, headers=auth(finder_token))

    items = client.get(
        f"/api/v1/matches/lost-posts/{lost_id}", headers=auth(owner_token)
    ).get_json()["data"]["items"]
    assert len(items) == 1
