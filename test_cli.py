"""Test API mimo HA:  python test_cli.py email heslo 2026-05-01 [-1003]"""

import asyncio
import importlib.util
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# api.py se načítá přímo: adresář balíčku nejde dát do sys.path, protože
# obsahuje platformu datetime.py, která by zastínila standardní modul.
_spec = importlib.util.spec_from_file_location(
    "pnd_api", Path(__file__).parent / "custom_components" / "cez_pnd" / "api.py"
)
_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_api)
PndClient, parse_stats = _api.PndClient, _api.parse_stats


logging.basicConfig(level=logging.DEBUG, format="%(message)s")
logging.getLogger("asyncio").setLevel(logging.WARNING)


async def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(f"Použití: python {sys.argv[0]} email heslo YYYY-MM-DD[THH:MM] [sestava]")
    user, pwd, dfrom = sys.argv[1:4]
    assembly = int(sys.argv[4]) if len(sys.argv) > 4 else -1003
    c = PndClient(user, pwd)
    try:
        await c.login()
        d = await c.get_definition()
        print("Definice:", json.dumps(d, ensure_ascii=False, indent=1))
        elm = d["electrometers"][0]["value"] if d.get("electrometers") else None
        dset = None if elm else str(d["deviceSets"][0]["value"])
        raw = await c.get_stats(
            assembly, datetime.fromisoformat(dfrom), datetime.now().replace(second=0, microsecond=0),
            device_set=dset, electrometer=elm,
        )
        print(json.dumps(parse_stats(raw), ensure_ascii=False, indent=1))
    finally:
        await c.close()


asyncio.run(main())
