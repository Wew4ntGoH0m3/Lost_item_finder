from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import LostPost
from ..utils import (
    body,
    current_user,
    is_owner,
    page_args,
    parse_category,
    parse_datetime,
    require_fields,
    success,
)

bp = Blueprint("lost_posts", __name__)
REQUIRED = [
    "title",
    "category",
    "color",
    "location",
    "lostAt",
    "features",
]
EDITABLE = {
    "title": "title",
    "color": "color",
    "location": "location",
    "features": "features",
    "privateFeature": "private_feature",
    "description": "description",
    "imageUrl": "image_url",
    "contactMethod": "contact_method",
}


@bp.post("")
@jwt_required()
def create_lost_post():
    user = current_user()
    payload = body()
    require_fields(payload, REQUIRED)
    post = LostPost(
        user_id=user.id,
        title=str(payload["title"]).strip(),
        category=parse_category(payload["category"]),
        color=str(payload["color"]).strip().upper(),
        location=str(payload["location"]).strip(),
        lost_at=parse_datetime(payload["lostAt"], "lostAt"),
        features=str(payload["features"]).strip(),
        private_feature=payload.get("privateFeature") or None,
        description=payload.get("description") or None,
        image_url=payload.get("imageUrl") or None,
        contact_method=payload.get("contactMethod", "NOTIFICATION"),
    )
    db.session.add(post)
    db.session.commit()

    from ..tasks import analyze_lost_post_task

    analyze_lost_post_task.delay(post.id)
    return success({"post": post.to_dict(include_private=True), "analysisQueued": True}, 201)


@bp.get("")
def list_lost_posts():
    page, size = page_args()
    statement = db.select(LostPost)
    for param, column in {
        "location": LostPost.location,
        "status": LostPost.status,
    }.items():
        value = request.args.get(param)
        if value:
            normalized = value if param == "location" else value.upper()
            statement = statement.where(column == normalized)
    category = request.args.get("category")
    if category:
        statement = statement.where(LostPost.category == parse_category(category))
    statement = statement.order_by(LostPost.created_at.desc())
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
def get_lost_post(post_id):
    user = current_user(optional=True)
    post = db.session.get(LostPost, post_id)
    if not post:
        raise ApiError("LOST_POST_NOT_FOUND", "분실글을 찾을 수 없습니다.", 404)
    include_private = bool(user and is_owner(user, post.user_id))
    return success(post.to_dict(include_private=include_private))


@bp.patch("/<int:post_id>")
@jwt_required()
def update_lost_post(post_id):
    user = current_user()
    post = db.session.get(LostPost, post_id)
    if not post:
        raise ApiError("LOST_POST_NOT_FOUND", "분실글을 찾을 수 없습니다.", 404)
    if not is_owner(user, post.user_id):
        raise ApiError("FORBIDDEN", "게시글 수정 권한이 없습니다.", 403)
    payload = body()
    needs_analysis = False
    for source, target in EDITABLE.items():
        if source in payload:
            setattr(post, target, payload[source] or None)
            needs_analysis = needs_analysis or source != "contactMethod"
    if "category" in payload:
        post.category = parse_category(payload["category"])
        needs_analysis = True
    if "lostAt" in payload:
        post.lost_at = parse_datetime(payload["lostAt"], "lostAt")
        needs_analysis = True
    if "status" in payload:
        status = str(payload["status"]).upper()
        if status not in {"OPEN", "CLOSED"}:
            raise ApiError("INVALID_STATUS_TRANSITION", "허용되지 않은 상태입니다.", 409)
        post.status = status
    db.session.commit()
    if needs_analysis and post.status == "OPEN":
        from ..tasks import analyze_lost_post_task

        analyze_lost_post_task.delay(post.id)
    return success({"post": post.to_dict(include_private=True), "analysisQueued": needs_analysis})


@bp.delete("/<int:post_id>")
@jwt_required()
def delete_lost_post(post_id):
    user = current_user()
    post = db.session.get(LostPost, post_id)
    if not post:
        raise ApiError("LOST_POST_NOT_FOUND", "분실글을 찾을 수 없습니다.", 404)
    if not is_owner(user, post.user_id):
        raise ApiError("FORBIDDEN", "게시글 삭제 권한이 없습니다.", 403)
    if post.status == "MATCHED":
        raise ApiError("INVALID_STATUS_TRANSITION", "매칭 처리 중인 글은 삭제할 수 없습니다.", 409)
    db.session.delete(post)
    db.session.commit()
    return "", 204


@bp.post("/<int:post_id>/matches/analyze")
@jwt_required()
def reanalyze(post_id):
    user = current_user()
    post = db.session.get(LostPost, post_id)
    if not post:
        raise ApiError("LOST_POST_NOT_FOUND", "분실글을 찾을 수 없습니다.", 404)
    if not is_owner(user, post.user_id):
        raise ApiError("FORBIDDEN", "분석 요청 권한이 없습니다.", 403)
    if post.status != "OPEN":
        raise ApiError("INVALID_STATUS_TRANSITION", "OPEN 상태만 분석할 수 있습니다.", 409)
    from ..tasks import analyze_lost_post_task

    task = analyze_lost_post_task.delay(post.id)
    return success({"jobId": task.id, "status": "QUEUED"}, 202)
