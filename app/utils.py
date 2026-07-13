from datetime import datetime, timezone

from flask import jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from .errors import ApiError
from .extensions import db
from .models import User


def success(data=None, status=200):
    return jsonify({"success": True, "data": data, "error": None}), status


def body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("VALIDATION_FAILED", "JSON 요청 본문이 필요합니다.", 400)
    return payload


def require_fields(payload: dict, fields: list[str]):
    missing = [name for name in fields if payload.get(name) in (None, "")]
    if missing:
        raise ApiError(
            "VALIDATION_FAILED",
            "필수 입력값을 확인해 주세요.",
            422,
            [{"field": name, "reason": "필수 항목입니다."} for name in missing],
        )


def parse_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ApiError(
            "VALIDATION_FAILED",
            f"{field}는 ISO 8601 날짜 형식이어야 합니다.",
            422,
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def current_user(optional: bool = False) -> User | None:
    verify_jwt_in_request(optional=optional)
    identity = get_jwt_identity()
    if identity is None:
        return None
    user = db.session.get(User, int(identity))
    if not user or not user.is_active:
        raise ApiError("UNAUTHORIZED", "유효하지 않은 사용자입니다.", 401)
    return user


def is_owner_or_admin(user: User, owner_id: int) -> bool:
    return user.role == "ADMIN" or user.id == owner_id


def page_args():
    try:
        page = max(1, int(request.args.get("page", "1")))
        size = min(100, max(1, int(request.args.get("size", "20"))))
    except ValueError as exc:
        raise ApiError("VALIDATION_FAILED", "page와 size는 정수여야 합니다.", 422) from exc
    return page, size
