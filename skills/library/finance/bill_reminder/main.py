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

from datetime import datetime, date
from skills.utils import success_response, error_response

BILLS = []

async def bill_reminder(params: dict) -> dict:
    action = params.get("action", "list")
    if action == "add":
        name = params.get("name")
        amount = params.get("amount")
        due_date = params.get("due_date")
        category = params.get("category", "other")
        paid = params.get("paid", False)
        if not all([name, amount, due_date]):
            return error_response("name, amount, and due_date are required")
        try:
            parsed_due = datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            return error_response("due_date must be in YYYY-MM-DD format")
        bill = {
            "id": len(BILLS) + 1,
            "name": name,
            "amount": float(amount),
            "due_date": due_date,
            "category": category,
            "paid": paid
        }
        BILLS.append(bill)
        return success_response(bill, "Bill added successfully")
    elif action == "list":
        today = date.today()
        enriched = []
        for b in BILLS:
            due = datetime.strptime(b["due_date"], "%Y-%m-%d").date()
            b_copy = dict(b)
            b_copy["overdue"] = not b["paid"] and due < today
            b_copy["days_until_due"] = (due - today).days
            enriched.append(b_copy)
        return success_response({"bills": enriched, "total": len(enriched), "overdue_count": sum(1 for b in enriched if b["overdue"])})
    elif action == "due-soon":
        days = params.get("days", 7)
        today = date.today()
        upcoming = []
        for b in BILLS:
            due = datetime.strptime(b["due_date"], "%Y-%m-%d").date()
            if not b["paid"] and 0 <= (due - today).days <= days:
                b_copy = dict(b)
                b_copy["days_until_due"] = (due - today).days
                upcoming.append(b_copy)
        return success_response({"due_soon": upcoming, "count": len(upcoming)})
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
