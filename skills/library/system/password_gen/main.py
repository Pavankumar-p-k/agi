import random
import string
from skills.utils import success_response

async def password_gen(params: dict) -> dict:
    """Generate a secure password."""
    length = int(params.get("length", 16))
    use_symbols = params.get("symbols", True)
    
    chars = string.ascii_letters + string.digits
    if use_symbols:
        chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    pwd = "".join(random.choice(chars) for _ in range(length))
    return success_response({"password": pwd, "length": length})

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
