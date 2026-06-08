import urllib.parse
from skills.utils import success_response, error_response

async def upi_gen(params: dict) -> dict:
    action = params.get("action", "generate")
    vpa = params.get("vpa")
    amount = params.get("amount")
    name = params.get("name", "")
    note = params.get("note", "")
    if not vpa:
        return error_response("vpa (UPI ID) is required")
    if not isinstance(vpa, str) or "@" not in vpa:
        return error_response("Invalid VPA format. Must be like user@paytm")
    if action == "generate":
        if amount is None:
            return error_response("amount is required")
        amount = float(amount)
        if amount <= 0:
            return error_response("amount must be positive")
        params_dict = {
            "pa": vpa,
            "pn": name,
            "am": str(amount),
            "tn": note,
            "cu": "INR"
        }
        query_string = urllib.parse.urlencode(params_dict)
        upi_link = f"upi://pay?{query_string}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_link)}"
        return success_response({
            "upi_link": upi_link,
            "qr_url": qr_url,
            "vpa": vpa,
            "amount": amount,
            "payee_name": name,
            "note": note
        }, "UPI payment link generated")
    elif action == "qr":
        if amount is None:
            amount = 0
        params_dict = {
            "pa": vpa,
            "pn": name,
            "am": str(float(amount)) if amount else "",
            "tn": note,
            "cu": "INR"
        }
        query_string = urllib.parse.urlencode(params_dict)
        upi_link = f"upi://pay?{query_string}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(upi_link)}"
        return success_response({
            "upi_link": upi_link,
            "qr_url": qr_url,
            "vpa": vpa
        }, "QR code URL generated")
    return error_response(f"Unknown action: {action}")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
