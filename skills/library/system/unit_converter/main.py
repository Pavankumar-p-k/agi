# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from skills.utils import success_response, error_response

CONVERSIONS = {
    "length": {
        "m": 1, "km": 1000, "mile": 1609.344, "foot": 0.3048,
        "inch": 0.0254, "cm": 0.01, "yard": 0.9144,
    },
    "mass": {
        "kg": 1, "g": 0.001, "lb": 0.453592, "oz": 0.0283495, "ton": 1000,
    },
    "volume": {
        "L": 1, "mL": 0.001, "gal": 3.78541, "cup": 0.236588, "fl_oz": 0.0295735,
    },
    "speed": {
        "kmh": 1, "mph": 1.60934, "mps": 3.6, "knot": 1.852,
    },
    "area": {
        "sqm": 1, "sqft": 0.092903, "acre": 4046.86, "hectare": 10000,
    },
    "digital": {
        "B": 1, "KB": 1024, "MB": 1048576, "GB": 1073741824, "TB": 1099511627776,
    },
}

def _convert_temperature(value, from_unit, to_unit):
    if from_unit == to_unit:
        return value
    if from_unit == "C":
        kelvin = value + 273.15
    elif from_unit == "F":
        kelvin = (value - 32) * 5 / 9 + 273.15
    elif from_unit == "K":
        kelvin = value
    else:
        raise ValueError(f"Unknown temperature unit: {from_unit}")
    if to_unit == "C":
        return round(kelvin - 273.15, 4)
    elif to_unit == "F":
        return round((kelvin - 273.15) * 9 / 5 + 32, 4)
    elif to_unit == "K":
        return round(kelvin, 4)
    raise ValueError(f"Unknown temperature unit: {to_unit}")

async def unit_converter(params: dict) -> dict:
    value = params.get("value")
    from_unit = params.get("from_unit")
    to_unit = params.get("to_unit")
    category = params.get("category")
    if value is None or not from_unit or not to_unit:
        return error_response("Missing required params: value, from_unit, to_unit")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return error_response("value must be a number")
    from_unit = from_unit.lower()
    to_unit = to_unit.lower()
    if category == "temperature":
        result = _convert_temperature(value, from_unit, to_unit)
        return success_response({
            "value": value, "from_unit": from_unit,
            "result": result, "to_unit": to_unit, "category": category,
        })
    if not category or category not in CONVERSIONS:
        return error_response(f"Unknown category '{category}'. Use one of: {', '.join(CONVERSIONS)}")
    units = CONVERSIONS[category]
    if from_unit not in units:
        return error_response(f"Unknown {category} unit '{from_unit}'")
    if to_unit not in units:
        return error_response(f"Unknown {category} unit '{to_unit}'")
    base_value = value * units[from_unit]
    result = base_value / units[to_unit]
    return success_response({
        "value": value, "from_unit": from_unit,
        "result": round(result, 6), "to_unit": to_unit, "category": category,
    })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
