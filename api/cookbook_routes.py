from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from core.hardware_advisor import scan_hardware, get_recommended_models, pull_model_ollama, list_installed_models

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
