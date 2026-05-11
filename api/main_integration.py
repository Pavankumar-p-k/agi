# main_integration.py
"""
ADD THESE 3 THINGS TO YOUR EXISTING main.py
Nothing else needs to change.
"""

# ── 1. Import at top of main.py ──────────────────────────────
from api.vision_routes import router as vision_router, init_agents

# ── 2. Register route (with your existing app.include_router calls) ──
app.include_router(vision_router)

# ── 3. Start vision agent on startup (inside your existing startup function) ──
@app.on_event("startup")
async def on_startup():
    # ... your existing startup code ...
    brain = get_brain()
    await brain.startup()

    # ADD THIS:
    await init_agents()
    print("[Main] Vision Agent ready [OK]")


# ─────────────────────────────────────────────────────────────
# HOOKING VISION INTO CHAT (OPTIONAL)
# If user says "jarvis do X" in chat, route to vision agent
# ─────────────────────────────────────────────────────────────

from api.vision_routes import _execute as vision_execute

@app.post("/api/chat")
async def chat(body: dict):
    msg = body.get("message","")

    # Check if this is a "do something on screen" command
    VISION_TRIGGERS = [
        "open chrome", "open instagram", "open whatsapp", "go to amazon",
        "search amazon", "buy ", "order ", "send message", "send msg",
        "open youtube", "play ", "share photo", "delete photos",
        "open photos", "open gallery", "google search", "send email",
    ]
    is_vision = any(trigger in msg.lower() for trigger in VISION_TRIGGERS)

    if is_vision:
        # Route to Vision Agent
        result = await vision_execute(f"v_{int(time.time())}", msg, "pc")
        return {
            "response": f"Done! {result.get('result', 'Task completed')}",
            "vision_task": result,
        }

    # Otherwise use normal brain
    brain_result = await get_brain().think(Message(text=msg))
    return {"response": brain_result.reply}
