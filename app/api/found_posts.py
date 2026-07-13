from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import FoundPost
from ..utils import (
    body,
    current_user,
    is_owner_or_admin,
    page_args,
    parse_datetime,
    require_fields,
    success,
)

bp = Blueprint("found_posts", __name__)
REQUIRED = [
    "siteCode",
    "title",
    "category",
    "color",
    "location",
    "foundAt",
    "storageLocation",
    "features",
]
EDITABLE = {
    "title": "title",
    "category": "category",
    "color": "color",
    "location": "location",
    "storageLocation": "storage_location",
    "features": "features",
    "privateFeature": "private_feature",
    "verificationQuestion": "verification_question",
    "description": "description",
    "imageUrl": "image_url",
}


@bp.post("")
@jwt_required()
def create_found_post():
    user = current_user()
    payload = body()
    require_fields(payload, REQUIRED)
    site_code = str(payload["siteCode"]).strip().upper()
    if user.role != "ADMIN" and site_code != user.site_code:
        raise ApiError("FORBIDDEN", "소속 시설에만 게시글을 등록할 수 있습니다.", 403)
    post = FoundPost(
        user_id=user.id,
        site_code=site_code,
        title=str(payload["title"]).strip(),
        category=str(payload["category"]).strip().upper(),
        color=str(payload["color"]).strip().upper(),
        location=str(payload["location"]).strip(),
        found_at=parse_datetime(payload["foundAt"], "foundAt"),
        storage_location=str(payload["storageLocation"]).strip(),
        features=str(payload["features"]).strip(),
        private_feature=payload.get("privateFeature") or None,
        verification_question=payload.get("verificationQuestion") or None,
        description=payload.get("description") or None,
        image_url=payload.get("imageUrl") or None,
    )
    db.session.add(post)
    db.session.commit()

    from ..tasks import analyze_found_post_task

    analyze_found_post_task.delay(post.id)
    return success({"post": post.to_dict(include_private=True), "analysisQueued": True}, 201)


@bp.get("")
def list_found_posts():
    user = current_user(optional=True)
    page, size = page_args()
    statement = db.select(FoundPost)
    requested_status = request.args.get("status")
    if user and user.role == "ADMIN" and requested_status:
        statement = statement.where(FoundPost.status == requested_status.upper())
    else:
        statement = statement.where(FoundPost.status == "STORED")
    for param, column in {
        "siteCode": FoundPost.site_code,
        "category": FoundPost.category,
        "location": FoundPost.location,
    }.items():
        value = request.args.get(param)
        if value:
            normalized = value if param == "location" else value.upper()
            statement = statement.where(column == normalized)
    statement = statement.order_by(FoundPost.created_at.desc())
    pagination = db.paginate(statement, page=page, per_page=size, error_out=False)
    return success(
        {
            "items": [item.to_dict() for item in pagination.items],
            "page": {
                "number": page,
                "size": size,
                "total": pagination.total,
                "pages": pagination.pages,
            },
        }
    )


@bp.get("/<int:post_id>")
def get_found_post(post_id):
    user = current_user(optional=True)
    post = db.session.get(FoundPost, post_id)
    if not post:
        raise ApiError("FOUND_POST_NOT_FOUND", "습득글을 찾을 수 없습니다.", 404)
    include_private = bool(user and is_owner_or_admin(user, post.user_id))
    return success(post.to_dict(include_private=include_private))


@bp.patch("/<int:post_id>")
@jwt_required()
def update_found_post(post_id):
    user = current_user()
    post = db.session.get(FoundPost, post_id)
    if not post:
        raise ApiError("FOUND_POST_NOT_FOUND", "습득글을 찾을 수 없습니다.", 404)
    if not is_owner_or_admin(user, post.user_id):
        raise ApiError("FORBIDDEN", "게시글 수정 권한이 없습니다.", 403)
    payload = body()
    needs_analysis = False
    for source, target in EDITABLE.items():
        if source in payload:
            setattr(post, target, payload[source] or None)
            needs_analysis = True
    if "foundAt" in payload:
        post.found_at = parse_datetime(payload["foundAt"], "foundAt")
        needs_analysis = True
    if "status" in payload:
        allowed = {"STORED", "CLOSED"}
        if user.role != "ADMIN" or payload["status"] not in allowed:
            raise ApiError("INVALID_STATUS_TRANSITION", "허용되지 않은 상태입니다.", 409)
        post.status = payload["status"]
    db.session.commit()
    if needs_analysis and post.status == "STORED":
        from ..tasks import analyze_found_post_task

        analyze_found_post_task.delay(post.id)
    return success({"post": post.to_dict(include_private=True), "analysisQueued": needs_analysis})


@bp.delete("/<int:post_id>")
@jwt_required()
def delete_found_post(post_id):
    user = current_user()
    post = db.session.get(FoundPost, post_id)
    if not post:
        raise ApiError("FOUND_POST_NOT_FOUND", "습득글을 찾을 수 없습니다.", 404)
    if not is_owner_or_admin(user, post.user_id):
        raise ApiError("FORBIDDEN", "게시글 삭제 권한이 없습니다.", 403)
    if post.status in {"CLAIMED", "RETURNED"}:
        raise ApiError(
            "INVALID_STATUS_TRANSITION",
            "처리 중이거나 반환된 글은 삭제할 수 없습니다.",
            409,
        )
    db.session.delete(post)
    db.session.commit()
    return "", 204
