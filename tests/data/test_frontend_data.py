from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from teloce.data import DataShapeError, frontend_json, to_frontend_data


@dataclass
class Record:
    name: str
    count: int
    happened: date


def test_shapes_plain_records_and_json_safe_values():
    result = to_frontend_data([
        {"name": "A", "count": "4", "secret": "drop", "when": datetime(2026, 1, 2)},
    ], {"name": "string", "count": "integer", "when": "date"})

    assert result == [{"name": "A", "count": 4, "when": "2026-01-02T00:00:00"}]


def test_shapes_dataclasses_and_special_values():
    result = to_frontend_data([Record("A", 2, date(2026, 2, 3))])
    assert result == [{"name": "A", "count": 2, "happened": "2026-02-03"}]

    result = to_frontend_data([{"amount": Decimal("2.5"), "id": UUID("00000000-0000-0000-0000-000000000001")}])
    assert result == [{"amount": 2.5, "id": "00000000-0000-0000-0000-000000000001"}]
    assert '"name": "A"' in frontend_json([{"name": "A"}])


def test_tuple_rows_require_and_follow_schema():
    assert to_frontend_data([(1, "ready")], {"id": "integer", "status": "string"}) == [
        {"id": 1, "status": "ready"}
    ]
    with pytest.raises(DataShapeError, match="expected 2"):
        to_frontend_data([("missing",)], {"id": "string", "status": "string"})
    with pytest.raises(DataShapeError, match="mapping or tuple"):
        to_frontend_data(["not a record"])


def test_invalid_schema_and_non_json_values_are_actionable():
    with pytest.raises(DataShapeError, match="Unknown frontend field type"):
        to_frontend_data([{"value": 1}], {"value": "money"})
    with pytest.raises(DataShapeError, match="Unsupported value"):
        to_frontend_data([{"value": object()}])
