import re

from flask import Blueprint
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..errors import ApiError
from ..extensions import db
from ..models import User
from ..utils import body, require_fields, success

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.post("/signup")
def signup():
    payload = body()
    require_fields(payload, ["email", "password", "nickname", "siteCode"])
    email = payload["email"].strip().lower()
    password = payload["password"]
    nickname = payload["nickname"].strip()
    site_code = payload["siteCode"].strip().upper()

    details = []
    if not EMAIL_RE.match(email):
        details.append({"field": "email", "reason": "유효한 이메일이 아닙니다."})
    if len(password) < 8 or len(password) > 64:
        details.append({"field": "password", "reason": "8~64자로 입력해 주세요."})
    if not 2 <= len(nickname) <= 20:
        details.append({"field": "nickname", "reason": "2~20자로 입력해 주세요."})
    if not site_code or len(site_code) > 50:
        details.append({"field": "siteCode", "reason": "시설 코드를 확인해 주세요."})
    if details:
        raise ApiError("VALIDATION_FAILED", "입력값을 확인해 주세요.", 422, details)
    if db.session.scalar(db.select(User).where(User.email == email)):
        raise ApiError("EMAIL_ALREADY_EXISTS", "이미 가입된 이메일입니다.", 409)

    user = User(
        email=email,
        password_hash=generate_password_hash(password),
        nickname=nickname,
        site_code=site_code,
    )
    db.session.add(user)
    db.session.commit()
    return success({"user": user.public_dict()}, 201)


@bp.post("/login")
def login():
    payload = body()
    require_fields(payload, ["email", "password"])
    email = payload["email"].strip().lower()
    user = db.session.scalar(db.select(User).where(User.email == email))
    if (
        not user
        or not user.is_active
        or not check_password_hash(user.password_hash, payload["password"])
    ):
        raise ApiError("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 다릅니다.", 401)

    device = payload.get("device") or {}
    if device.get("platform") in {"ANDROID", "IOS"}:
        user.platform = device["platform"]
    if device.get("pushToken"):
        user.push_token = device["pushToken"]
    db.session.commit()

    identity = str(user.id)
    return success(
        {
            "accessToken": create_access_token(identity=identity),
            "refreshToken": create_refresh_token(identity=identity),
            "user": user.public_dict(),
        }
    )


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    user = db.session.get(User, int(identity))
    if not user or not user.is_active:
        raise ApiError("UNAUTHORIZED", "유효하지 않은 사용자입니다.", 401)
    return success({"accessToken": create_access_token(identity=identity)})
