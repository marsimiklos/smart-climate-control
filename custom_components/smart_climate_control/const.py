DOMAIN = "smart_climate_control"

CONF_HEAT_PUMP = "heat_pump"
CONF_ROOM_SENSOR = "room_sensor"
CONF_OUTSIDE_SENSOR = "outside_sensor"
CONF_AVERAGE_SENSOR = "average_sensor"
CONF_HEAT_PUMP_CONTACT = "heat_pump_contact"
CONF_DOOR_SENSOR = "door_sensor"
CONF_WINDOW_SENSORS = "window_sensors"
CONF_WINDOW_DELAY = "window_delay"
CONF_BED_SENSORS = "bed_sensors"
CONF_PRESENCE_TRACKER = "presence_tracker"
CONF_COMFORT_TEMP = "comfort_temp"
CONF_ECO_TEMP = "eco_temp"
CONF_BOOST_TEMP = "boost_temp"
CONF_COOLING_TEMP = "cooling_temp"
CONF_DEADBAND_BELOW = "deadband_below"
CONF_DEADBAND_ABOVE = "deadband_above"
CONF_MAX_HOUSE_TEMP = "max_house_temp"
CONF_WEATHER_COMP_FACTOR = "weather_comp_factor"
CONF_MAX_COMP_TEMP = "max_comp_temp"
CONF_MIN_COMP_TEMP = "min_comp_temp"
CONF_COMFORT_OFFSET = "comfort_temp_offset"
CONF_MIN_RUN_TIME = "min_run_time"
CONF_LOW_TEMP_THRESHOLD = "low_temp_threshold"
CONF_SAFETY_CUTOFF = "safety_cutoff"

# Ventilation Constants
CONF_FAN_GROUP_A = "fan_group_a"
CONF_FAN_GROUP_B = "fan_group_b"
CONF_HUMIDITY_SENSOR_A = "humidity_sensor_a"
CONF_HUMIDITY_SENSOR_B = "humidity_sensor_b"
CONF_VENT_CYCLE_TIME = "vent_cycle_time"        # Time in seconds for one direction
CONF_VENT_DURATION = "vent_duration"            # Duration of a standard run in minutes
CONF_VENT_MAX_DURATION = "vent_max_duration"    # Max safety duration in minutes
CONF_HUMIDITY_THRESHOLD = "humidity_threshold"  # RH% threshold to trigger ventilation
CONF_VENT_AUTO_INTERVAL = "vent_auto_interval"  # Hours between auto runs

DEFAULT_COMFORT_TEMP = 20.0
DEFAULT_ECO_TEMP = 18.0
DEFAULT_BOOST_TEMP = 23.0
DEFAULT_COOLING_TEMP = 22.0
DEFAULT_DEADBAND = 0.5
DEFAULT_MAX_HOUSE_TEMP = 25.0
DEFAULT_WEATHER_COMP_FACTOR = 0.5
DEFAULT_MAX_COMP_TEMP = 25.0
DEFAULT_MIN_COMP_TEMP = 16.0
DEFAULT_COMFORT_OFFSET = 0.5
DEFAULT_MIN_RUN_TIME = 30
DEFAULT_LOW_TEMP_THRESHOLD = 5.0
DEFAULT_SAFETY_CUTOFF = 1.0
DEFAULT_WINDOW_DELAY = 1.0

# Ventilation Defaults
DEFAULT_VENT_CYCLE_TIME = 75      # seconds
DEFAULT_VENT_DURATION = 60        # minutes
DEFAULT_VENT_MAX_DURATION = 120   # minutes
DEFAULT_HUMIDITY_THRESHOLD = 60.0 # RH%
DEFAULT_VENT_AUTO_INTERVAL = 12   # hours