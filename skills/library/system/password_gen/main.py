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
