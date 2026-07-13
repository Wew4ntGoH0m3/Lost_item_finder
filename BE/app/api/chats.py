from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import ChatMessage, ChatRoom, ChatRoomMember, Match
from ..services.chat import (
    ensure_chat_room,
    get_room_for_user,
    mark_room_read,
    room_to_dict,
)
from ..utils import body, current_user, require_fields, success

bp = Blueprint("chats", __name__)


@bp.get("")
@jwt_required()
def list_chat_rooms():
    user = current_user()
    rooms = list(
        db.session.scalars(
            db.select(ChatRoom)
            .join(ChatRoomMember)
            .where(ChatRoomMember.user_id == user.id)
            .order_by(ChatRoom.updated_at.desc())
        )
    )
    return success({"items": [room_to_dict(room, user.id) for room in rooms]})


@bp.post("/matches/<int:match_id>")
@jwt_required()
def open_chat_room(match_id):
    user = current_user()
    match = db.session.get(Match, match_id)
    if not match:
        raise ApiError("MATCH_NOT_FOUND", "매칭 결과를 찾을 수 없습니다.", 404)
    room, created = ensure_chat_room(match, user.id)
    db.session.commit()
    return success(room_to_dict(room, user.id), 201 if created else 200)


@bp.get("/<int:room_id>")
@jwt_required()
def get_chat_room(room_id):
    user = current_user()
    room = get_room_for_user(room_id, user.id)
    return success(room_to_dict(room, user.id))


@bp.get("/<int:room_id>/messages")
@jwt_required()
def list_messages(room_id):
    user = current_user()
    room = get_room_for_user(room_id, user.id)
    try:
        limit = min(100, max(1, int(request.args.get("limit", "50"))))
        before_id = request.args.get("beforeId")
        before_id = int(before_id) if before_id else None
    except ValueError as exc:
        raise ApiError("VALIDATION_FAILED", "beforeId와 limit은 정수여야 합니다.", 422) from exc

    query = db.select(ChatMessage).where(ChatMessage.room_id == room.id)
    if before_id is not None:
        query = query.where(ChatMessage.id < before_id)
    rows = list(db.session.scalars(query.order_by(ChatMessage.id.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()
    return success(
        {
            "items": [message.to_dict() for message in rows],
            "hasMore": has_more,
            "nextBeforeId": rows[0].id if has_more and rows else None,
        }
    )


@bp.patch("/<int:room_id>/read")
@jwt_required()
def read_messages(room_id):
    user = current_user()
    payload = body()
    require_fields(payload, ["messageId"])
    room = get_room_for_user(room_id, user.id)
    try:
        message_id = int(payload["messageId"])
    except (TypeError, ValueError) as exc:
        raise ApiError("VALIDATION_FAILED", "messageId는 정수여야 합니다.", 422) from exc
    member = mark_room_read(room, user.id, message_id)
    return success(
        {
            "roomId": room.id,
            "messageId": message_id,
            "lastReadMessageId": member.last_read_message_id,
            "lastReadAt": member.last_read_at.isoformat(),
        }
    )
