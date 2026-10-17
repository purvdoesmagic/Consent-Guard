"""Small server-side input validation helpers.

Every API handler reads its input through these helpers so that type, length
and allowed-value checks happen on the server regardless of the frontend.
"""

import re

from flask import request

from app.utils.errors import ApiError
from app.utils.time import parse_iso


def json_body():
    if not request.is_json:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Request body must be JSON.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_JSON", "Request body must be a JSON object.")
    return data


def invalid(field, message):
    return ApiError(400, "VALIDATION_ERROR", message, {"field": field})


def get_str(data, field, *, required=True, min_len=0, max_len=255, pattern=None, strip=True):
    value = data.get(field)
    if value is None or (isinstance(value, str) and not value.strip() and strip):
        if required:
            raise invalid(field, f"'{field}' is required.")
        return None
    if not isinstance(value, str):
        raise invalid(field, f"'{field}' must be a string.")
    if strip:
        value = value.strip()
    if len(value) < min_len or len(value) > max_len:
        raise invalid(field, f"'{field}' must be between {min_len} and {max_len} characters.")
    if pattern and not re.fullmatch(pattern, value):
        raise invalid(field, f"'{field}' has an invalid format.")
    return value


def get_choice(data, field, choices, *, required=True):
    value = data.get(field)
    if value is None:
        if required:
            raise invalid(field, f"'{field}' is required.")
        return None
    if value not in choices:
        raise invalid(field, f"'{field}' must be one of: {', '.join(sorted(choices))}.")
    return value


def get_choice_list(data, field, choices, *, required=True, min_items=1):
    value = data.get(field)
    if value is None:
        if required:
            raise invalid(field, f"'{field}' is required.")
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise invalid(field, f"'{field}' must be a list of strings.")
    unique = sorted(set(value))
    if len(unique) < min_items:
        raise invalid(field, f"'{field}' must contain at least {min_items} item(s).")
    bad = [v for v in unique if v not in choices]
    if bad:
        raise invalid(field, f"'{field}' contains unsupported values: {', '.join(bad)}.")
    return unique


def get_int(data, field, *, required=True, minimum=None, maximum=None):
    value = data.get(field)
    if value is None:
        if required:
            raise invalid(field, f"'{field}' is required.")
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise invalid(field, f"'{field}' must be an integer.")
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise invalid(field, f"'{field}' is out of range.")
    return value


def get_timestamp(data, field, *, required=True):
    value = data.get(field)
    if value in (None, ""):
        if required:
            raise invalid(field, f"'{field}' is required.")
        return None
    try:
        return parse_iso(value)
    except (ValueError, TypeError):
        raise invalid(field, f"'{field}' must be an ISO-8601 timestamp.")


def query_timestamp(name):
    value = request.args.get(name)
    if not value:
        return None
    try:
        return parse_iso(value)
    except ValueError:
        raise invalid(name, f"'{name}' must be an ISO-8601 timestamp.")


def query_int(name, default=None, minimum=None, maximum=None):
    value = request.args.get(name)
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except ValueError:
        raise invalid(name, f"'{name}' must be an integer.")
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise invalid(name, f"'{name}' is out of range.")
    return number
