from conftest import auth, login, signup

from app.extensions import socketio


def _create_match(client):
    signup(client, "chat-user-a@example.com", "사용자A")
    signup(client, "chat-user-b@example.com", "사용자B")
    user_a_token = login(client, "chat-user-a@example.com")
    user_b_token = login(client, "chat-user-b@example.com")

    found = client.post(
        "/api/v1/found-posts",
        headers=auth(user_b_token),
        json={
            "category": "CARD",
            "color": "BLUE",
            "location": "체육관 입구",
            "foundAt": "2026-07-13T14:20:00Z",
            "storageLocation": "학생회실",
            "observations": "파란 학교 로고",
            "verificationQuestion": "학번 끝 두 자리는?",
        },
    ).get_json()["data"]["post"]
    lost = client.post(
        "/api/v1/lost-posts",
        headers=auth(user_a_token),
        json={
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
        f"/api/v1/matches/lost-posts/{lost['id']}", headers=auth(user_a_token)
    ).get_json()["data"]["items"][0]
    return user_a_token, user_b_token, found, lost, match


def test_claim_creates_participant_only_chat_room(app, client):
    user_a_token, user_b_token, _, _, match = _create_match(client)

    before_claim = client.post(f"/api/v1/chats/matches/{match['id']}", headers=auth(user_a_token))
    assert before_claim.status_code == 409
    assert before_claim.get_json()["error"]["code"] == "CHAT_NOT_AVAILABLE"

    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        headers=auth(user_a_token),
        json={"answer": "42", "message": "확인 부탁드립니다."},
    )
    assert claim.status_code == 200
    room_id = claim.get_json()["data"]["chatRoomId"]
    assert room_id is not None

    for token in (user_a_token, user_b_token):
        room = client.get(f"/api/v1/chats/{room_id}", headers=auth(token))
        assert room.status_code == 200
        assert {member["nickname"] for member in room.get_json()["data"]["members"]} == {
            "사용자A",
            "사용자B",
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
    user_a_token, user_b_token, _, _, match = _create_match(client)
    claim = client.post(
        f"/api/v1/matches/{match['id']}/claims",
        headers=auth(user_a_token),
        json={"answer": "42"},
    ).get_json()["data"]
    room_id = claim["chatRoomId"]

    invalid_socket = socketio.test_client(app, auth={"token": "invalid"})
    assert not invalid_socket.is_connected()

    user_a_socket = socketio.test_client(app, auth={"token": user_a_token})
    user_b_socket = socketio.test_client(app, auth={"token": f"Bearer {user_b_token}"})
    assert user_a_socket.is_connected()
    assert user_b_socket.is_connected()

    user_a_join = user_a_socket.emit("join_chat", {"roomId": room_id}, callback=True)
    user_b_join = user_b_socket.emit("join_chat", {"roomId": room_id}, callback=True)
    assert user_a_join["success"] is True
    assert user_b_join["success"] is True
    user_a_socket.get_received()
    user_b_socket.get_received()

    sent = user_a_socket.emit(
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

    received = user_b_socket.get_received()
    new_messages = [item for item in received if item["name"] == "new_message"]
    assert len(new_messages) == 1
    assert new_messages[0]["args"][0]["content"] == "학생증 뒷면에 숫자 42가 있습니다."

    duplicate = user_a_socket.emit(
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
    assert not [item for item in user_b_socket.get_received() if item["name"] == "new_message"]

    history = client.get(
        f"/api/v1/chats/{room_id}/messages", headers=auth(user_b_token)
    ).get_json()["data"]
    assert [item["id"] for item in history["items"]] == [message_id]

    room_before_read = client.get(
        f"/api/v1/chats/{room_id}", headers=auth(user_b_token)
    ).get_json()["data"]
    assert room_before_read["unreadCount"] == 1

    read = user_b_socket.emit(
        "mark_read", {"roomId": room_id, "messageId": message_id}, callback=True
    )
    assert read["success"] is True
    room_after_read = client.get(f"/api/v1/chats/{room_id}", headers=auth(user_b_token)).get_json()[
        "data"
    ]
    assert room_after_read["unreadCount"] == 0

    rejected = client.patch(
        f"/api/v1/matches/{match['id']}/reject",
        headers=auth(user_a_token),
        json={"reason": "추가 특징이 다릅니다."},
    )
    assert rejected.status_code == 200
    closed = user_a_socket.emit(
        "send_message",
        {"roomId": room_id, "content": "종료 후 메시지"},
        callback=True,
    )
    assert closed["success"] is False
    assert closed["error"]["code"] == "CHAT_CLOSED"
    preserved = client.get(
        f"/api/v1/chats/{room_id}/messages", headers=auth(user_a_token)
    ).get_json()["data"]["items"]
    assert [item["id"] for item in preserved] == [message_id]

    user_a_socket.disconnect()
    user_b_socket.disconnect()
