"""Testy parseru proti uloženým odpovědím API (zachytí změnu formátu)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.cez_pnd.api import (
    PndClient,
    PndError,
    parse_number,
    parse_pnd_datetime,
    parse_stats,
)
from custom_components.cez_pnd.coordinator import extract

from .conftest import load


def test_parse_number():
    assert parse_number("5 440,38") == 5440.38
    assert parse_number("5\xa0440,38") == 5440.38
    assert parse_number("0,0") == 0.0
    assert parse_number(None) is None


def test_parse_pnd_datetime():
    assert parse_pnd_datetime("11.11.2026 08:50") == datetime(2026, 11, 11, 8, 50)
    assert parse_pnd_datetime("30.04.2026 24:00") == datetime(2026, 5, 1, 0, 0)
    assert parse_pnd_datetime("31.12.2026 24:00") == datetime(2027, 1, 1, 0, 0)
    assert parse_pnd_datetime("nesmysl") is None
    assert parse_pnd_datetime(None) is None


def test_parse_stats():
    d = parse_stats(load("stats_1003.json"))
    assert set(d) == {"+A/123456", "-A/123456"}
    v = d["-A/123456"]["values"]
    assert v["1007"]["name"] == "Celkem v intervalu"
    assert v["1007"]["unit"] == "kWh"
    assert v["1007"]["value"] == 5440.38
    assert v["1002"]["date"] == "18.05.2026 13:00"


def test_extract():
    data = extract(parse_stats(load("stats_1003.json")))
    assert data.import_kwh == 708.498
    assert data.import_status == 100.0
    assert data.export_kwh == 5440.38
    assert data.export_status == 100.0
    assert data.end_date.replace(tzinfo=None) == datetime(2026, 11, 11, 8, 50)


def test_extract_empty():
    data = extract(parse_stats({"hasData": False}))
    assert data.import_kwh is None and data.end_date is None


def test_definition_shape():
    d = load("definition.json")
    assert d["electrometers"][0]["value"] == "123456"
    assert d["deviceSets"][0]["value"] == 10001


@pytest.mark.parametrize(
    "exc",
    [
        aiohttp.ClientResponseError(MagicMock(real_url="x"), (), status=500),
        aiohttp.ClientConnectionError("down"),
        TimeoutError(),
    ],
)
async def test_login_network_error_is_pnd_error(exc):
    """Chyba sítě/HTTP 500 během přihlášení -> PndError (dočasná chyba)."""
    client = PndClient("a", "b")
    with patch.object(client, "_follow", AsyncMock(side_effect=exc)):
        with pytest.raises(PndError):
            await client.get_stats(-1003, datetime(2026, 1, 1), datetime(2026, 1, 2))
    await client.close()
