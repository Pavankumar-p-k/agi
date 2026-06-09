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
# backend/automation/routes.py
#
# Add these routes to your existing core/main.py FastAPI app
# They expose all automation features via REST API

from fastapi import APIRouter, Depends, Body
from typing import Optional
from .pc_automation import (
    execute_command, contacts_db, browser, launch_app,
    wa, ig, sys_ctrl, SITE_MAP, APP_MAP
)

router = APIRouter(prefix="/api/automation", tags=["automation"])


# ── Execute any natural language command ──────────────────
@router.post("/command")
async def run_command(body: dict = Body(...)):
    """
    POST { "command": "send whatsapp to Rahul saying hello" }
    Returns { action, success, speech, ...extras }
    """
    command = body.get("command","")
    if not command:
        return {"success": False, "speech": "No command provided."}
    return execute_command(command)


# ── Contacts CRUD ─────────────────────────────────────────
@router.get("/contacts")
async def list_contacts():
    return contacts_db.list_all()

@router.get("/contacts/search")
async def search_contacts(q: str):
    return contacts_db.search(q)

@router.post("/contacts")
async def add_contact(body: dict = Body(...)):
    """
    POST { name, phone?, whatsapp?, instagram?, email?, notes? }
    """
    name = body.get("name","").strip()
    if not name:
        return {"success": False, "error": "Name required"}
    contact = contacts_db.add(
        name=name,
        phone=body.get("phone",""),
        whatsapp=body.get("whatsapp",""),
        instagram=body.get("instagram",""),
        email=body.get("email",""),
        notes=body.get("notes",""),
    )
    return {"success": True, "contact": contact}

@router.delete("/contacts/{name}")
async def delete_contact(name: str):
    ok = contacts_db.delete(name)
    return {"success": ok, "deleted": name}


# ── WhatsApp ──────────────────────────────────────────────
@router.post("/whatsapp/send")
async def send_whatsapp(body: dict = Body(...)):
    """
    POST { "contact": "Rahul", "message": "I'll be late" }
    Contact can be a name (looks up JARVIS contacts) or phone number.
    """
    contact = body.get("contact","")
    message = body.get("message","")
    if not contact or not message:
        return {"success": False, "error": "contact and message required"}

    # Check if it looks like a phone number
    if re.match(r"^[+\d]", contact):
        result = wa.send_by_number(contact, message)
    else:
        result = wa.send_to_contact(contact, message)
    return result

import re


# ── Instagram ─────────────────────────────────────────────
@router.post("/instagram/send")
async def send_instagram(body: dict = Body(...)):
    """
    POST { "contact": "john_doe or 'John' (saved contact)", "message": "hi" }
    """
    contact = body.get("contact","")
    message = body.get("message","")
    if not contact or not message:
        return {"success": False, "error": "contact and message required"}
    c = contacts_db.get(contact)
    if c and c.get("instagram"):
        return ig.send_to_contact(contact, message)
    return ig.send(contact, message)


# ── Browser / Web ─────────────────────────────────────────
@router.post("/browser/open")
async def open_url(body: dict = Body(...)):
    """POST { "url": "https://..." }"""
    url = body.get("url","")
    if not url: return {"success": False}
    browser.open(url)
    return {"success": True, "url": url}

@router.post("/browser/google")
async def google_search(body: dict = Body(...)):
    """POST { "query": "Python tutorials" }"""
    q = body.get("query","")
    browser.google(q)
    return {"success": True, "query": q}

@router.post("/browser/youtube")
async def youtube(body: dict = Body(...)):
    """POST { "query": "Coldplay music", "autoplay": true }"""
    q = body.get("query","")
    if body.get("autoplay", False):
        browser.youtube_play(q)
    else:
        browser.youtube_search(q)
    return {"success": True, "query": q}

@router.post("/browser/maps")
async def maps_search(body: dict = Body(...)):
    """POST { "place": "Connaught Place Delhi" }"""
    place = body.get("place","")
    browser.maps(place)
    return {"success": True, "place": place}

@router.get("/browser/sites")
async def list_sites():
    """Get all pre-configured site shortcuts."""
    return {"sites": list(SITE_MAP.keys())}


# ── App launcher ──────────────────────────────────────────
@router.post("/apps/launch")
async def open_app(body: dict = Body(...)):
    """POST { "app": "spotify" }"""
    app = body.get("app","")
    return launch_app(app)

@router.get("/apps/list")
async def list_apps():
    return {"apps": list(APP_MAP.keys())}


# ── System control ────────────────────────────────────────
@router.post("/system/screenshot")
async def screenshot():
    path = sys_ctrl.screenshot()
    return {"success": True, "path": path}

@router.post("/system/volume")
async def volume(body: dict = Body(...)):
    """POST { "action": "up"/"down"/"mute", "steps": 2 }"""
    action = body.get("action","up")
    steps  = body.get("steps", 2)
    if action == "up":   sys_ctrl.vol_up(steps)
    elif action == "down": sys_ctrl.vol_down(steps)
    elif action == "mute": sys_ctrl.mute()
    return {"success": True, "action": action}

@router.post("/system/lock")
async def lock_screen():
    sys_ctrl.lock()
    return {"success": True}

@router.post("/system/sleep")
async def sleep_pc():
    sys_ctrl.sleep()
    return {"success": True}

@router.post("/system/shutdown")
async def shutdown_pc(body: dict = Body(...)):
    delay = body.get("delay", 60)
    sys_ctrl.shutdown(delay)
    return {"success": True, "in_seconds": delay}

@router.post("/system/cancel_shutdown")
async def cancel_shutdown():
    sys_ctrl.cancel_shutdown()
    return {"success": True}


# ── Add to your main.py ───────────────────────────────────
# from automation.routes import router as automation_router
# app.include_router(automation_router)
