"""Společné fixtures."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_client():
    """PndClient bez sítě: login OK, definice a statistiky z fixtures."""
    base = "custom_components.cez_pnd.api.PndClient"
    with (
        patch(f"{base}.login", AsyncMock()) as login,
        patch(f"{base}.get_definition", AsyncMock(return_value=load("definition.json"))),
        patch(f"{base}.get_stats", AsyncMock(return_value=load("stats_1003.json"))) as stats,
        patch(f"{base}.close", AsyncMock()),
    ):
        yield {"login": login, "get_stats": stats}
