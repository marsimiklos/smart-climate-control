# Changelog

This fork continues from the original project's v3.0.

## 3.2.0

### Added
- Schedule support with **learned pre-heating**: the house reaches the comfort temperature when the schedule turns on. The heating rate is learned per outside temperature. New sensors *Learned Heating Rate* and *Preheat Start*, switches *Schedule Control* and *Preheat*.
- Statistics and diagnosis: *Runtime Today*, *Cycles Today*, *Estimated Energy Today*, *Average Run Length Today* and *Cycle Diagnosis* (detects short cycling). Optional heat pump power sensor or rated power for the energy estimate.
- *Force Heating* switch.

### Changed
- **HEAT now follows the deadband** like AUTO does. It used to heat continuously, bypassing the deadband. That behaviour moved to the separate *Force Heating* switch. *Force Comfort Mode* only selects the comfort target now.

## 3.1.0

### Fixed
- Sensor changes (window, temperatures, power, presence) now trigger an immediate update. The state listener was a coroutine decorated with `@callback` and never ran.
- A value of `0` can be saved in the options (window delay, boot delay, minimum run / off time). It used to be replaced by the default.
- Saving the options no longer resets values adjusted through number entities (cooling temperature, free cooling limits, ...).
- Clearing an optional entity in the options now really removes it instead of falling back to the one from the initial setup.
- The *Vent Run Duration* number is respected by automatic runs. `trigger_ventilation` with a duration no longer overwrites the default.
- Periodic fan circulation is no longer switched off by the ventilation safety check.
- AUTO mode can cool when no outside sensor is configured.
- Bed detection considers all configured bed sensors, not just the first.
- The status sensor state is cut to Home Assistant's 255 character limit.

### Added
- Presence tracker is now used: Eco while nobody is home (README promised it, the code did not do it).
- *Force Boost Mode* switch, so the Boost temperature is actually usable.
- Options for deadbands, house limit, weather compensation, low-temperature threshold, comfort offset, bed sensors, presence tracker and more.
- Hungarian translation, `trigger_ventilation` service description, service schemas.
- Unit and integration tests, GitHub Actions (hassfest, HACS, ruff, pytest).

### Changed
- The heat pump is commanded from a background task, so the update loop is never blocked for tens of seconds. Entities are updated by push instead of polling.
- The coordinator moved to `coordinator.py`, pure logic to `logic.py`, a shared base entity to `entity.py`.
- Services are registered once, validated, and removed with the last config entry.
- The heat pump entity is moved back to its original device when the integration is removed.
- The same heat pump can no longer be configured twice.
- Status messages are English only. The manifest version, `iot_class` and minimum Home Assistant version (2024.12) were corrected.
