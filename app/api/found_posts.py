from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import FoundPost
from ..services.found_content import (
    build_found_content_facts,
    generate_found_post_content,
)
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

bp = Blueprint("found_posts", __name__)
REQUIRED = [
    "category",
    "color",
    "location",
    "foundAt",
    "storageLocation",
]
EDITABLE = {
    "storageLocation": "storage_location",
    "privateFeature": "private_feature",
    "verificationQuestion": "verification_question",
    "imageUrl": "image_url",
}
SOURCE_FIELDS = {"category", "color", "location", "foundAt", "observations"}
MANUAL_CONTENT_FIELDS = {"title", "features", "description"}


def _observations(payload: dict, legacy_fallback: bool = False) -> str:
    value = payload.get("observations")
    if value is None and legacy_fallback:
        value = payload.get("features")
    normalized = str(value or "").strip()
    if len(normalized) > 1000:
        raise ApiError(
            "VALIDATION_FAILED",
            "observations는 1000자 이하여야 합니다.",
            422,
            [{"field": "observations", "reason": "1000자 이하여야 합니다."}],
        )
    return normalized


def _generation_metadata(generator: str, facts: dict[str, str]) -> dict:
    return {"generator": generator, "sourceFields": list(facts)}


@bp.post("")
@jwt_required()
def create_found_post():
    user = current_user()
    payload = body()
    require_fields(payload, REQUIRED)
    category = parse_category(payload["category"])
    color = str(payload["color"]).strip().upper()
    location = str(payload["location"]).strip()
    found_at = parse_datetime(payload["foundAt"], "foundAt")
    observations = _observations(payload, legacy_fallback=True)
    facts = build_found_content_facts(
        category,
        color,
        location,
        found_at,
        observations,
    )
    content, generator = generate_found_post_content(facts)
    post = FoundPost(
        user_id=user.id,
        title=content["title"],
        category=category,
        color=color,
        location=location,
        found_at=found_at,
        storage_location=str(payload["storageLocation"]).strip(),
        features=content["features"],
        source_observations=observations,
        content_generator=generator,
        private_feature=payload.get("privateFeature") or None,
        verification_question=payload.get("verificationQuestion") or None,
        description=content["description"] or None,
        image_url=payload.get("imageUrl") or None,
    )
    db.session.add(post)
    db.session.commit()

    from ..tasks import analyze_found_post_task

    analyze_found_post_task.delay(post.id)
    return success(
        {
            "post": post.to_dict(include_private=True),
            "contentGeneration": _generation_metadata(generator, facts),
            "analysisQueued": True,
        },
        201,
    )


@bp.get("")
def list_found_posts():
    page, size = page_args()
    statement = db.select(FoundPost).where(FoundPost.status == "STORED")
    location = request.args.get("location")
    if location:
        statement = statement.where(FoundPost.location == location)
    category = request.args.get("category")
    if category:
        statement = statement.where(FoundPost.category == parse_category(category))
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
    include_private = bool(user and is_owner(user, post.user_id))
    return success(post.to_dict(include_private=include_private))


@bp.patch("/<int:post_id>")
@jwt_required()
def update_found_post(post_id):
    user = current_user()
    post = db.session.get(FoundPost, post_id)
    if not post:
        raise ApiError("FOUND_POST_NOT_FOUND", "습득글을 찾을 수 없습니다.", 404)
    if not is_owner(user, post.user_id):
        raise ApiError("FORBIDDEN", "게시글 수정 권한이 없습니다.", 403)
    payload = body()
    manual_fields = sorted(MANUAL_CONTENT_FIELDS.intersection(payload))
    if manual_fields:
        raise ApiError(
            "VALIDATION_FAILED",
            "습득글 내용은 입력 정보로 자동 생성됩니다.",
            422,
            [
                {"field": field, "reason": "직접 수정할 수 없는 자동 생성 항목입니다."}
                for field in manual_fields
            ],
        )
    for source, target in EDITABLE.items():
        if source in payload:
            setattr(post, target, payload[source] or None)
    regenerate_content = bool(SOURCE_FIELDS.intersection(payload))
    if "category" in payload:
        post.category = parse_category(payload["category"])
    if "color" in payload:
        post.color = str(payload["color"]).strip().upper()
    if "location" in payload:
        post.location = str(payload["location"]).strip()
    if "foundAt" in payload:
        post.found_at = parse_datetime(payload["foundAt"], "foundAt")
    if "observations" in payload:
        post.source_observations = _observations(payload)

    generation = None
    if regenerate_content:
        facts = build_found_content_facts(
            post.category,
            post.color,
            post.location,
            post.found_at,
            post.source_observations,
        )
        content, generator = generate_found_post_content(facts)
        post.title = content["title"]
        post.features = content["features"]
        post.description = content["description"] or None
        post.content_generator = generator
        generation = _generation_metadata(generator, facts)
    if "status" in payload:
        allowed = {"STORED", "CLOSED"}
        status = str(payload["status"]).upper()
        if status not in allowed:
            raise ApiError("INVALID_STATUS_TRANSITION", "허용되지 않은 상태입니다.", 409)
        post.status = status
    db.session.commit()
    if regenerate_content and post.status == "STORED":
        from ..tasks import analyze_found_post_task

        analyze_found_post_task.delay(post.id)
    response = {
        "post": post.to_dict(include_private=True),
        "analysisQueued": regenerate_content,
    }
    if generation:
        response["contentGeneration"] = generation
    return success(response)


@bp.delete("/<int:post_id>")
@jwt_required()
def delete_found_post(post_id):
    user = current_user()
    post = db.session.get(FoundPost, post_id)
    if not post:
        raise ApiError("FOUND_POST_NOT_FOUND", "습득글을 찾을 수 없습니다.", 404)
    if not is_owner(user, post.user_id):
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
