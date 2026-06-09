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
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.hardware_advisor import get_recommended_models, list_installed_models, pull_model_ollama, scan_hardware

router = APIRouter(prefix="/cookbook", tags=["cookbook"])

@router.get("/hardware")
async def get_hardware():
    return scan_hardware()

@router.get("/models")
async def get_models():
    hw = scan_hardware()
    # Use vram_free_gb if available, otherwise total vram
    vram = hw.get("vram_free_gb") or hw.get("vram_total_gb", 4.0)
    return {
        "hardware": hw,
        "models": get_recommended_models(vram)
    }

@router.post("/pull")
async def pull_model(body: dict):
    """Stream ollama pull output."""
    model_name = body.get("model_name", "")
    if not model_name:
        raise HTTPException(400, "model_name required")

    async def generate():
        async for line in pull_model_ollama(model_name):
            yield line + "\n"

    return StreamingResponse(generate(), media_type="text/plain")

@router.get("/installed")
async def get_installed():
    return {"models": list_installed_models()}
