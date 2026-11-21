"""Testy parseru proti uloženým odpovědím API (zachytí změnu formátu)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.cez_pnd.api import (
    PndAuthError,
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


def _client_with_responses(responses):
    """Klient s podvrženým _request: postupně vrací/vyhazuje položky z responses."""
    client = PndClient("a", "b")
    logins = AsyncMock()

    async def fake_login():
        await logins()
        client._logged_in = True

    async def fake_request(method, url, json=None):
        r = responses.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r

    client.login = fake_login
    client._request = fake_request
    return client, logins


async def test_server_error_relogins_and_retries():
    """500 při stahování -> nové přihlášení a druhý pokus ve stejném volání."""
    from custom_components.cez_pnd.api import _ServerError

    client, logins = _client_with_responses([_ServerError("500"), {"ok": 1}])
    assert await client.get_stats(-1003, datetime(2026, 1, 1), datetime(2026, 1, 2)) == {"ok": 1}
    assert logins.await_count == 2  # úvodní + po 500
    await client.close()


async def test_after_error_next_call_logs_in_again():
    """Trvalá 500 -> PndError; další volání (portál už OK) se přihlásí znovu."""
    from custom_components.cez_pnd.api import _ServerError

    client, logins = _client_with_responses(
        [_ServerError("500"), _ServerError("500"), {"ok": 1}]
    )
    with pytest.raises(PndError, match="500"):
        await client.get_stats(-1003, datetime(2026, 1, 1), datetime(2026, 1, 2))
    assert client._logged_in is False
    logins.reset_mock()
    assert await client.get_stats(-1003, datetime(2026, 1, 1), datetime(2026, 1, 2)) == {"ok": 1}
    assert logins.await_count == 1
    await client.close()


async def test_login_500_is_not_auth_error():
    """500 z CAS po odeslání formuláře není špatné heslo."""
    client = PndClient("a", "b")
    calls = []

    class Resp:
        def __init__(self, status, location=""):
            self.status = status
            self.headers = MagicMock(getall=lambda *_: [], get=lambda *_: location)
            self.request_info = MagicMock(real_url="x")
            self.history = ()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def raise_for_status(self):
            if self.status >= 400:
                raise aiohttp.ClientResponseError(self.request_info, (), status=self.status)

        async def text(self):
            return '<input name="execution" value="e1">'

        async def read(self):
            return b""

    def request(method, url, **kw):
        calls.append((method, str(url)))
        if method == "POST":
            return Resp(500)
        if "cas" in str(url):
            return Resp(200)
        return Resp(302, "https://cas.cez.cz/cas/login")

    sess = MagicMock(request=request, closed=False, close=AsyncMock())
    client._session = sess
    with pytest.raises(PndError) as ei:
        await client.login()
    assert not isinstance(ei.value, PndAuthError)
    assert calls[-1][0] == "POST"
    await client.close()
