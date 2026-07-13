from flask import Blueprint, request
from flask_jwt_extended import jwt_required

from ..errors import ApiError
from ..extensions import db
from ..models import FoundPost, LostPost, Match, utcnow
from ..services.chat import ensure_chat_room
from ..utils import body, current_user, is_owner, require_fields, success

bp = Blueprint("matches", __name__)


def _get_match_for_update(match_id: int) -> Match:
    match = db.session.scalar(db.select(Match).where(Match.id == match_id).with_for_update())
    if not match:
        raise ApiError("MATCH_NOT_FOUND", "매칭 결과를 찾을 수 없습니다.", 404)
    return match


def _can_access(user, match: Match) -> bool:
    return user.id in {
        match.lost_post.user_id,
        match.found_post.user_id,
    }


@bp.get("")
@jwt_required()
def list_my_matches():
    user = current_user()
    statement = (
        db.select(Match)
        .join(LostPost, Match.lost_post_id == LostPost.id)
        .join(FoundPost, Match.found_post_id == FoundPost.id)
        .where(db.or_(LostPost.user_id == user.id, FoundPost.user_id == user.id))
    )
    status = request.args.get("status")
    if status:
        statement = statement.where(Match.status == status.upper())
    statement = statement.order_by(Match.score.desc(), Match.created_at.desc())
    items = list(db.session.scalars(statement))
    return success({"items": [item.to_dict() for item in items]})


@bp.get("/lost-posts/<int:lost_post_id>")
@jwt_required()
def matches_for_lost(lost_post_id):
    user = current_user()
    post = db.session.get(LostPost, lost_post_id)
    if not post:
        raise ApiError("LOST_POST_NOT_FOUND", "분실글을 찾을 수 없습니다.", 404)
    if not is_owner(user, post.user_id):
        raise ApiError("FORBIDDEN", "매칭 후보 조회 권한이 없습니다.", 403)
    items = list(
        db.session.scalars(
            db.select(Match)
            .where(Match.lost_post_id == post.id, Match.status != "REJECTED")
            .order_by(Match.score.desc(), Match.created_at.desc())
        )
    )
    return success({"items": [item.to_dict() for item in items]})


@bp.get("/found-posts/<int:found_post_id>")
@jwt_required()
def matches_for_found(found_post_id):
    user = current_user()
    post = db.session.get(FoundPost, found_post_id)
    if not post:
        raise ApiError("FOUND_POST_NOT_FOUND", "습득글을 찾을 수 없습니다.", 404)
    if not is_owner(user, post.user_id):
        raise ApiError("FORBIDDEN", "매칭 후보 조회 권한이 없습니다.", 403)
    items = list(
        db.session.scalars(
            db.select(Match)
            .where(Match.found_post_id == post.id, Match.status != "REJECTED")
            .order_by(Match.score.desc(), Match.created_at.desc())
        )
    )
    return success({"items": [item.to_dict() for item in items]})


@bp.get("/<int:match_id>")
@jwt_required()
def get_match(match_id):
    user = current_user()
    match = db.session.get(Match, match_id)
    if not match:
        raise ApiError("MATCH_NOT_FOUND", "매칭 결과를 찾을 수 없습니다.", 404)
    if not _can_access(user, match):
        raise ApiError("FORBIDDEN", "매칭 상세 조회 권한이 없습니다.", 403)
    return success(match.to_dict(include_sensitive=True))


@bp.post("/<int:match_id>/claims")
@jwt_required()
def claim_match(match_id):
    user = current_user()
    payload = body()
    require_fields(payload, ["answer"])
    match = _get_match_for_update(match_id)
    if user.id != match.lost_post.user_id:
        raise ApiError("FORBIDDEN", "분실글 작성자만 수령 요청할 수 있습니다.", 403)
    if match.status != "CANDIDATE" or match.found_post.status != "STORED":
        raise ApiError("INVALID_STATUS_TRANSITION", "현재 수령 요청할 수 없는 상태입니다.", 409)

    match.status = "CLAIM_REQUESTED"
    match.claim_answer = str(payload["answer"]).strip()
    match.claim_message = str(payload.get("message", "")).strip() or None
    match.claimed_at = utcnow()
    match.lost_post.status = "MATCHED"
    match.found_post.status = "CLAIMED"
    ensure_chat_room(match)
    db.session.commit()
    return success(match.to_dict(include_sensitive=True))


@bp.patch("/<int:match_id>/verify")
@jwt_required()
def verify_match(match_id):
    user = current_user()
    match = _get_match_for_update(match_id)
    if user.id != match.found_post.user_id:
        raise ApiError("FORBIDDEN", "습득글 작성자만 확인할 수 있습니다.", 403)
    if match.status != "CLAIM_REQUESTED":
        raise ApiError("INVALID_STATUS_TRANSITION", "확인 요청 상태가 아닙니다.", 409)
    match.status = "VERIFIED"
    match.confirmed_by = user.id
    match.confirmed_at = utcnow()
    db.session.commit()
    return success(match.to_dict(include_sensitive=True))


@bp.patch("/<int:match_id>/reject")
@jwt_required()
def reject_match(match_id):
    user = current_user()
    payload = body()
    match = _get_match_for_update(match_id)
    if not _can_access(user, match):
        raise ApiError("FORBIDDEN", "매칭 거절 권한이 없습니다.", 403)
    if match.status not in {"CANDIDATE", "CLAIM_REQUESTED", "VERIFIED"}:
        raise ApiError("INVALID_STATUS_TRANSITION", "거절할 수 없는 상태입니다.", 409)
    was_claimed = match.status in {"CLAIM_REQUESTED", "VERIFIED"}
    match.status = "REJECTED"
    match.rejection_reason = str(payload.get("reason", "")).strip() or None
    if was_claimed and match.found_post.status == "CLAIMED":
        match.found_post.status = "STORED"
        other_active = db.session.scalar(
            db.select(Match.id).where(
                Match.lost_post_id == match.lost_post_id,
                Match.id != match.id,
                Match.status.in_(["CLAIM_REQUESTED", "VERIFIED"]),
            )
        )
        if not other_active:
            match.lost_post.status = "OPEN"
    db.session.commit()
    return success(match.to_dict())


@bp.patch("/<int:match_id>/handover")
@jwt_required()
def handover_match(match_id):
    user = current_user()
    match = _get_match_for_update(match_id)
    if user.id != match.found_post.user_id:
        raise ApiError("FORBIDDEN", "습득글 작성자만 인계 완료할 수 있습니다.", 403)
    if match.status != "VERIFIED":
        raise ApiError("INVALID_STATUS_TRANSITION", "본인 확인 후 인계할 수 있습니다.", 409)
    match.status = "HANDED_OVER"
    match.handed_over_at = utcnow()
    match.lost_post.status = "RETURNED"
    match.found_post.status = "RETURNED"
    db.session.commit()
    return success(match.to_dict(include_sensitive=True))
