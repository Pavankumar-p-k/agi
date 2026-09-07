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

from datetime import datetime
from collections import defaultdict
from skills.utils import success_response, error_response

EXPENSES = []
EXPENSE_ID = 1

async def expenses(params: dict) -> dict:
    global EXPENSE_ID
    action = params.get("action", "list")
    if action == "add":
        amount = params.get("amount")
        category = params.get("category", "other")
        description = params.get("description", "")
        date = params.get("date")
        if not amount:
            return error_response("amount is required")
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return error_response("date must be in YYYY-MM-DD format")
        expense = {
            "id": EXPENSE_ID,
            "amount": float(amount),
            "category": category,
            "description": description,
            "date": date
        }
        EXPENSES.append(expense)
        EXPENSE_ID += 1
        return success_response(expense, "Expense added")
    elif action == "list":
        category_filter = params.get("category")
        items = EXPENSES
        if category_filter:
            items = [e for e in items if e["category"] == category_filter]
        return success_response({"expenses": items, "count": len(items)})
    elif action == "total":
        by_category = defaultdict(list)
        total = 0.0
        for e in EXPENSES:
            by_category[e["category"]].append(e)
            total += e["amount"]
        cat_totals = {cat: sum(e["amount"] for e in items) for cat, items in by_category.items()}
        cat_counts = {cat: len(items) for cat, items in by_category.items()}
        return success_response({
            "total": total,
            "count": len(EXPENSES),
            "by_category": {cat: {"total": cat_totals[cat], "count": cat_counts[cat]} for cat in cat_totals},
            "average_per_expense": total / len(EXPENSES) if EXPENSES else 0
        })
    elif action == "delete":
        expense_id = params.get("id")
        if expense_id is None:
            return error_response("id is required")
        for i, e in enumerate(EXPENSES):
            if e["id"] == int(expense_id):
                removed = EXPENSES.pop(i)
                return success_response(removed, "Expense deleted")
        return error_response(f"Expense with id {expense_id} not found")
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
