# tests/test_sensor.py


from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.ventaxia_ha.const import CONF_WIFI_DEVICE_ID, DOMAIN
from tests.const import MOCK_CONFIG

# `hass` and `setup_integration` fixtures are from tests/conftest.py
# `mock_ventaxia_iot_components` fixture is also from tests/conftest.py


async def test_sensor_entities(
    hass: HomeAssistant, setup_integration, mock_ventaxia_iot_components: dict
):
    """Test that sensor entities are created and have correct initial state."""
    # The setup_integration fixture has loaded the component with mocked data.

    # Get the entity registry
    entity_registry = er.async_get(hass)

    # Access the mock device instance that holds the state
    mock_device = mock_ventaxia_iot_components["device"]

    # --- Test Temperature Sensor ---
    temp_entity_id = "sensor.ventaxia_device_temperature"  # Adjust based on your entity_id generation
    temp_state = hass.states.get(temp_entity_id)
    assert temp_state is not None
    # Assert state matches the mocked device's 'temp' property
    assert float(temp_state.state) == mock_device.temp
    assert temp_state.attributes.get("unit_of_measurement") == "°C"
    assert temp_state.attributes.get("device_class") == "temperature"

    # --- Test Humidity Sensor ---
    humidity_entity_id = "sensor.ventaxia_device_humidity"
    humidity_state = hass.states.get(humidity_entity_id)
    assert humidity_state is not None
    # Assert state matches the mocked device's 'rh' property
    assert float(humidity_state.state) == mock_device.rh
    assert humidity_state.attributes.get("unit_of_measurement") == "%"
    assert humidity_state.attributes.get("device_class") == "humidity"

    # --- Test Fan Speed Sensor (if applicable) ---
    fan_speed_entity_id = "sensor.ventaxia_device_fan_speed"
    fan_speed_state = hass.states.get(fan_speed_entity_id)
    assert fan_speed_state is not None
    assert int(fan_speed_state.state) == mock_device.fan_speed

    # Ensure the underlying `get_state` (or equivalent) was called if your component polls
    # This might implicitly be called by the `processor.process` which updates `device`

    # --- Test State Update ---
    # Change the mock device's properties to simulate a device update
    mock_device.temp = 25.0
    mock_device.rh = 70
    mock_device.fan_speed = 4

    # Now, simulate a message being processed that would update the device.
    # In your __init__.py, you have `self._notify_update()` after `processor.process()`.
    # To trigger an update in the test, we can directly call `_notify_update` on the coordinator
    # or simulate the async message loop.
    # For simplicity here, we'll directly update `device` and assert if the entities update based on polling.
    # If your component uses a DataUpdateCoordinator, you would call `coordinator.async_update_listeners()`.
    # For now, if sensors are polling, you might need to wait for next update cycle or trigger it manually.
    # A basic way to trigger an update without waiting for a real timer:
    coordinator = hass.data[DOMAIN].get(
        "your_config_entry_id_here"
    )  # Replace "your_config_entry_id_here"
    # with the actual entry_id or dynamically get it.
    if coordinator:
        coordinator._notify_update()  # Directly call the notification method
    await hass.async_block_till_done()  # Allow Home Assistant to process state changes

    # Re-assert sensor states after the mock update
    temp_state_after_update = hass.states.get(temp_entity_id)
    assert float(temp_state_after_update.state) == 25.0

    humidity_state_after_update = hass.states.get(humidity_entity_id)
    assert float(humidity_state_after_update.state) == 70.0

    fan_speed_state_after_update = hass.states.get(fan_speed_entity_id)
    assert int(fan_speed_state_after_update.state) == 4

    # Test entity unique ID (good practice)
    entry = entity_registry.async_get(temp_entity_id)
    assert (
        entry.unique_id == f"{MOCK_CONFIG[CONF_WIFI_DEVICE_ID]}_temperature"
    )  # Adjust based on your unique_id format
