from flask import jsonify


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or []


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(error):
        return (
            jsonify(
                {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "details": error.details,
                    },
                }
            ),
            error.status,
        )

    @app.errorhandler(413)
    def handle_too_large(_error):
        return (
            jsonify(
                {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "IMAGE_TOO_LARGE",
                        "message": "이미지 파일 크기가 제한을 초과했습니다.",
                        "details": [],
                    },
                }
            ),
            413,
        )
