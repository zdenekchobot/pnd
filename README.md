# ČEZ Distribuce PND – Home Assistant

Custom integrace pro [Home Assistant](https://www.home-assistant.io/), která čte z
[Portálu naměřených dat ČEZ Distribuce](https://pnd.cezdistribuce.cz) (PND) odběr a dodávku
elektřiny (import/export) z jednoho elektroměru. Nepotřebuje prohlížeč: přihlásí se do portálu
stejně jako webová aplikace a čte data přímo z jejího JSON API.

Integrace není oficiálním produktem ČEZ Distribuce.

## Co integrace dělá

Při každé aktualizaci stáhne souhrnnou tabulku sestavy „00 Profil spotřeby a výroby“ za období
**od zadaného data a času do okamžiku čtení** a vytvoří z ní tyto entity:

| Entita | Název (cs / en) | Zdroj v portálu | Jednotka |
| --- | --- | --- | --- |
| `sensor.elm<číslo>_import` | PND import | řada +A, Celkem v intervalu | kWh |
| `sensor.elm<číslo>_import_status` | PND import - stav / status | řada +A, Úplnost dat | % |
| `sensor.elm<číslo>_export` | PND export | řada −A, Celkem v intervalu | kWh |
| `sensor.elm<číslo>_export_status` | PND export - stav / status | řada −A, Úplnost dat | % |
| `sensor.elm<číslo>_end_date` | Data do: / End date | konec dat v portálu | datum a čas |
| `datetime.elm<číslo>_start_date` | Data od: / Start date | nastavení integrace | datum a čas |

Všechny entity patří zařízení `ELM<číslo>`. Hodnoty importu a exportu mají 3 desetinná místa,
`device_class: energy` a `state_class: total` s `last_reset` = „Data od“.

„Data do:“ ukazuje, do kdy portál data skutečně má. ČEZ je doplňuje se zpožděním, obvykle
jednou denně, proto bývá o několik hodin až den za aktuálním časem.

## Instalace

1. Zkopíruj složku `custom_components/cez_pnd` do `/config/custom_components/` v Home Assistantu.
2. Restartuj Home Assistant.
3. **Nastavení → Zařízení a služby → Přidat integraci → „ČEZ Distribuce PND“**.

Vyžaduje Home Assistant 2026.10 nebo novější.

## Nastavení

Průvodce má dva kroky:

1. **Přihlášení** – e-mail a heslo do PND a interval aktualizace (15–1440 minut, výchozí 60).
2. **Elektroměr a období** – číslo elektroměru (nabídne elektroměry z účtu) a „Data od“
   (datum a čas, výchozí 1. 1. aktuálního roku 00:00).

„Data od“ a interval jde kdykoli změnit přes **Konfigurovat** u integrace. „Data od“ jde změnit
i přímo entitou `datetime.elm<číslo>_start_date`, z dashboardu nebo automatizací. Po změně se
data hned znovu načtou. Když se změní heslo, Home Assistant sám nabídne nové přihlášení.

Pro každý elektroměr se integrace přidává zvlášť.

## Energy dashboard

`PND import` a `PND export` jde vybrat v **Nastavení → Energie** jako odběr ze sítě a dodávku do sítě.
Má to ale dvě omezení:

- Spotřeba se do statistik připíše v hodině, kdy ji integrace stáhla, ne v hodině, kdy skutečně
  proběhla, protože portál data doplňuje se zpožděním.
- Změna „Data od“ znamená nový začátek počítání (`last_reset`).

## Pojmenování entit

Home Assistant běžně skládá zobrazovaný název jako „zařízení + entita“ (např. „ELM123456 PND import“).
Aby zůstaly krátké názvy, integrace je při prvním přidání entity uloží do registru entit, stejně
jako by je uživatel přejmenoval ručně. Když entitu přejmenuješ, tvůj název zůstane. Při změně
jazyka Home Assistantu se už uložené názvy samy nepřeloží.

## Řešení problémů

Podrobný log zapneš v `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.cez_pnd: debug
```

Test přihlášení a stažení dat bez Home Assistantu (potřebuje jen `aiohttp`):

```bash
python test_cli.py email heslo 2026-05-01
```

## Vývoj

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

Testy používají uložené (anonymizované) odpovědi portálu v `tests/fixtures`. Když portál změní
formát, ulož v prohlížeči nový HAR (DevTools → Network → Save all as HAR) a porovnej ho s fixtures.
HAR obsahuje přihlašovací tokeny, do gitu ho necommituj.

## Licence

[MIT](LICENSE)
