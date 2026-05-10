"""
dashboard/admin.py — JARVIS Admin Dashboard
=============================================
Runs on localhost:8765/admin ONLY.
Auth required via password.
Features: toggle auto-reply, presence, personality sliders,
          engagement graphs, experiment logs, intervention logs, STOP ALL.
"""
from __future__ import annotations
import hashlib, json, logging, os, time, sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, Request, HTTPException, Depends
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    _FASTAPI = True
except ImportError:
    _FASTAPI = False

from db.schema import connect, get_setting, set_setting, clamp, DB_PATH
from friends.registry import FriendRegistry
from experiments.engine import ExperimentEngine, InterventionEngine

DASHBOARD_HOST = "127.0.0.1"   # localhost only — never expose publicly
DASHBOARD_PORT = 8765

DEFAULT_PASSWORD = "jarvis2024"   # change on first run


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ══════════════════════════════════════════════════
#  FASTAPI APP
# ══════════════════════════════════════════════════

if _FASTAPI:
    app = FastAPI(title="JARVIS Admin", docs_url=None, redoc_url=None)

    # Block non-localhost requests at middleware level
    @app.middleware("http")
    async def localhost_only(request: Request, call_next):
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            return JSONResponse({"error": "Access denied"}, status_code=403)
        return await call_next(request)

    # ── Auth ──────────────────────────────────────────────────────

    def verify_token(request: Request) -> bool:
        token = request.headers.get("X-Admin-Token","") or request.cookies.get("admin_token","")
        stored_hash = get_setting("admin_password_hash", DB_PATH)
        if not stored_hash:
            # First run — set default password
            set_setting("admin_password_hash", _hash(DEFAULT_PASSWORD), DB_PATH)
            stored_hash = _hash(DEFAULT_PASSWORD)
        return token == stored_hash

    def require_auth(request: Request):
        if not verify_token(request):
            raise HTTPException(401, "Unauthorized")

    # ── Auth endpoint ─────────────────────────────────────────────

    class LoginRequest(BaseModel):
        password: str

    @app.post("/admin/login")
    async def login(body: LoginRequest):
        stored_hash = get_setting("admin_password_hash", DB_PATH)
        if not stored_hash:
            stored_hash = _hash(DEFAULT_PASSWORD)
        if _hash(body.password) == stored_hash:
            return {"token": stored_hash}
        raise HTTPException(401, "Wrong password")

    @app.post("/admin/change_password")
    async def change_password(body: LoginRequest, request: Request):
        require_auth(request)
        set_setting("admin_password_hash", _hash(body.password), DB_PATH)
        return {"ok": True}

    # ── Settings toggles ──────────────────────────────────────────

    @app.get("/admin/settings")
    async def get_settings(request: Request):
        require_auth(request)
        return {
            "auto_reply_enabled": get_setting("auto_reply_enabled", DB_PATH),
            "presence_enabled":   get_setting("presence_enabled",   DB_PATH),
            "experiment_enabled": get_setting("experiment_enabled",  DB_PATH),
            "system_paused":      get_setting("system_paused",       DB_PATH),
            "laptop_status":      get_setting("laptop_status",       DB_PATH),
        }

    @app.post("/admin/settings/{key}/{value}")
    async def update_setting(key: str, value: str, request: Request):
        require_auth(request)
        allowed = {"auto_reply_enabled","presence_enabled","experiment_enabled",
                    "system_paused","laptop_status"}
        if key not in allowed:
            raise HTTPException(400, "Unknown setting")
        set_setting(key, value, DB_PATH)
        return {"ok": True, "key": key, "value": value}

    @app.post("/admin/emergency_stop")
    async def emergency_stop(request: Request):
        require_auth(request)
        set_setting("system_paused", "true", DB_PATH)
        set_setting("auto_reply_enabled", "false", DB_PATH)
        set_setting("presence_enabled", "false", DB_PATH)
        logger.warning("[Admin] EMERGENCY STOP triggered.")
        return {"ok": True, "message": "All systems stopped."}

    @app.post("/admin/resume")
    async def resume(request: Request):
        require_auth(request)
        set_setting("system_paused", "false", DB_PATH)
        set_setting("auto_reply_enabled", "true", DB_PATH)
        set_setting("presence_enabled", "true", DB_PATH)
        return {"ok": True, "message": "Systems resumed."}

    # ── Friends ───────────────────────────────────────────────────

    @app.get("/admin/friends")
    async def list_friends(request: Request):
        require_auth(request)
        reg = FriendRegistry(DB_PATH)
        friends = reg.all_friends()
        return [{"friend_id": f.friend_id, "name": f.display_name,
                  "special": f.special_mode, "engagement": f.engagement_score,
                  "cooldown_left": f.cooldown_seconds_left,
                  "awaiting_reply": f.awaiting_reply,
                  "traits": f.traits} for f in friends]

    @app.post("/admin/friends/{friend_id}/special/{value}")
    async def set_special(friend_id: str, value: str, request: Request):
        require_auth(request)
        reg = FriendRegistry(DB_PATH)
        reg.set_special_mode(friend_id, value.lower() == "true")
        return {"ok": True}

    @app.post("/admin/friends/{friend_id}/cooldown/clear")
    async def clear_cooldown(friend_id: str, request: Request):
        require_auth(request)
        reg = FriendRegistry(DB_PATH)
        reg.clear_cooldown(friend_id)
        return {"ok": True}

    class TraitUpdate(BaseModel):
        trait: str
        value: float

    @app.post("/admin/friends/{friend_id}/trait")
    async def update_trait(friend_id: str, body: TraitUpdate, request: Request):
        require_auth(request)
        reg = FriendRegistry(DB_PATH)
        try:
            reg.update_trait(friend_id, body.trait, clamp(body.value))
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(400, str(e))

    # ── Analytics ─────────────────────────────────────────────────

    @app.get("/admin/analytics/{friend_id}")
    async def get_analytics(friend_id: str, request: Request, days: int = 7):
        require_auth(request)
        cutoff = time.time() - days * 86400
        con = connect(DB_PATH)
        rows = con.execute(
            "SELECT timestamp, sentiment, conflict_flag, engagement, emoji_density "
            "FROM metadata_logs WHERE friend_id=? AND timestamp>? ORDER BY timestamp",
            (friend_id, cutoff)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    @app.get("/admin/engagement_summary")
    async def engagement_summary(request: Request):
        require_auth(request)
        con = connect(DB_PATH)
        rows = con.execute("""
            SELECT f.display_name, pv.engagement_score,
                   pv.special_mode, pv.cooldown_until
            FROM friends f
            JOIN personality_vectors pv ON pv.friend_id=f.friend_id
            ORDER BY pv.engagement_score DESC
        """).fetchall()
        con.close()
        return [dict(r) for r in rows]

    # ── Experiments ───────────────────────────────────────────────

    @app.get("/admin/experiments")
    async def get_experiments(request: Request, friend_id: str = None):
        require_auth(request)
        engine = ExperimentEngine(DB_PATH)
        if friend_id:
            return engine.get_history(friend_id)
        con = connect(DB_PATH)
        rows = con.execute(
            "SELECT * FROM experiment_history ORDER BY started_at DESC LIMIT 50"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    # ── Interventions ─────────────────────────────────────────────

    @app.get("/admin/interventions")
    async def get_interventions(request: Request, friend_id: str = None):
        require_auth(request)
        ie = InterventionEngine(DB_PATH)
        return ie.get_logs(friend_id)

    @app.get("/admin/interventions/high_priority")
    async def high_priority_interventions(request: Request):
        require_auth(request)
        ie = InterventionEngine(DB_PATH)
        return ie.get_unresolved_high()

    @app.post("/admin/interventions/{iv_id}/resolve")
    async def resolve_intervention(iv_id: int, request: Request):
        require_auth(request)
        con = connect(DB_PATH)
        con.execute("UPDATE intervention_logs SET resolved=1 WHERE id=?", (iv_id,))
        con.commit()
        con.close()
        return {"ok": True}

    # ── Dashboard HTML ────────────────────────────────────────────

    @app.get("/admin", response_class=HTMLResponse)
    async def dashboard_html(request: Request):
        if not verify_token(request):
            return HTMLResponse(_login_page())
        return HTMLResponse(_dashboard_page())

    def _login_page() -> str:
        return """<!DOCTYPE html>
<html><head><title>JARVIS Admin</title>
<style>
  body{background:#03045E;color:#00B4D8;font-family:monospace;display:flex;
       justify-content:center;align-items:center;height:100vh;margin:0}
  .box{background:#023E8A;padding:40px;border-radius:8px;border:1px solid #00B4D8}
  h1{margin:0 0 24px;letter-spacing:3px;font-size:18px}
  input{background:#03045E;border:1px solid #00B4D8;color:#00B4D8;
        padding:10px;width:100%;box-sizing:border-box;margin-bottom:16px;font-family:monospace}
  button{background:#00B4D8;color:#03045E;border:none;padding:10px 24px;
         cursor:pointer;font-family:monospace;font-weight:bold;width:100%}
  #err{color:#ff4d6d;font-size:12px;margin-top:8px}
</style></head>
<body><div class="box">
  <h1>⬡ JARVIS ADMIN</h1>
  <input type="password" id="pw" placeholder="Password" onkeydown="if(event.key==='Enter')login()"/>
  <button onclick="login()">AUTHENTICATE</button>
  <div id="err"></div>
</div>
<script>
async function login(){
  const pw=document.getElementById('pw').value;
  const r=await fetch('/admin/login',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({password:pw})});
  if(r.ok){const d=await r.json();
    document.cookie='admin_token='+d.token+';path=/';location.reload();}
  else document.getElementById('err').textContent='Invalid password';
}
</script></body></html>"""

    def _dashboard_page() -> str:
        return """<!DOCTYPE html>
<html><head><title>JARVIS Admin</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#03045E;color:#caf0f8;font-family:monospace;padding:20px}
  h1{color:#00B4D8;letter-spacing:3px;font-size:20px;margin-bottom:20px}
  h2{color:#90E0EF;font-size:13px;letter-spacing:2px;margin:16px 0 10px;text-transform:uppercase}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
  .card{background:#023E8A;border-radius:6px;padding:16px;border:1px solid #0077B6}
  .btn{background:#00B4D8;color:#03045E;border:none;padding:8px 16px;cursor:pointer;
       font-family:monospace;font-weight:bold;font-size:11px;border-radius:4px;margin:4px}
  .btn.red{background:#ff4d6d;color:white}
  .btn.green{background:#06d6a0}
  .toggle{display:flex;align-items:center;gap:10px;margin:6px 0}
  .status{font-size:11px;padding:3px 8px;border-radius:10px}
  .on{background:#06d6a01a;color:#06d6a0;border:1px solid #06d6a0}
  .off{background:#ff4d6d1a;color:#ff4d6d;border:1px solid #ff4d6d}
  table{width:100%;border-collapse:collapse;font-size:11px}
  td,th{padding:6px 8px;border-bottom:1px solid #0077B6;text-align:left}
  th{color:#90E0EF}
  .slider-row{margin:8px 0}
  input[type=range]{width:100%;accent-color:#00B4D8}
  #friends-list{max-height:300px;overflow-y:auto}
</style></head>
<body>
<h1>⬡ JARVIS SOCIAL — ADMIN DASHBOARD</h1>

<div class="grid">

  <!-- System Controls -->
  <div class="card">
    <h2>System Controls</h2>
    <div id="status-badges"></div>
    <br>
    <button class="btn red" onclick="emergencyStop()">⛔ EMERGENCY STOP</button>
    <button class="btn green" onclick="resumeAll()">▶ RESUME ALL</button>
    <br><br>
    <div class="toggle">Auto Reply <span id="ar-status" class="status"></span>
      <button class="btn" onclick="toggleSetting('auto_reply_enabled')">Toggle</button></div>
    <div class="toggle">Presence Engine <span id="pe-status" class="status"></span>
      <button class="btn" onclick="toggleSetting('presence_enabled')">Toggle</button></div>
    <div class="toggle">Experiments <span id="ex-status" class="status"></span>
      <button class="btn" onclick="toggleSetting('experiment_enabled')">Toggle</button></div>
  </div>

  <!-- Friends -->
  <div class="card">
    <h2>Friends</h2>
    <div id="friends-list">Loading...</div>
  </div>

  <!-- Interventions -->
  <div class="card">
    <h2>⚠ Interventions (Unresolved HIGH)</h2>
    <div id="interventions">Loading...</div>
  </div>

  <!-- Experiments -->
  <div class="card">
    <h2>Experiments (Recent)</h2>
    <div id="experiments">Loading...</div>
  </div>

</div>

<script>
const token=document.cookie.split(';').find(c=>c.trim().startsWith('admin_token='))
  ?.split('=')[1]||'';
const H={'Content-Type':'application/json','X-Admin-Token':token};

async function api(url,method='GET',body=null){
  const r=await fetch(url,{method,headers:H,body:body?JSON.stringify(body):null});
  return r.json();
}

async function loadSettings(){
  const s=await api('/admin/settings');
  const badge=(k,id)=>{
    const el=document.getElementById(id);
    if(el){el.textContent=s[k]==='true'?'ON':'OFF';el.className='status '+(s[k]==='true'?'on':'off');}
  };
  badge('auto_reply_enabled','ar-status');
  badge('presence_enabled','pe-status');
  badge('experiment_enabled','ex-status');
  document.getElementById('status-badges').innerHTML=
    `<span class="status ${s.system_paused==='true'?'off':'on'}" style="font-size:12px">
      System: ${s.system_paused==='true'?'PAUSED':'RUNNING'}
    </span> &nbsp;
    <span class="status ${s.laptop_status==='online'?'on':'off'}" style="font-size:12px">
      Laptop: ${s.laptop_status}
    </span>`;
}

async function toggleSetting(key){
  const s=await api('/admin/settings');
  const cur=s[key]==='true';
  await api('/admin/settings/'+key+'/'+(cur?'false':'true'),'POST');
  loadSettings();
}

async function emergencyStop(){
  if(confirm('EMERGENCY STOP — halt all systems?')){
    await api('/admin/emergency_stop','POST');
    loadSettings();alert('Systems stopped.');
  }
}
async function resumeAll(){
  await api('/admin/resume','POST');
  loadSettings();
}

async function loadFriends(){
  const friends=await api('/admin/friends');
  const el=document.getElementById('friends-list');
  if(!friends.length){el.innerHTML='<small style="color:#90E0EF">No friends registered</small>';return;}
  el.innerHTML='<table><tr><th>Name</th><th>Eng</th><th>Special</th><th>Cooldown</th></tr>'+
    friends.map(f=>`<tr>
      <td>${f.name}</td>
      <td>${(f.engagement*100).toFixed(0)}%</td>
      <td><button class="btn" style="padding:2px 6px" onclick="toggleSpecial('${f.friend_id}',${!f.special})">
        ${f.special?'✓ YES':'NO'}</button></td>
      <td>${f.cooldown_left>0?Math.round(f.cooldown_left/3600)+'h':'Ready'}</td>
    </tr>`).join('')+'</table>';
}

async function toggleSpecial(id,val){
  await api('/admin/friends/'+id+'/special/'+val,'POST');
  loadFriends();
}

async function loadInterventions(){
  const ivs=await api('/admin/interventions/high_priority');
  const el=document.getElementById('interventions');
  if(!ivs.length){el.innerHTML='<small style="color:#06d6a0">None — all clear ✓</small>';return;}
  el.innerHTML=ivs.map(i=>`
    <div style="border-left:3px solid #ff4d6d;padding:8px;margin-bottom:8px">
      <div style="color:#ff4d6d;font-size:11px">${i.friend_id} — ${i.trigger_reason}</div>
      <div style="font-size:10px;color:#90E0EF">${i.trait_adjusted}: ${i.old_value.toFixed(2)}→${i.new_value.toFixed(2)}</div>
      <div style="font-size:10px">Manual takeover suggested</div>
      <button class="btn" style="padding:2px 6px;margin-top:4px" onclick="resolveIv(${i.id})">Resolve</button>
    </div>`).join('');
}

async function resolveIv(id){
  await api('/admin/interventions/'+id+'/resolve','POST');
  loadInterventions();
}

async function loadExperiments(){
  const exps=await api('/admin/experiments');
  const el=document.getElementById('experiments');
  if(!exps.length){el.innerHTML='<small style="color:#90E0EF">No experiments yet</small>';return;}
  el.innerHTML='<table><tr><th>Friend</th><th>Trait</th><th>Result</th><th>Eng↑</th></tr>'+
    exps.slice(0,10).map(e=>`<tr>
      <td>${e.friend_id.slice(0,12)}</td>
      <td>${e.trait_name}</td>
      <td style="color:${e.result==='kept'?'#06d6a0':e.result==='reverted'?'#ff4d6d':'#90E0EF'}">${e.result}</td>
      <td>${e.engagement_after>0?(e.engagement_after-e.engagement_before>0?'+':'')+
           ((e.engagement_after-e.engagement_before)*100).toFixed(1)+'%':'—'}</td>
    </tr>`).join('')+'</table>';
}

// Init
loadSettings();loadFriends();loadInterventions();loadExperiments();
setInterval(()=>{loadSettings();loadInterventions();},30000);
</script>
</body></html>"""


def run_dashboard(db_path: str = DB_PATH, port: int = DASHBOARD_PORT) -> None:
    if not _FASTAPI:
        print("[Admin] fastapi/uvicorn not installed. Run: pip install fastapi uvicorn")
        return
    import uvicorn
    print(f"[Admin] Dashboard at http://127.0.0.1:{port}/admin")
    print(f"[Admin] Default password: {DEFAULT_PASSWORD}")
    uvicorn.run(app, host=DASHBOARD_HOST, port=port, log_level="warning")
