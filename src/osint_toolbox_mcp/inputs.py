"""Checks for tool arguments. Failures are ToolErrors: the model sees them and can correct its call."""

from __future__ import annotations

import re
from typing import Any


class ToolError(Exception):
    """Bad input or a failed run: returned to the model as a tool error it can act on."""


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_DOMAIN = re.compile(r"(?=.{1,253}$)([a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?\.)+[a-z0-9-]{2,63}")


def text(arguments: dict[str, Any], key: str, *, required: bool = True, max_length: int = 256) -> str | None:
    value = arguments.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ToolError(f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise ToolError(f"'{key}' must be a string")
    return clean(key, value, max_length)


def clean(key: str, value: str, max_length: int = 256) -> str:
    value = value.strip()
    if len(value) > max_length:
        raise ToolError(f"'{key}' must be at most {max_length} characters")
    if value.startswith("-"):
        raise ToolError(f"'{key}' must not start with '-': the tool would read it as an option")
    if _CONTROL_CHARS.search(value):
        raise ToolError(f"'{key}' must not contain control characters")
    return value


def domain(arguments: dict[str, Any], key: str) -> str:
    """A domain name, also accepted as a URL or with a trailing dot; returned in lowercase ASCII (IDNA)."""
    value = text(arguments, key).lower()
    value = re.sub(r"^[a-z][a-z0-9+.-]*://", "", value).split("/")[0].split(":")[0].rstrip(".")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        raise ToolError(f"'{key}' is not a valid domain name") from None
    if not _DOMAIN.fullmatch(value):
        raise ToolError(f"'{key}' must be a domain name like example.com")
    return value


def integer(arguments: dict[str, Any], key: str, low: int, high: int) -> int | None:
    value = arguments.get(key)
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"'{key}' must be an integer")
    if not low <= value <= high:
        raise ToolError(f"'{key}' must be between {low} and {high}")
    return value


def flag(arguments: dict[str, Any], key: str, default: bool) -> bool:
    value = arguments.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolError(f"'{key}' must be true or false")
    return value


def choice(arguments: dict[str, Any], key: str, choices: tuple[str, ...], default: str) -> str:
    value = arguments.get(key)
    if value is None:
        return default
    if value not in choices:
        raise ToolError(f"'{key}' must be one of: {', '.join(choices)}")
    return value
