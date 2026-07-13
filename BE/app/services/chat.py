from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..errors import ApiError
from ..extensions import db
from ..models import ChatMessage, ChatRoom, ChatRoomMember, Match, utcnow

CHAT_ENABLED_STATUSES = {"CLAIM_REQUESTED", "VERIFIED", "HANDED_OVER"}
CHAT_WRITABLE_STATUSES = {"CLAIM_REQUESTED", "VERIFIED"}


def match_participant_ids(match: Match) -> set[int]:
    return {match.lost_post.user_id, match.found_post.user_id}


def require_match_participant(match: Match, user_id: int):
    if user_id not in match_participant_ids(match):
        raise ApiError("FORBIDDEN", "채팅 참여 권한이 없습니다.", 403)


def ensure_chat_room(match: Match, user_id: int | None = None) -> tuple[ChatRoom, bool]:
    if user_id is not None:
        require_match_participant(match, user_id)
    if match.status not in CHAT_ENABLED_STATUSES:
        raise ApiError(
            "CHAT_NOT_AVAILABLE",
            "수령 요청 후 채팅을 시작할 수 있습니다.",
            409,
        )
    if match.chat_room:
        return match.chat_room, False

    room = ChatRoom(match=match)
    room.members = [
        ChatRoomMember(user_id=participant_id)
        for participant_id in sorted(match_participant_ids(match))
    ]
    db.session.add(room)
    db.session.flush()
    return room, True


def get_room_for_user(room_id: int, user_id: int) -> ChatRoom:
    room = db.session.scalar(
        db.select(ChatRoom)
        .join(ChatRoomMember)
        .where(ChatRoom.id == room_id, ChatRoomMember.user_id == user_id)
    )
    if not room:
        raise ApiError("CHAT_ROOM_NOT_FOUND", "채팅방을 찾을 수 없습니다.", 404)
    return room


def get_member(room: ChatRoom, user_id: int) -> ChatRoomMember:
    member = next((item for item in room.members if item.user_id == user_id), None)
    if not member:
        raise ApiError("FORBIDDEN", "채팅 참여 권한이 없습니다.", 403)
    return member


def room_to_dict(room: ChatRoom, user_id: int) -> dict:
    member = get_member(room, user_id)
    latest = db.session.scalar(
        db.select(ChatMessage)
        .where(ChatMessage.room_id == room.id)
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )
    unread_conditions = [
        ChatMessage.room_id == room.id,
        ChatMessage.sender_id != user_id,
    ]
    if member.last_read_message_id:
        unread_conditions.append(ChatMessage.id > member.last_read_message_id)
    unread_count = db.session.scalar(
        db.select(func.count(ChatMessage.id)).where(*unread_conditions)
    )
    return {
        "id": room.id,
        "matchId": room.match_id,
        "matchStatus": room.match.status,
        "members": [
            {
                "id": item.user.id,
                "nickname": item.user.nickname,
                "profileImageUrl": item.user.profile_image_url,
            }
            for item in room.members
        ],
        "lastMessage": latest.to_dict() if latest else None,
        "unreadCount": unread_count or 0,
        "createdAt": room.created_at.isoformat(),
        "updatedAt": room.updated_at.isoformat(),
    }


def create_message(
    room: ChatRoom,
    user_id: int,
    content,
    client_message_id=None,
) -> tuple[ChatMessage, bool]:
    get_member(room, user_id)
    if room.match.status not in CHAT_WRITABLE_STATUSES:
        raise ApiError("CHAT_CLOSED", "종료된 채팅방에는 메시지를 보낼 수 없습니다.", 409)

    normalized_content = str(content or "").strip()
    if not normalized_content or len(normalized_content) > 1000:
        raise ApiError("INVALID_MESSAGE", "메시지는 1~1000자로 입력해 주세요.", 422)

    normalized_client_id = str(client_message_id or "").strip() or None
    if normalized_client_id and len(normalized_client_id) > 64:
        raise ApiError("INVALID_CLIENT_MESSAGE_ID", "clientMessageId는 64자 이하여야 합니다.", 422)
    if normalized_client_id:
        existing = db.session.scalar(
            db.select(ChatMessage).where(
                ChatMessage.room_id == room.id,
                ChatMessage.sender_id == user_id,
                ChatMessage.client_message_id == normalized_client_id,
            )
        )
        if existing:
            return existing, False

    message = ChatMessage(
        room_id=room.id,
        sender_id=user_id,
        content=normalized_content,
        client_message_id=normalized_client_id,
    )
    room_id = room.id
    room.updated_at = utcnow()
    db.session.add(message)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if normalized_client_id:
            existing = db.session.scalar(
                db.select(ChatMessage).where(
                    ChatMessage.room_id == room_id,
                    ChatMessage.sender_id == user_id,
                    ChatMessage.client_message_id == normalized_client_id,
                )
            )
            if existing:
                return existing, False
        raise
    return message, True


def mark_room_read(room: ChatRoom, user_id: int, message_id: int) -> ChatRoomMember:
    member = get_member(room, user_id)
    message = db.session.scalar(
        db.select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.room_id == room.id,
        )
    )
    if not message:
        raise ApiError("MESSAGE_NOT_FOUND", "메시지를 찾을 수 없습니다.", 404)
    if member.last_read_message_id is None or message.id > member.last_read_message_id:
        member.last_read_message_id = message.id
        member.last_read_at = message.created_at
        db.session.commit()
    return member
