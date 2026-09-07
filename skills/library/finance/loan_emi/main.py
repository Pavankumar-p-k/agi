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

async def loan_emi(params: dict) -> dict:
    principal = params.get("principal")
    rate = params.get("rate")
    tenure = params.get("tenure")
    tenure_unit = params.get("tenure_unit", "months")
    action = params.get("action", "calculate")
    if not all([principal, rate, tenure]):
        return error_response("principal, rate, and tenure are required")
    principal = float(principal)
    annual_rate = float(rate)
    tenure = int(tenure)
    if principal <= 0 or annual_rate < 0 or tenure <= 0:
        return error_response("principal, rate, and tenure must be positive")
    if tenure_unit == "years":
        n = tenure * 12
    else:
        n = tenure
    monthly_rate = annual_rate / (12 * 100)
    if monthly_rate == 0:
        emi = principal / n
    else:
        emi = principal * monthly_rate * ((1 + monthly_rate) ** n) / (((1 + monthly_rate) ** n) - 1)
    total_payment = emi * n
    total_interest = total_payment - principal
    if action == "calculate":
        return success_response({
            "principal": principal,
            "annual_rate": annual_rate,
            "tenure_months": n,
            "monthly_emi": round(emi, 2),
            "total_interest": round(total_interest, 2),
            "total_payment": round(total_payment, 2),
            "interest_to_principal_ratio": round(total_interest / principal * 100, 2) if principal else 0
        })
    elif action == "amortization":
        schedule = []
        remaining = principal
        for i in range(1, n + 1):
            interest_part = remaining * monthly_rate
            principal_part = emi - interest_part
            remaining -= principal_part
            schedule.append({
                "month": i,
                "emi": round(emi, 2),
                "principal": round(principal_part, 2),
                "interest": round(interest_part, 2),
                "balance": round(max(remaining, 0), 2)
            })
        return success_response({
            "principal": principal,
            "annual_rate": annual_rate,
            "tenure_months": n,
            "monthly_emi": round(emi, 2),
            "total_interest": round(total_interest, 2),
            "total_payment": round(total_payment, 2),
            "schedule": schedule
        })
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
