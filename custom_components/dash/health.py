from .const import (
    COOLANT_HOT_C, COOLANT_CRITICAL_C,
    VOLTAGE_LOW_V, VOLTAGE_CRITICAL_V, VOLTAGE_HIGH_V,
    FUEL_LOW_PCT, FUEL_CRITICAL_PCT,
)


def calculate_health_score(reading: dict) -> tuple[int, dict]:
    score = 100
    breakdown = {}

    coolant = reading.get("coolant_temp")
    if coolant is not None:
        if coolant > COOLANT_CRITICAL_C:
            score -= 30
            breakdown["coolant"] = {"label": "Engine Overheating", "value": f"{coolant:.0f}°C", "level": "critical"}
        elif coolant > COOLANT_HOT_C:
            score -= 15
            breakdown["coolant"] = {"label": "Running Hot", "value": f"{coolant:.0f}°C", "level": "warning"}

    voltage = reading.get("voltage")
    if voltage is not None:
        if voltage < VOLTAGE_CRITICAL_V:
            score -= 25
            breakdown["voltage"] = {"label": "Battery Critical", "value": f"{voltage:.1f}V", "level": "critical"}
        elif voltage < VOLTAGE_LOW_V:
            score -= 10
            breakdown["voltage"] = {"label": "Charging System Low", "value": f"{voltage:.1f}V", "level": "warning"}
        elif voltage > VOLTAGE_HIGH_V:
            score -= 15
            breakdown["voltage"] = {"label": "Voltage Overcharge", "value": f"{voltage:.1f}V", "level": "warning"}

    fuel = reading.get("fuel_level")
    if fuel is not None:
        if fuel < FUEL_CRITICAL_PCT:
            score -= 20
            breakdown["fuel"] = {"label": "Fuel Critical", "value": f"{fuel:.0f}%", "level": "critical"}
        elif fuel < FUEL_LOW_PCT:
            score -= 10
            breakdown["fuel"] = {"label": "Fuel Low", "value": f"{fuel:.0f}%", "level": "warning"}

    return max(0, min(100, score)), breakdown
