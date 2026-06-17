DOMAIN = "dash"

# If no reading is received for this many seconds, the current trip is considered ended
TRIP_GAP_SECONDS = 300  # 5 minutes

# Coolant temperature thresholds (°C)
COOLANT_HOT_C = 110
COOLANT_CRITICAL_C = 120

# Battery/control module voltage thresholds (V, engine running)
VOLTAGE_LOW_V = 13.5
VOLTAGE_CRITICAL_V = 12.0
VOLTAGE_HIGH_V = 15.0

# Fuel level thresholds (%)
FUEL_LOW_PCT = 15
FUEL_CRITICAL_PCT = 5
