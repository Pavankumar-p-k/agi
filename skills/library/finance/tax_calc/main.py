from skills.utils import success_response, error_response

TAX_SLABS = {
    "us": {
        "single": [
            (0, 11600, 0.10), (11601, 47150, 0.12), (47151, 100525, 0.22),
            (100526, 191950, 0.24), (191951, 243725, 0.32), (243726, 609350, 0.35), (609351, float("inf"), 0.37)
        ],
        "married": [
            (0, 23200, 0.10), (23201, 94300, 0.12), (94301, 201050, 0.22),
            (201051, 383900, 0.24), (383901, 487450, 0.32), (487451, 731200, 0.35), (731201, float("inf"), 0.37)
        ],
        "head_of_household": [
            (0, 16550, 0.10), (16551, 63100, 0.12), (63101, 100500, 0.22),
            (100501, 191950, 0.24), (191951, 243700, 0.32), (243701, 609350, 0.35), (609351, float("inf"), 0.37)
        ]
    },
    "uk": {
        "single": [
            (0, 12570, 0.0), (12571, 50270, 0.20), (50271, 125140, 0.40), (125141, float("inf"), 0.45)
        ]
    },
    "in": {
        "single": [
            (0, 300000, 0.0), (300001, 600000, 0.05), (600001, 900000, 0.10),
            (900001, 1200000, 0.15), (1200001, 1500000, 0.20), (1500001, float("inf"), 0.30)
        ]
    }
}
STANDARD_DEDUCTION = {"us": 14600, "uk": 12570, "in": 0}

async def tax_calc(params: dict) -> dict:
    income = params.get("income")
    country = (params.get("country", "us")).lower()
    filing_status = params.get("filing_status", "single")
    year = params.get("year", 2024)
    deductions = params.get("deductions", 0)
    if not income:
        return error_response("income is required")
    income = float(income)
    deductions = float(deductions)
    slabs_dict = TAX_SLABS.get(country)
    if not slabs_dict:
        return error_response(f"Unsupported country: {country}")
    slabs = slabs_dict.get(filing_status)
    if not slabs:
        slabs = slabs_dict.get("single")
    std_ded = STANDARD_DEDUCTION.get(country, 0)
    total_deductions = deductions + std_ded
    taxable_income = max(0, income - total_deductions)
    total_tax = 0.0
    bracket_details = []
    for low, high, rate in slabs:
        if taxable_income > low:
            bracket_income = min(taxable_income, high) - low
            bracket_tax = bracket_income * rate
            if bracket_income > 0:
                bracket_details.append({
                    "from": low, "to": min(high, taxable_income),
                    "rate": f"{int(rate * 100)}%",
                    "taxable_in_bracket": round(bracket_income, 2),
                    "tax": round(bracket_tax, 2)
                })
            total_tax += bracket_tax
        if taxable_income <= high:
            break
    effective_rate = (total_tax / income * 100) if income > 0 else 0
    marginal_rate = 0
    for low, high, rate in slabs:
        if low < taxable_income <= high:
            marginal_rate = rate * 100
            break
        if low < taxable_income and high == float("inf"):
            marginal_rate = rate * 100
            break
    return success_response({
        "country": country, "year": year, "filing_status": filing_status,
        "gross_income": income, "standard_deduction": std_ded,
        "additional_deductions": deductions, "taxable_income": round(taxable_income, 2),
        "total_tax": round(total_tax, 2), "effective_tax_rate": round(effective_rate, 2),
        "marginal_tax_rate": f"{int(marginal_rate)}%",
        "tax_breakdown": bracket_details,
        "take_home": round(income - total_tax, 2)
    })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
