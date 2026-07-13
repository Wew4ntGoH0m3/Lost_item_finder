from flask import Blueprint
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..utils import body, current_user, success

bp = Blueprint("users", __name__)


@bp.get("/me")
@jwt_required()
def me():
    return success(current_user().public_dict())


@bp.patch("/me")
@jwt_required()
def update_me():
    user = current_user()
    payload = body()
    if "nickname" in payload:
        nickname = str(payload["nickname"]).strip()
        if not 2 <= len(nickname) <= 20:
            raise ApiError("VALIDATION_FAILED", "닉네임은 2~20자여야 합니다.", 422)
        user.nickname = nickname
    if "profileImageUrl" in payload:
        user.profile_image_url = payload["profileImageUrl"] or None
    db.session.commit()
    return success(user.public_dict())


@bp.patch("/me/push-token")
@jwt_required()
def update_push_token():
    user = current_user()
    payload = body()
    platform = payload.get("platform")
    if platform not in {"ANDROID", "IOS"}:
        raise ApiError("VALIDATION_FAILED", "platform은 ANDROID 또는 IOS입니다.", 422)
    token = str(payload.get("pushToken", "")).strip()
    if not token:
        raise ApiError("VALIDATION_FAILED", "pushToken이 필요합니다.", 422)
    user.platform = platform
    user.push_token = token
    db.session.commit()
    return success({"platform": platform, "registered": True})
