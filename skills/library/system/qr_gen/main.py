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

import base64
import io
import urllib.parse
from skills.utils import success_response, error_response

async def qr_gen(params: dict) -> dict:
    data = params.get("data")
    if not data:
        return error_response("Missing required param: data")
    size = params.get("size", 200)
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        return success_response({
            "data_url": f"data:image/png;base64,{b64}",
            "format": "png",
            "size": size,
            "library": "qrcode",
        })
    except ImportError:
        encoded = urllib.parse.quote(data)
        url = f"https://chart.googleapis.com/chart?chs={size}x{size}&cht=qr&chl={encoded}"
        return success_response({
            "data_url": url,
            "format": "url",
            "size": size,
            "library": "google-charts",
            "note": "qrcode library not installed. Install with: pip install qrcode[pil]",
        })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
