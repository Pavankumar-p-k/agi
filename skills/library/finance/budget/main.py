from skills.utils import success_response, error_response

BUDGETS = {}
SPENDING = {}

async def budget(params: dict) -> dict:
    action = params.get("action", "status")
    category = params.get("category")
    amount = params.get("amount")
    month = params.get("month")

    if action == "set":
        if not all([category, amount, month]):
            return error_response("category, amount, and month are required")
        if category not in ("food", "transport", "shopping", "bills", "entertainment", "other", "rent", "utilities", "subscription", "insurance", "loan"):
            return error_response(f"Invalid category: {category}")
        key = f"{month}:{category}"
        BUDGETS[key] = float(amount)
        if key not in SPENDING:
            SPENDING[key] = 0.0
        return success_response({"month": month, "category": category, "budget": float(amount)}, "Budget set")
    elif action == "spend":
        if not all([category, amount, month]):
            return error_response("category, amount, and month are required")
        key = f"{month}:{category}"
        SPENDING[key] = SPENDING.get(key, 0.0) + float(amount)
        budget_limit = BUDGETS.get(key)
        total = SPENDING[key]
        if budget_limit and total > budget_limit:
            return success_response({
                "month": month, "category": category, "spent": total,
                "budget": budget_limit, "overspent": total - budget_limit
            }, f"Overspent by {total - budget_limit:.2f}")
        return success_response({"month": month, "category": category, "spent": total}, "Expense recorded")
    elif action == "status":
        if not month:
            return error_response("month is required")
        categories = {}
        total_budget = 0.0
        total_spent = 0.0
        for key, budget_limit in BUDGETS.items():
            k_month, k_cat = key.split(":", 1)
            if k_month == month:
                spent = SPENDING.get(key, 0.0)
                categories[k_cat] = {
                    "budget": budget_limit,
                    "spent": spent,
                    "remaining": budget_limit - spent,
                    "overspent": max(0, spent - budget_limit)
                }
                total_budget += budget_limit
                total_spent += spent
        return success_response({
            "month": month, "categories": categories,
            "total_budget": total_budget, "total_spent": total_spent,
            "total_remaining": total_budget - total_spent,
            "alerts": [f"Over budget in {c}" for c, v in categories.items() if v["overspent"] > 0]
        })
    elif action == "reset":
        month = params.get("month")
        category = params.get("category")
        if month and category:
            key = f"{month}:{category}"
            BUDGETS.pop(key, None)
            SPENDING.pop(key, None)
            return success_response({}, f"Reset {category} for {month}")
        elif month:
            keys = [k for k in BUDGETS if k.startswith(f"{month}:")]
            for k in keys:
                BUDGETS.pop(k, None)
                SPENDING.pop(k, None)
            return success_response({}, f"Reset all budgets for {month}")
        return error_response("month is required")
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
