from conftest import auth, login, signup

from app.extensions import socketio


def _create_match(client):
    signup(client, "chat-owner@example.com", "분실자")
    signup(client, "chat-finder@example.com", "습득자")
    owner_token = login(client, "chat-owner@example.com")
    finder_token = login(client, "chat-finder@example.com")

    found = client.post(
        "/api/v1/found-posts",
        headers=auth(finder_token),
        json={
            "siteCode": "SCHOOL_001",
            "title": "체육관에서 학생증 주움",
            "category": "CARD",
            "color": "BLUE",
            "location": "체육관 입구",
            "foundAt": "2026-07-13T14:20:00Z",
            "storageLocation": "학생회실",
            "features": "파란 학교 로고",
            "verificationQuestion": "학번 끝 두 자리는?",
        },
    ).get_json()["data"]["post"]
    lost = client.post(
        "/api/v1/lost-posts",
        headers=auth(owner_token),
        json={
            "siteCode": "SCHOOL_001",
            "title": "파란 학생증 잃어버림",
            "category": "CARD",
            "color": "BLUE",
            "location": "체육관",
            "lostAt": "2026-07-13T14:00:00Z",
            "features": "파란 학교 로고",
            "privateFeature": "학번 끝 두 자리 42",
        },
    ).get_json()["data"]["post"]
    match = client.get(
        f"/api/v1/matches/lost-posts/{lost['id']}", headers=auth(owner_token)
    ).get_json()["data"]["items"][0]
    return owner_token, finder_token, found, lost, match


def test_claim_creates_participant_only_chat_room(app, client):
    owner_token, finder_token, _, _, match = _create_match(client)

    before_claim = client.post(
        f"/api/v1/chats/matches/{match['id']}", headers=auth(owner_token)
    )
    assert before_claim.status_code == 409
    assert before_claim.get_json()["error"]["code"] == "CHAT_NOT_AVAILABLE"

    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        headers=auth(owner_token),
        json={"answer": "42", "message": "확인 부탁드립니다."},
    )
    assert claim.status_code == 200
    room_id = claim.get_json()["data"]["chatRoomId"]
    assert room_id is not None

    for token in (owner_token, finder_token):
        room = client.get(f"/api/v1/chats/{room_id}", headers=auth(token))
        assert room.status_code == 200
        assert {member["nickname"] for member in room.get_json()["data"]["members"]} == {
            "분실자",
            "습득자",
        }

    signup(client, "chat-outsider@example.com", "제삼자")
    outsider_token = login(client, "chat-outsider@example.com")
    forbidden = client.get(f"/api/v1/chats/{room_id}", headers=auth(outsider_token))
    assert forbidden.status_code == 404
    outsider_socket = socketio.test_client(app, auth={"token": outsider_token})
    denied_join = outsider_socket.emit("join_chat", {"roomId": room_id}, callback=True)
    assert denied_join["success"] is False
    assert denied_join["error"]["code"] == "CHAT_ROOM_NOT_FOUND"
    outsider_socket.disconnect()


def test_socket_chat_persists_messages_and_read_state(app, client):
    owner_token, finder_token, _, _, match = _create_match(client)
    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        headers=auth(owner_token),
        json={"answer": "42"},
    ).get_json()["data"]
    room_id = claim["chatRoomId"]

    invalid_socket = socketio.test_client(app, auth={"token": "invalid"})
    assert not invalid_socket.is_connected()

    owner_socket = socketio.test_client(app, auth={"token": owner_token})
    finder_socket = socketio.test_client(app, auth={"token": f"Bearer {finder_token}"})
    assert owner_socket.is_connected()
    assert finder_socket.is_connected()

    owner_join = owner_socket.emit("join_chat", {"roomId": room_id}, callback=True)
    finder_join = finder_socket.emit("join_chat", {"roomId": room_id}, callback=True)
    assert owner_join["success"] is True
    assert finder_join["success"] is True
    owner_socket.get_received()
    finder_socket.get_received()

    sent = owner_socket.emit(
        "send_message",
        {
            "roomId": room_id,
            "content": "학생증 뒷면에 숫자 42가 있습니다.",
            "clientMessageId": "mobile-001",
        },
        callback=True,
    )
    assert sent["success"] is True
    assert sent["created"] is True
    message_id = sent["data"]["id"]

    received = finder_socket.get_received()
    new_messages = [item for item in received if item["name"] == "new_message"]
    assert len(new_messages) == 1
    assert new_messages[0]["args"][0]["content"] == "학생증 뒷면에 숫자 42가 있습니다."

    duplicate = owner_socket.emit(
        "send_message",
        {
            "roomId": room_id,
            "content": "재전송된 메시지",
            "clientMessageId": "mobile-001",
        },
        callback=True,
    )
    assert duplicate["success"] is True
    assert duplicate["created"] is False
    assert duplicate["data"]["id"] == message_id
    assert not [
        item for item in finder_socket.get_received() if item["name"] == "new_message"
    ]

    history = client.get(
        f"/api/v1/chats/{room_id}/messages", headers=auth(finder_token)
    ).get_json()["data"]
    assert [item["id"] for item in history["items"]] == [message_id]

    room_before_read = client.get(
        f"/api/v1/chats/{room_id}", headers=auth(finder_token)
    ).get_json()["data"]
    assert room_before_read["unreadCount"] == 1

    read = finder_socket.emit(
        "mark_read", {"roomId": room_id, "messageId": message_id}, callback=True
    )
    assert read["success"] is True
    room_after_read = client.get(
        f"/api/v1/chats/{room_id}", headers=auth(finder_token)
    ).get_json()["data"]
    assert room_after_read["unreadCount"] == 0

    rejected = client.patch(
        f"/api/v1/matches/{match['id']}/reject",
        headers=auth(owner_token),
        json={"reason": "추가 특징이 다릅니다."},
    )
    assert rejected.status_code == 200
    closed = owner_socket.emit(
        "send_message",
        {"roomId": room_id, "content": "종료 후 메시지"},
        callback=True,
    )
    assert closed["success"] is False
    assert closed["error"]["code"] == "CHAT_CLOSED"
    preserved = client.get(
        f"/api/v1/chats/{room_id}/messages", headers=auth(owner_token)
    ).get_json()["data"]["items"]
    assert [item["id"] for item in preserved] == [message_id]

    owner_socket.disconnect()
    finder_socket.disconnect()
