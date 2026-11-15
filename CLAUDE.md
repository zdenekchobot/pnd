# ČEZ Distribuce PND – Home Assistant integrace

Custom integrace (`custom_components/cez_pnd`) čte data elektroměru z portálu
https://pnd.cezdistribuce.cz bez prohlížeče – přímo přes JSON API, které volá Vue frontend.
Komunikace a odpovědi v češtině.

## Architektura
- `api.py` – klient nezávislý na HA (jen aiohttp). Lze testovat samostatně (`test_cli.py`).
- `coordinator.py` – DataUpdateCoordinator, sestava -1003, interval „Data od → teď“, vrací `PndData`.
- `config_flow.py` – přihlášení + interval (15–1440 min) → elektroměr + Data od; options (Data od, interval); reauth; migrace v1→v2 v `__init__.py`.
- `sensor.py` – import, import_status, export, export_status, end_date; `datetime.py` – „Data od:“ (změna uloží options a reloadne).
- `entity.py` – zařízení `ELM<číslo>`, unique_id/entity_id `elm<číslo>_<klíč>`, názvy z překladů.
  HA 2026.10 předřazuje friendly name název zařízení; krátké názvy („PND import“, „Data od:“) se proto
  při přidání entity zapíšou do registru (`name`), jen pokud ho uživatel nepřejmenoval.
- Platforma `datetime.py` zastiňuje modul `datetime` v balíčku: v `__init__.py` importovat jako `DateTime`,
  testy importují přes `custom_components.cez_pnd…`, `test_cli.py` načítá `api.py` přes importlib.

## Přihlášení (CAS + OAuth2)
1. GET `/cezpnd2/external/dashboard/view` → 302 řetěz → `mepas.cez.cz/cas/login?service=…` (HTML formulář)
2. POST formuláře: `username`, `password`, `execution` (skryté pole), `_eventId=submit`, `geolocation=`
3. 302 řetěz → `/cezpnd2/login/oauth2/code/mepas-external?code=…` → dashboard 200

Důležité (zjištěno při ladění):
- Přesměrování se procházejí ručně (`_follow`) s `URL(..., encoded=True)` – aiohttp jinak překódovává `service`/`state`.
- Cookies řeší vlastní `_Jar` (aiohttp `DummyCookieJar`). Standardní jar zahazoval cookie
  (pravděpodobně F5 `TS01ed5b19` s atributem Domain) → nekonečná smyčka přihlášení.

## API
- `GET /cezpnd2/external/dashboard/window/definition` → `deviceSets` (idDeviceSet), `electrometers` (electrometerId)
- `POST /cezpnd2/external/data` JSON:
  `{"format":"stats","idAssembly":-1003,"idDeviceSet":null|"10001","intervalFrom":"dd.mm.YYYY HH:MM","intervalTo":"…","compareFrom":null,"opmId":null,"electrometerId":"123456"|null}`
- Odpověď: `columns[{id,name}]`, `ranges{"+A/123456":[{start,end,values{colId:{v,u,d}}}]}`; čísla v CZ formátu (`"5 440,38"`).
- Sloupce: 1001 řada, 1002 Max, 1003 Min, 1004 Celkem, 1005 Průměr, 1006 Posl. hod. registru,
  1007 Celkem v intervalu, 1008 Účiník, 1009 Úplnost dat, 1010 CO2.
- Sestavy (pevně v `const.py`): -1003, -1001, -1002, -1012, -1011, -1021, -1022, -1027.
- `POST /external/dashboard/window/update` NEvolat – mění uložený dashboard uživatele.

## Vývoj
- Testy: `python -m venv .venv && .venv/bin/pip install -r requirements_test.txt && .venv/bin/pytest` (fixtures = reálné odpovědi API v `tests/fixtures`).
- Živý test: `python test_cli.py email heslo 2026-05-01 -1003` (debug výpis přesměrování a cookies).
- Při změně portálu: nový HAR (DevTools → Network → Save all as HAR), porovnat s fixtures. HAR do gitu necommitovat (obsahuje tokeny).
- Fixtures jsou anonymizované (elektroměr 123456, sada 10001) – nové odpovědi z portálu před commitem anonymizovat stejně.
