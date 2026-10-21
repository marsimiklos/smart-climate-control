# Smart Climate Control for Home Assistant

[![Validate](https://github.com/marsimiklos/smart-climate-control/actions/workflows/validate.yml/badge.svg)](https://github.com/marsimiklos/smart-climate-control/actions/workflows/validate.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

A native Home Assistant integration that runs your heat pump / air conditioner and heat recovery ventilation (HRV) with a bit of intelligence: deadband control, weather compensation, solar surplus storage, presence and sleep detection, free cooling and humidity-driven ventilation.

It started as a Node-RED flow and was rebuilt as an integration, so everything is configured from the Home Assistant UI instead of by editing flows.

This is a fork of [smartthings54/smart-climate-control](https://github.com/smartthings54/smart-climate-control) that has since been heavily reworked: the control logic was restructured, several bugs were fixed, the documented presence and boost features were actually implemented, and tests and CI were added. See the [changelog](CHANGELOG.md). The name and entity names are unchanged, so it can replace the original in place.

> Most of the code was written with the help of AI. My part is integration, testing, and making it work in my own setup. Please test it with your hardware before relying on it.

![Overview](docs/images/smart-climate-overview.png)

## Features

**Temperature control**

- Heating and cooling with **AUTO** mode (picks heat or cool from the outside temperature, falls back to the room temperature)
- Deadband control to prevent rapid cycling, plus minimum run time and minimum off time for the compressor
- Presets: Comfort, Eco and Boost for heating, Comfort and Eco for cooling
- **Weekly schedule with learned pre-heating**: comfort while a Home Assistant `schedule` is on, eco while it is off, and the house is warm *when* the schedule turns on (see below)
- Weather compensation for freezing days (heating only)
- Whole-house maximum temperature safety limit (heating)

**Diagnostics and statistics**

- Daily runtime, number of on/off cycles, average run length and estimated electric energy (usable in the Energy dashboard)
- A diagnosis sensor that tells you when the heat pump is short-cycling, so you know the deadband is too small
- The learned heating rate of your house per outside temperature

**Solar sync ("thermal battery")**

- Uses surplus solar power to shift the target by a configurable offset
- Two levels: *base* (run at the normal target) and *offset* (run with the shifted target), with a delay before dropping back

**Ventilation (HRV)**

- Two fan groups that alternate direction, scheduled runs, and humidity-triggered runs
- Humidity lock: if only one side is humid, the direction is fixed to extract it fast (disabled below 15 °C outside to keep heat recovery efficient)
- Auto free cooling: pulls in cooler outside air instead of running the compressor
- Manual airout in a chosen direction
- Periodic fan circulation while cooling is idle

**Smart home integration**

- Presence tracker: switches to Eco when nobody is home
- Bed sensors: switches to Eco while sleeping (heating only)
- Window / door sensors: pauses the HVAC after a delay and restores it after a cool-down
- Heat pump contact sensor: verifies a (for example IR controlled) unit is really running

## Requirements

- Home Assistant 2024.12 or newer
- HACS (recommended)
- A `climate` entity for the heat pump / air conditioner
- A room temperature sensor

Everything else (outside sensor, solar, fans, presence, ...) is optional.

## Installation

### HACS (recommended)

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/marsimiklos/smart-climate-control` as category **Integration**
3. Search for **Smart Climate Control**, download it and restart Home Assistant

### Manual

Copy `custom_components/smart_climate_control` to `config/custom_components/` and restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → Smart Climate Control**, then pick your entities. Most settings can be changed later under **Configure** on the integration.

| Entity | Required | Used for |
| --- | --- | --- |
| Heat pump (`climate`) | yes | The device that is controlled |
| Room temperature sensor | yes | Deadband control |
| Outside temperature sensor | no | AUTO mode, weather compensation, free cooling, humidity lock |
| Average house temperature sensor | no | House temperature safety limit |
| Window / door sensors | no | Pause the HVAC while open |
| Heat pump contact sensor | no | Verify the unit is running |
| Presence tracker | no | Eco when away (`person`, `device_tracker`, `binary_sensor`, `input_boolean`, `group`) |
| Bed sensors | no | Eco while sleeping |
| Solar production sensor (W) / consumption sensor (W) | no | Solar sync |
| Schedule (`schedule` helper) | no | Comfort / eco times and pre-heating |
| Heat pump power sensor (W) | no | Real energy statistics (otherwise the *rated power* from the options is used) |
| Fan groups and humidity sensors | no | Ventilation |

The heat pump entity is shown under the integration's device. The original assignment is restored if you remove the integration.

## Entities

The names below assume the default name `Smart Climate`.

| Platform | Entities |
| --- | --- |
| `climate` | Thermostat with OFF / HEAT / COOL / AUTO |
| `switch` | Climate Management, Force Comfort Mode, Force Eco Mode, Force Boost Mode, Force Heating, Schedule Control, Preheat, Auto Free Cooling, Solar Sync, Periodic Fan Circulation, Ventilation Enabled, Ventilation Manual Run, Airout |
| `select` | Operating Mode (auto / heat / cool), Airout Direction |
| `sensor` | Status, Mode, Target, Active Logic, Ventilation Status, Runtime Today, Cycles Today, Estimated Energy Today, Average Run Length Today, Cycle Diagnosis, Learned Heating Rate, Preheat Start |
| `number` | Boost / Comfort / Eco / Cooling / Cooling Eco temperatures, humidity threshold, ventilation timings and speed, airout and free cooling limits, solar thresholds, offset and delay |

### Which target is used

From highest to lowest priority: **Boost** (heating only) → **Force Comfort** → **Force Eco**, **sleeping**, **away** or **schedule off** → **Comfort** (also while **pre-heating**).

HEAT, COOL and AUTO all use the deadband. **Force Heating** is a separate switch: it keeps heating continuously at the current target and ignores the deadband (the house temperature limit, the window pause and the compressor minimum times still apply).

## Schedule and pre-heating

Create a schedule helper (**Settings → Devices & services → Helpers → Schedule**) with the times you want the house comfortable, and select it in the integration options.

- Schedule **on** → comfort target. Schedule **off** → eco target.
- Shortly before the schedule turns on, heating starts early so the room *reaches* the comfort temperature at that moment. The start time is `time = (comfort − room) / heating rate × 1.1`, capped by *Maximum pre-heat time* (default 180 min). The **Preheat Start** sensor shows the predicted start.
- The **heating rate** (°C/h) is learned from your own house: whenever the heat pump runs for at least 20 minutes with a real gap to the target, the observed temperature rise is stored in a moving average per outside temperature range. Until something has been learned, 1 °C/h is assumed, so the first mornings start a bit early or late. Use the **Learned Heating Rate** sensor to follow it.
- Pre-heating is skipped when nobody is home, when heating is not the active mode, or when the **Preheat** switch is off. Switch **Schedule Control** off to ignore the schedule completely. If the schedule entity is unavailable, the normal behaviour continues.
- Other rules still win: Boost, Force Comfort and Force Eco override the schedule.

## Statistics and diagnosis

- **Runtime Today / Cycles Today / Average Run Length Today** are reset at midnight. Yesterday and the last 14 days are in the sensor attributes.
- **Estimated Energy Today** uses the heat pump power sensor if you set one, otherwise the *average power when running* from the options. Without either it is unavailable.
- **Cycle Diagnosis** is `short_cycling` when, over yesterday and today, there are at least 4 cycles with an average run shorter than 10 minutes. Then increase the deadband or the minimum run time.

## Services

| Service | Description |
| --- | --- |
| `smart_climate_control.force_eco` | Force eco mode (`enable`: true / false) |
| `smart_climate_control.force_comfort` | Force comfort mode (`enable`: true / false) |
| `smart_climate_control.reset_temperatures` | Reset all temperature presets to their defaults |
| `smart_climate_control.trigger_ventilation` | Start a ventilation cycle now (optional `duration` in minutes) |

## How it works

The HVAC logic runs every 60 seconds and immediately (debounced to once per 5 s) when a configured sensor changes. Ventilation is checked every 2 seconds.

1. **Mode**: AUTO resolves to cooling above 22 °C outside, heating below 16 °C, and in between to cooling only if the room is at or above the cooling target.
2. **Target**: presets, presence, sleep, solar offset and weather compensation are applied.
3. **Deadband**:
   - Heating turns on at `target − deadband below` and off at `target + deadband above`.
   - Cooling turns on at `target + deadband above` and off at `target − deadband below`.
4. **Protections**: boot delay after Home Assistant starts, minimum run time, minimum off time, window / door pause.
5. **Ventilation**: free cooling, humidity, scheduled runs and airout, in that order of priority.

Commands to the heat pump are retried in the background (up to three times with a state check), so a slow device never blocks the control loop.

![Deadbands](docs/images/deadbands.jpg)

## Dashboard example

```yaml
type: vertical-stack
cards:
  - type: thermostat
    entity: climate.smart_climate
  - type: entities
    entities:
      - sensor.smart_climate_status
      - sensor.smart_climate_mode
      - switch.smart_climate_climate_management
      - switch.smart_climate_solar_sync
      - switch.smart_climate_auto_free_cooling
```

## Troubleshooting

**The system is not heating / cooling**

1. Is the **Climate Management** switch on?
2. Is a window / door sensor open (or in its restore cool-down)?
3. Read the **Status** sensor. It states the reason (deadband, minimum run / off time, boot delay, ...).
4. Check that Solar Sync is not shifting the target.

**Ventilation is stuck in one direction**

1. Is an airout or free cooling run active?
2. Is the humidity threshold exceeded on only one side while it is warmer than 15 °C outside? Then the direction is locked on purpose.

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check .
```

The decision logic that does not need Home Assistant lives in `custom_components/smart_climate_control/logic.py` and is covered by unit tests.

## Support

- [Issues](https://github.com/marsimiklos/smart-climate-control/issues)
- [Discussions](https://github.com/marsimiklos/smart-climate-control/discussions)

## License

MIT, see [LICENSE](LICENSE).
