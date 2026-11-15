"""Testy config flow, entit a změny data „od“."""

from datetime import datetime

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.cez_pnd.api import PndAuthError
from custom_components.cez_pnd.const import (
    CONF_DATE_FROM,
    CONF_ELECTROMETER,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

USER = {CONF_USERNAME: "a@b.cz", CONF_PASSWORD: "x", CONF_SCAN_INTERVAL: 30}


def _entry(**options) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="elm123456",
        title="Elektroměr 123456",
        data={CONF_USERNAME: "a@b.cz", CONF_PASSWORD: "x", CONF_ELECTROMETER: "123456"},
        options={CONF_DATE_FROM: "2026-05-01 00:00:00", CONF_SCAN_INTERVAL: 60, **options},
    )


async def test_flow_ok(hass: HomeAssistant, mock_client) -> None:
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert r["step_id"] == "user"
    r = await hass.config_entries.flow.async_configure(r["flow_id"], USER)
    assert r["step_id"] == "electrometer"
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {CONF_ELECTROMETER: "123456", CONF_DATE_FROM: "2026-05-01 06:30:00"}
    )
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["title"] == "Elektroměr 123456"
    assert r["result"].unique_id == "elm123456"
    assert r["data"][CONF_ELECTROMETER] == "123456"
    assert r["options"] == {CONF_DATE_FROM: "2026-05-01 06:30:00", CONF_SCAN_INTERVAL: 30}
    await hass.async_block_till_done()


async def test_flow_invalid_auth(hass: HomeAssistant, mock_client) -> None:
    mock_client["login"].side_effect = PndAuthError("bad")
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    r = await hass.config_entries.flow.async_configure(r["flow_id"], USER)
    assert r["errors"] == {"base": "invalid_auth"}


async def test_flow_duplicate(hass: HomeAssistant, mock_client) -> None:
    _entry().add_to_hass(hass)
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    r = await hass.config_entries.flow.async_configure(r["flow_id"], USER)
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {CONF_ELECTROMETER: "123456", CONF_DATE_FROM: "2026-05-01 00:00:00"}
    )
    assert r["type"] is FlowResultType.ABORT
    assert r["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("language", "names"),
    [
        (
            "en",
            {
                "sensor.elm123456_import": "PND import",
                "sensor.elm123456_import_status": "PND import - status",
                "sensor.elm123456_export": "PND export",
                "sensor.elm123456_export_status": "PND export - status",
                "sensor.elm123456_end_date": "End date",
                "datetime.elm123456_start_date": "Start date",
            },
        ),
        (
            "cs",
            {
                "sensor.elm123456_import": "PND import",
                "sensor.elm123456_import_status": "PND import - stav",
                "sensor.elm123456_export": "PND export",
                "sensor.elm123456_export_status": "PND export - stav",
                "sensor.elm123456_end_date": "Data do:",
                "datetime.elm123456_start_date": "Data od:",
            },
        ),
    ],
)
async def test_entities(hass: HomeAssistant, mock_client, language, names) -> None:
    hass.config.language = language
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    reg = er.async_get(hass)
    for entity_id, name in names.items():
        st = hass.states.get(entity_id)
        assert st is not None, entity_id
        assert st.attributes["friendly_name"] == name
        reg_entry = reg.async_get(entity_id)
        assert reg_entry.unique_id == entity_id.split(".", 1)[1]
        device = dr.async_get(hass).async_get(reg_entry.device_id)
        assert device.name == "ELM123456"

    imp = hass.states.get("sensor.elm123456_import")
    assert float(imp.state) == 708.498
    assert imp.attributes["unit_of_measurement"] == "kWh"
    assert imp.attributes["device_class"] == "energy"
    assert imp.attributes["state_class"] == "total"
    assert float(hass.states.get("sensor.elm123456_export").state) == 5440.38
    assert float(hass.states.get("sensor.elm123456_import_status").state) == 100.0
    assert hass.states.get("sensor.elm123456_import_status").attributes["unit_of_measurement"] == "%"
    for eid, icon in (
        ("sensor.elm123456_import_status", "mdi:progress-pencil"),
        ("sensor.elm123456_export_status", "mdi:progress-pencil"),
        ("sensor.elm123456_end_date", "mdi:calendar-clock"),
        ("datetime.elm123456_start_date", "mdi:calendar-clock"),
    ):
        assert hass.states.get(eid).attributes["icon"] == icon, eid
    end = hass.states.get("sensor.elm123456_end_date")
    assert end.attributes["device_class"] == "timestamp"
    assert datetime.fromisoformat(end.state).isoformat().startswith("2026-11-11T")

    # dotaz na portál: interval od „Data od“ do teď, správný elektroměr
    call = mock_client["get_stats"].call_args
    assert call.args[0] == -1003
    assert call.args[1] == datetime(2026, 5, 1, 0, 0)
    assert call.kwargs["electrometer"] == "123456"


async def test_set_start_date(hass: HomeAssistant, mock_client) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "datetime",
        "set_value",
        {"entity_id": "datetime.elm123456_start_date", "datetime": "2026-06-01 12:00:00"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert entry.options[CONF_DATE_FROM] == "2026-06-01 12:00:00"
    assert mock_client["get_stats"].call_args.args[1] == datetime(2026, 6, 1, 12, 0)


async def test_options_flow(hass: HomeAssistant, mock_client) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {CONF_DATE_FROM: "2026-07-01 00:00:00", CONF_SCAN_INTERVAL: 1440}
    )
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_DATE_FROM: "2026-07-01 00:00:00", CONF_SCAN_INTERVAL: 1440}


async def test_auth_error_starts_reauth(hass: HomeAssistant, mock_client) -> None:
    mock_client["get_stats"].side_effect = PndAuthError("bad")
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_migrate_v1(hass: HomeAssistant, mock_client) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        unique_id="a@b.cz_elm:123456_-1003",
        data={
            CONF_USERNAME: "a@b.cz",
            CONF_PASSWORD: "x",
            "assembly": "-1003",
            "device": "elm:123456",
            CONF_DATE_FROM: "2026-05-01",
            CONF_SCAN_INTERVAL: 60,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 2
    assert entry.unique_id == "elm123456"
    assert entry.options[CONF_DATE_FROM] == "2026-05-01 00:00:00"
    assert hass.states.get("sensor.elm123456_import") is not None


async def test_user_rename_kept(hass: HomeAssistant, mock_client) -> None:
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    er.async_get(hass).async_update_entity("sensor.elm123456_import", name="Spotřeba")
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.elm123456_import").attributes["friendly_name"] == "Spotřeba"


async def test_brand_icons(hass: HomeAssistant) -> None:
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    assert integration.has_branding


async def test_status_binary_sensor(hass: HomeAssistant, mock_client) -> None:
    from custom_components.cez_pnd.api import PndError

    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    eid = "binary_sensor.elm123456_status"
    st = hass.states.get(eid)
    assert st.state == "off"
    assert st.attributes["friendly_name"] == "PND status"
    assert st.attributes["icon"] == "mdi:refresh"
    assert st.attributes["device_class"] == "problem"
    assert er.async_get(hass).async_get(eid).unique_id == "elm123456_status"

    coordinator = entry.runtime_data
    mock_client["get_stats"].side_effect = PndError("portál nedostupný")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    st = hass.states.get(eid)
    assert st.state == "on"
    assert "portál nedostupný" in st.attributes["error"]

    mock_client["get_stats"].side_effect = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"
