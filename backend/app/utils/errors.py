"""Uniform JSON error responses.

Every error body has the shape ``{"error": {"code", "message", "request_id"}}``.
Internal exceptions are logged server-side and returned as a generic 500 so
stack traces and data never reach the client.
"""

import logging

from flask import g, jsonify
from werkzeug.exceptions import HTTPException

log = logging.getLogger("consentguard")


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def error_response(status, code, message, details=None):
    body = {"error": {"code": code, "message": message, "request_id": getattr(g, "request_id", None)}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        return error_response(err.status, err.code, err.message, err.details)

    @app.errorhandler(429)
    def handle_rate_limit(err):
        return error_response(429, "RATE_LIMITED", "Too many attempts. Please wait and try again.")

    @app.errorhandler(HTTPException)
    def handle_http(err):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 413: "PAYLOAD_TOO_LARGE", 400: "BAD_REQUEST"}
        return error_response(err.code, codes.get(err.code, "HTTP_ERROR"), err.description or err.name)

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        log.exception("Unhandled error (request_id=%s)", getattr(g, "request_id", None))
        from app.extensions import db

        db.session.rollback()
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")
