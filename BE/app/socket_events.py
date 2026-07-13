from flask import session
from flask_jwt_extended import decode_token
from flask_socketio import emit, join_room, leave_room

from .errors import ApiError
from .extensions import db, socketio
from .models import User
from .services.chat import create_message, get_room_for_user, mark_room_read


def _channel(room_id: int) -> str:
    return f"chat:{room_id}"


def _error(error: ApiError) -> dict:
    return {
        "success": False,
        "error": {"code": error.code, "message": error.message},
    }


def _socket_user() -> User:
    user_id = session.get("socket_user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise ApiError("UNAUTHORIZED", "유효하지 않은 사용자입니다.", 401)
    return user


def _room_id(data) -> int:
    try:
        return int((data or {}).get("roomId"))
    except (TypeError, ValueError) as exc:
        raise ApiError("VALIDATION_FAILED", "roomId는 정수여야 합니다.", 422) from exc


def register_socket_events():
    def connect(auth):
        token = str((auth or {}).get("token", "")).strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        try:
            decoded = decode_token(token)
            if decoded.get("type") != "access":
                return False
            user = db.session.get(User, int(decoded["sub"]))
        except (KeyError, TypeError, ValueError):
            return False
        except Exception:
            return False
        if not user or not user.is_active:
            return False
        session["socket_user_id"] = user.id
        emit("connected", {"userId": user.id})
        return True

    def join_chat(data):
        try:
            user = _socket_user()
            room = get_room_for_user(_room_id(data), user.id)
            join_room(_channel(room.id))
            return {"success": True, "data": {"roomId": room.id}}
        except ApiError as error:
            return _error(error)

    def leave_chat(data):
        try:
            user = _socket_user()
            room = get_room_for_user(_room_id(data), user.id)
            leave_room(_channel(room.id))
            return {"success": True, "data": {"roomId": room.id}}
        except ApiError as error:
            return _error(error)

    def send_message(data):
        try:
            user = _socket_user()
            room = get_room_for_user(_room_id(data), user.id)
            message, created = create_message(
                room,
                user.id,
                (data or {}).get("content"),
                (data or {}).get("clientMessageId"),
            )
            payload = message.to_dict()
            if created:
                emit("new_message", payload, to=_channel(room.id))
            return {"success": True, "data": payload, "created": created}
        except ApiError as error:
            return _error(error)

    def typing(data):
        try:
            user = _socket_user()
            room = get_room_for_user(_room_id(data), user.id)
            emit(
                "typing",
                {
                    "roomId": room.id,
                    "userId": user.id,
                    "isTyping": bool((data or {}).get("isTyping")),
                },
                to=_channel(room.id),
                include_self=False,
            )
            return {"success": True}
        except ApiError as error:
            return _error(error)

    def mark_read(data):
        try:
            user = _socket_user()
            room = get_room_for_user(_room_id(data), user.id)
            try:
                message_id = int((data or {}).get("messageId"))
            except (TypeError, ValueError) as exc:
                raise ApiError(
                    "VALIDATION_FAILED", "messageId는 정수여야 합니다.", 422
                ) from exc
            member = mark_room_read(room, user.id, message_id)
            payload = {
                "roomId": room.id,
                "userId": user.id,
                "messageId": message_id,
                "lastReadMessageId": member.last_read_message_id,
                "lastReadAt": member.last_read_at.isoformat(),
            }
            emit("messages_read", payload, to=_channel(room.id))
            return {"success": True, "data": payload}
        except ApiError as error:
            return _error(error)

    socketio.on_event("connect", connect)
    socketio.on_event("join_chat", join_chat)
    socketio.on_event("leave_chat", leave_chat)
    socketio.on_event("send_message", send_message)
    socketio.on_event("typing", typing)
    socketio.on_event("mark_read", mark_read)
