"""Lehký klient pro portál ČEZ Distribuce PND (bez závislosti na HA)."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from yarl import URL

_LOGGER = logging.getLogger(__name__)

BASE = "https://pnd.cezdistribuce.cz/cezpnd2"
ENTRY_URL = f"{BASE}/external/dashboard/view"
DEFINITION_URL = f"{BASE}/external/dashboard/window/definition"
CHECK_URL = f"{BASE}/external/dashboard/checkUserData"
DATA_URL = f"{BASE}/external/data"

_EXECUTION_RE = re.compile(
    r'<input[^>]*name="execution"[^>]*value="([^"]+)"'
    r'|<input[^>]*value="([^"]+)"[^>]*name="execution"'
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "cs,en;q=0.8",
}
_JSON_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://pnd.cezdistribuce.cz",
    "Referer": ENTRY_URL,
}


class PndError(Exception):
    """Obecná chyba."""


class PndAuthError(PndError):
    """Chybné přihlašovací údaje."""


class _SessionExpired(PndError):
    """Session vypršela."""


def fmt_dt(dt: datetime) -> str:
    """Formát data používaný portálem."""
    return dt.strftime("%d.%m.%Y %H:%M")


def parse_pnd_datetime(value: str | None) -> datetime | None:
    """'11.11.2026 08:50' -> naivní datetime; '30.04.2026 24:00' -> 01.05.2026 00:00."""
    if not value:
        return None
    value = value.strip()
    try:
        if value.endswith("24:00"):
            day = datetime.strptime(value[:-5].strip(), "%d.%m.%Y")
            return day + timedelta(days=1)
        return datetime.strptime(value, "%d.%m.%Y %H:%M")
    except ValueError:
        return None


def parse_number(value: str | None) -> float | None:
    """'5 440,38' -> 5440.38."""
    if value is None:
        return None
    s = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class _Jar:
    """Minimalistické úložiště cookies (obchází striktní http.cookies)."""

    def __init__(self) -> None:
        # (domain, path, name) -> (value, host_only)
        self._c: dict[tuple[str, str, str], tuple[str, bool]] = {}

    def clear(self) -> None:
        self._c.clear()

    def update(self, url: str, headers: list[str]) -> None:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
        for raw in headers:
            parts = [p.strip() for p in raw.split(";")]
            if not parts or "=" not in parts[0]:
                continue
            name, value = parts[0].split("=", 1)
            name = name.strip()
            domain, host_only = host, True
            path = u.path.rsplit("/", 1)[0] or "/"
            delete = False
            attrs = []
            for a in parts[1:]:
                k, _, v = a.partition("=")
                k = k.strip().lower()
                v = v.strip()
                attrs.append(k)
                if k == "domain" and v:
                    domain, host_only = v.lstrip(".").lower(), False
                elif k == "path" and v:
                    path = v
                elif k == "max-age":
                    try:
                        delete = int(v) <= 0
                    except ValueError:
                        pass
                elif k == "expires" and not delete:
                    try:
                        delete = parsedate_to_datetime(v) < datetime.now(UTC)
                    except (TypeError, ValueError):
                        pass
            _LOGGER.debug(
                "  Set-Cookie %s (domain=%s path=%s %s)%s",
                name, domain, path, ",".join(attrs), " DELETE" if delete else "",
            )
            key = (domain, path, name)
            if delete:
                self._c.pop(key, None)
            else:
                self._c[key] = (value, host_only)

    def header(self, url: str) -> str:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
        rpath = u.path or "/"
        out = []
        for (domain, path, name), (value, host_only) in sorted(
            self._c.items(), key=lambda i: -len(i[0][1])
        ):
            if host_only and host != domain:
                continue
            if not host_only and not (host == domain or host.endswith("." + domain)):
                continue
            if not (rpath == path or rpath.startswith(path.rstrip("/") + "/")):
                continue
            out.append(f"{name}={value}")
        return "; ".join(out)


class PndClient:
    """Klient s vlastní session (cookies)."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._logged_in = False
        self._jar = _Jar()

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=_HEADERS,
                cookie_jar=aiohttp.DummyCookieJar(),
                timeout=aiohttp.ClientTimeout(total=60),
                requote_redirect_url=False,
            )
        return self._session

    async def _follow(
        self, method: str, url: str, data: dict[str, str] | None = None
    ) -> tuple[str, str]:
        """Ruční průchod přesměrováními bez překódování URL.

        Vrací (konečná URL, HTML).
        """
        sess = self._sess()
        seen: list[str] = []
        for _ in range(20):
            async with sess.request(
                method,
                URL(url, encoded=True),
                data=data,
                headers=self._cookie_hdr(url),
                allow_redirects=False,
            ) as resp:
                _LOGGER.debug("%s %s -> %s", method, url[:150], resp.status)
                self._jar.update(url, resp.headers.getall("Set-Cookie", []))
                if resp.status not in (301, 302, 303, 307, 308):
                    return url, await resp.text()
                loc = resp.headers.get("Location", "")
                await resp.read()
            seen.append(url)
            url = urljoin(url, loc)
            if resp.status in (301, 302, 303):
                method, data = "GET", None
        raise PndError("Smyčka přesměrování: " + " | ".join(u[:120] for u in seen[-6:]))

    def _cookie_hdr(self, url: str) -> dict[str, str]:
        c = self._jar.header(url)
        return {"Cookie": c} if c else {}

    async def login(self) -> None:
        """CAS login -> OAuth2 redirect -> session cookie v PND."""
        self._jar.clear()
        self._logged_in = False

        # 1) Vstupní stránka přesměruje na přihlašovací formulář CAS
        login_url, html = await self._follow("GET", ENTRY_URL)

        if "pnd.cezdistribuce.cz" in login_url and "dashboard" in login_url:
            self._logged_in = True  # ještě platná session
            return

        m = _EXECUTION_RE.search(html)
        if not m:
            raise PndError(f"Nenalezen přihlašovací formulář ({login_url})")

        form = {
            "username": self._username,
            "password": self._password,
            "execution": m.group(1) or m.group(2),
            "_eventId": "submit",
            "geolocation": "",
        }
        # 2) Odeslání formuláře + ruční průchod přesměrováními
        final_url, html = await self._follow("POST", login_url, form)

        if "pnd.cezdistribuce.cz" not in final_url:
            _LOGGER.debug("Login skončil na %s", final_url)
            raise PndAuthError("Přihlášení selhalo (špatné jméno nebo heslo?)")

        # 3) Ověření
        await self._get_json(CHECK_URL, retry=False)
        self._logged_in = True
        _LOGGER.debug("Přihlášení do PND OK")

    async def _request(self, method: str, url: str, json: Any = None) -> Any:
        sess = self._sess()
        async with sess.request(
            method,
            url,
            json=json,
            headers={**_JSON_HEADERS, **self._cookie_hdr(url)},
            allow_redirects=False,
        ) as resp:
            self._jar.update(url, resp.headers.getall("Set-Cookie", []))
            if resp.status in (301, 302, 303, 401, 403):
                raise _SessionExpired
            resp.raise_for_status()
            if "json" not in resp.headers.get("Content-Type", ""):
                raise _SessionExpired
            return await resp.json()

    async def _get_json(self, url: str, retry: bool = True) -> Any:
        return await self._call("GET", url, None, retry)

    async def _call(self, method: str, url: str, body: Any, retry: bool = True) -> Any:
        # Síťové chyby a HTTP chyby (např. 500) i během přihlášení -> PndError
        try:
            if not self._logged_in and retry:
                await self.login()
            try:
                return await self._request(method, url, body)
            except _SessionExpired:
                if not retry:
                    raise PndAuthError("Neplatná session po přihlášení") from None
                _LOGGER.debug("Session vypršela, přihlašuji znovu")
                await self.login()
                return await self._request(method, url, body)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PndError(f"Chyba komunikace: {err}") from err

    async def get_definition(self) -> dict[str, Any]:
        """Sestavy, sady zařízení, elektroměry."""
        return await self._get_json(DEFINITION_URL)

    async def get_stats(
        self,
        assembly: int,
        date_from: datetime,
        date_to: datetime,
        device_set: str | None = None,
        electrometer: str | None = None,
    ) -> dict[str, Any]:
        """Tabulka statistik (to, co se zobrazí pod grafem)."""
        body = {
            "format": "stats",
            "idAssembly": assembly,
            "idDeviceSet": device_set,
            "intervalFrom": fmt_dt(date_from),
            "intervalTo": fmt_dt(date_to),
            "compareFrom": None,
            "opmId": None,
            "electrometerId": electrometer,
        }
        return await self._call("POST", DATA_URL, body)


def parse_stats(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Převod odpovědi na {řada: {col_id: {name, value, raw, unit, date}}}.

    Sloupec 1001 (Datová řada) slouží jako název řady.
    """
    out: dict[str, dict[str, Any]] = {}
    if not data or not data.get("hasData"):
        return out
    cols = {c["id"]: c["name"] for c in data.get("columns", [])}
    for series, ranges in (data.get("ranges") or {}).items():
        if not ranges:
            continue
        rng = ranges[0]
        values: dict[str, Any] = {}
        for cid, cell in (rng.get("values") or {}).items():
            if cid == "1001":
                continue
            raw = cell.get("v")
            values[cid] = {
                "name": cols.get(cid, cid),
                "raw": raw,
                "value": parse_number(raw),
                "unit": cell.get("u"),
                "date": cell.get("d"),
            }
        out[series] = {
            "start": rng.get("start"),
            "end": rng.get("end"),
            "values": values,
        }
    return out
