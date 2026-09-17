"""Python-to-browser data shaping helpers.

The core package deliberately has no pandas dependency.  ``to_frontend_data``
accepts ordinary Python records and detects a pandas DataFrame by its public
``to_dict`` method when pandas is installed in the application environment.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from pathlib import Path
from collections.abc import Mapping
from typing import Any
from uuid import UUID


class DataShapeError(TypeError):
    """Raised when a value cannot be represented safely in JSON."""


def _records(value: Any) -> list[Any]:
    if value is None:
        return []
    # pandas DataFrame (and compatible table objects) without importing it.
    if hasattr(value, "to_dict") and callable(value.to_dict) and value.__class__.__name__ == "DataFrame":
        return list(value.to_dict(orient="records"))
    if isinstance(value, Mapping) or is_dataclass(value):
        return [value]
    if isinstance(value, (str, bytes, bytearray)):
        raise DataShapeError("records must be a mapping, dataclass, DataFrame, or iterable of records")
    try:
        return list(value)
    except TypeError as exc:
        raise DataShapeError("records must be iterable") from exc


def _json_value(value: Any, path: str) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value), path)
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not isfinite(value):
            return None
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID, Path)):
        return float(value) if isinstance(value, Decimal) else str(value)
    # Numpy scalar values expose item(); this keeps numpy optional too.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_value(item(), path)
        except (TypeError, ValueError):
            pass
    if isinstance(value, Mapping):
        return {str(key): _json_value(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise DataShapeError(f"Unsupported value at {path}: {type(value).__name__}")


def _coerce(value: Any, kind: Any, path: str) -> Any:
    if value is None:
        return None
    if callable(kind) and not isinstance(kind, str):
        try:
            return kind(value)
        except Exception as exc:  # pragma: no cover - user callback
            raise DataShapeError(f"Could not convert {path}: {exc}") from exc
    kind = str(kind or "json").lower()
    if kind in {"json", "any", "object"}:
        return value
    if kind in {"string", "str"}:
        return str(value)
    if kind in {"number", "float"}:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise DataShapeError(f"Expected a number at {path}, got {value!r}") from exc
    if kind in {"integer", "int"}:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise DataShapeError(f"Expected an integer at {path}, got {value!r}") from exc
    if kind in {"boolean", "bool"}:
        if isinstance(value, str):
            if value.lower() in {"true", "1", "yes", "on"}: return True
            if value.lower() in {"false", "0", "no", "off"}: return False
        return bool(value)
    if kind in {"date", "datetime"}:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)
    raise DataShapeError(f"Unknown frontend field type {kind!r} at {path}")


def to_frontend_data(records: Any, fields: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return JSON-safe records for a Teloce component.

    ``fields`` is an allow-list and optional type schema.  Omitting it keeps
    all mapping fields.  Extra attributes are intentionally dropped when a
    schema is supplied, preventing accidental exposure of backend-only data.
    """
    output: list[dict[str, Any]] = []
    schema = dict(fields or {})
    for index, record in enumerate(_records(records)):
        if is_dataclass(record): record = asdict(record)
        if not isinstance(record, Mapping):
            if isinstance(record, (tuple, list)) and schema:
                if len(record) != len(schema):
                    raise DataShapeError(
                        f"Record {index} has {len(record)} values; expected {len(schema)}"
                    )
                names = list(schema)
                record = dict(zip(names, record))
            else:
                raise DataShapeError(f"Record {index} must be a mapping or tuple with a schema")
        names = list(schema) if schema else list(record)
        shaped: dict[str, Any] = {}
        for name in names:
            path = f"records[{index}].{name}"
            value = record.get(name)
            if schema and name in schema:
                value = _coerce(value, schema[name], path)
            shaped[str(name)] = _json_value(value, path)
        output.append(shaped)
    # Validate the final shape now, so the developer receives an error at the
    # Python boundary rather than a failed response in the browser.
    try:
        json.dumps(output, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise DataShapeError(f"Frontend data is not JSON serializable: {exc}") from exc
    return output


def frontend_json(records: Any, fields: Mapping[str, Any] | None = None, **kwargs: Any) -> str:
    """Serialize :func:`to_frontend_data` for a Flask/FastAPI response."""
    return json.dumps(to_frontend_data(records, fields), ensure_ascii=False, **kwargs)


__all__ = ["DataShapeError", "frontend_json", "to_frontend_data"]
