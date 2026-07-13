import uuid
from pathlib import Path

from flask import Blueprint, current_app, request
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

from ..errors import ApiError
from ..utils import current_user, success

bp = Blueprint("uploads", __name__)


@bp.post("/images")
@jwt_required()
def upload_image():
    current_user()
    image = request.files.get("image")
    if not image or not image.filename:
        raise ApiError("VALIDATION_FAILED", "image 파일이 필요합니다.", 422)

    safe_name = secure_filename(image.filename)
    extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ApiError("INVALID_IMAGE_TYPE", "JPEG, PNG, WebP 이미지만 업로드할 수 있습니다.", 422)
    if image.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
        raise ApiError("INVALID_IMAGE_TYPE", "이미지 MIME 형식이 올바르지 않습니다.", 422)

    filename = f"{uuid.uuid4().hex}.{extension}"
    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    image.save(upload_dir / filename)
    url = f"{current_app.config['UPLOAD_URL_PREFIX'].rstrip('/')}/{filename}"
    return success({"fileName": filename, "url": url}, 201)
