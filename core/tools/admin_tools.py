import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from core.tools._tool_utils import MAX_OUTPUT_CHARS, MAX_READ_CHARS, _parse_tool_args, get_mcp_manager

logger = logging.getLogger(__name__)


# Endpoint management

def _do_manage_endpoints_sync(content: str, owner: Optional[str] = None) -> Dict:
    from core.database_models import SessionLocal, ModelEndpoint
    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = args.get("action", "list")
    db = SessionLocal()
    try:
        if action == "list":
            eps = db.query(ModelEndpoint).all()
            items = [{"id": e.id, "name": e.name, "base_url": e.base_url,
                       "is_enabled": e.is_enabled} for e in eps]
            return {"response": f"{len(items)} endpoints", "endpoints": items, "exit_code": 0}

        elif action == "add":
            import uuid as _uuid
            name = args.get("name", "")
            base_url = args.get("base_url", "")
            api_key = args.get("api_key", "")
            if not base_url:
                return {"error": "base_url is required", "exit_code": 1}
            eid = str(_uuid.uuid4())[:8]
            from datetime import datetime
            ep = ModelEndpoint(id=eid, name=name or base_url, base_url=base_url,
                               api_key=api_key, is_enabled=True,
                               created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            db.add(ep)
            db.commit()
            return {"response": f"Added endpoint '{name or base_url}' (id: {eid})", "exit_code": 0}

        elif action == "delete":
            eid = args.get("endpoint_id", "")
            ep = db.query(ModelEndpoint).filter(ModelEndpoint.id == eid).first()
            if not ep:
                return {"error": f"Endpoint {eid} not found", "exit_code": 1}
            name = ep.name
            db.delete(ep)
            db.commit()
            return {"response": f"Deleted endpoint '{name}'", "exit_code": 0}

        elif action in ("enable", "disable"):
            eid = args.get("endpoint_id", "")
            ep = db.query(ModelEndpoint).filter(ModelEndpoint.id == eid).first()
            if not ep:
                return {"error": f"Endpoint {eid} not found", "exit_code": 1}
            ep.is_enabled = (action == "enable")
            db.commit()
            return {"response": f"Endpoint '{ep.name}' {action}d", "exit_code": 0}

        else:
            return {"error": f"Unknown action: {action}", "exit_code": 1}
    except Exception as e:
        logger.error(f"manage_endpoints error: {e}")
        return {"error": str(e), "exit_code": 1}
    finally:
        db.close()


async def do_manage_endpoints(content: str, owner: Optional[str] = None) -> Dict:
    return await asyncio.to_thread(_do_manage_endpoints_sync, content, owner)


# MCP server management

async def do_manage_mcp(content: str, owner: Optional[str] = None) -> Dict:
    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = args.get("action", "list")

    if action == "list":
        mcp = get_mcp_manager()
        if not mcp:
            return {"response": "No MCP manager available", "servers": [], "exit_code": 0}
        from core.database_models import SessionLocal, McpServer
        db = SessionLocal()
        try:
            servers = db.query(McpServer).all()
            items = []
            for s in servers:
                st = mcp.get_server_status(s.id)
                status = st.get("status", "disconnected")
                tool_count = st.get("tool_count", 0)
                items.append({"id": s.id, "name": s.name, "transport": s.transport,
                              "is_enabled": s.is_enabled, "status": status,
                              "tool_count": tool_count})
            return {"response": f"{len(items)} MCP servers", "servers": items, "exit_code": 0}
        finally:
            db.close()

    elif action == "add":
        from core.database_models import SessionLocal, McpServer
        import uuid as _uuid
        from datetime import datetime
        name = args.get("name", "")
        command = args.get("command", "")
        cmd_args = args.get("args", [])
        env = args.get("env", {})
        if not name or not command:
            return {"error": "name and command are required", "exit_code": 1}
        sid = str(_uuid.uuid4())[:8]
        db = SessionLocal()
        try:
            srv = McpServer(id=sid, name=name, transport="stdio", command=command,
                            args=json.dumps(cmd_args) if isinstance(cmd_args, list) else cmd_args,
                            env=json.dumps(env) if isinstance(env, dict) else env,
                            is_enabled=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            db.add(srv)
            db.commit()
        finally:
            db.close()
        mcp = get_mcp_manager()
        tool_count = 0
        if mcp:
            try:
                await mcp.connect_server(
                    sid, name, "stdio", command=command,
                    args=cmd_args if isinstance(cmd_args, list) else json.loads(cmd_args),
                    env=env if isinstance(env, dict) else json.loads(env),
                )
                st = mcp.get_server_status(sid)
                tool_count = st.get("tool_count", 0)
            except Exception as e:
                logger.warning(f"MCP connect failed for {name}: {e}")
        return {"response": f"Added MCP server '{name}' ({tool_count} tools)", "exit_code": 0}

    elif action == "delete":
        sid = args.get("server_id", "")
        from core.database_models import SessionLocal, McpServer
        db = SessionLocal()
        try:
            srv = db.query(McpServer).filter(McpServer.id == sid).first()
            if not srv:
                return {"error": f"Server {sid} not found", "exit_code": 1}
            name = srv.name
            mcp = get_mcp_manager()
            if mcp:
                try:
                    await mcp.disconnect_server(sid)
                except Exception as _e:
                    logger.debug("MCP disconnect_server failed: %s", _e)
            db.delete(srv)
            db.commit()
            return {"response": f"Deleted MCP server '{name}'", "exit_code": 0}
        finally:
            db.close()

    elif action == "reconnect":
        sid = args.get("server_id", "")
        mcp = get_mcp_manager()
        if not mcp:
            return {"error": "MCP manager not available", "exit_code": 1}
        try:
            await mcp.disconnect_server(sid)
            from core.database_models import SessionLocal, McpServer
            db2 = SessionLocal()
            try:
                srv = db2.query(McpServer).filter(McpServer.id == sid).first()
                if srv:
                    _args = json.loads(srv.args) if srv.args else []
                    _env = json.loads(srv.env) if srv.env else {}
                    await mcp.connect_server(
                        server_id=sid,
                        name=srv.name,
                        transport=srv.transport,
                        command=srv.command,
                        args=_args,
                        env=_env,
                        url=srv.url,
                    )
                    st = mcp.get_server_status(sid)
                    return {"response": f"Reconnected '{srv.name}' ({st.get('tool_count', 0)} tools)", "exit_code": 0}
                return {"error": f"Server {sid} not found", "exit_code": 1}
            finally:
                db2.close()
        except Exception as e:
            return {"error": str(e), "exit_code": 1}

    elif action in ("enable", "disable"):
        sid = args.get("server_id", "")
        from core.database_models import SessionLocal, McpServer
        db = SessionLocal()
        try:
            srv = db.query(McpServer).filter(McpServer.id == sid).first()
            if not srv:
                return {"error": f"Server {sid} not found", "exit_code": 1}
            srv.is_enabled = (action == "enable")
            db.commit()
            return {"response": f"MCP server '{srv.name}' {action}d", "exit_code": 0}
        finally:
            db.close()

    elif action == "list_tools":
        mcp = get_mcp_manager()
        if not mcp:
            return {"response": "No MCP manager", "tools": [], "exit_code": 0}
        tools = mcp.get_all_tools()
        items = [{"name": t["name"], "server": t["server_name"],
                  "description": t.get("description", "")[:100]} for t in tools]
        return {"response": f"{len(items)} MCP tools available", "tools": items, "exit_code": 0}

    else:
        return {"error": f"Unknown action: {action}", "exit_code": 1}


# Webhook management

def _do_manage_webhooks_sync(content: str, owner: Optional[str] = None) -> Dict:
    from core.database_models import SessionLocal
    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = args.get("action", "list")
    db = SessionLocal()
    try:
        from core.database_models import Webhook
        if action == "list":
            hooks = db.query(Webhook).all()
            items = [{"id": h.id, "name": h.name, "url": h.url,
                       "events": h.events, "is_active": h.is_active} for h in hooks]
            return {"response": f"{len(items)} webhooks", "webhooks": items, "exit_code": 0}

        elif action == "add":
            import uuid as _uuid
            from datetime import datetime
            from core.webhook_manager import validate_events, validate_webhook_url
            name = args.get("name", "")
            url = args.get("url", "")
            events = args.get("events", "chat.completed")
            if not url:
                return {"error": "url is required", "exit_code": 1}
            try:
                url = validate_webhook_url(url)
                events = validate_events(events)
            except ValueError as e:
                return {"error": str(e), "exit_code": 1}
            wid = str(_uuid.uuid4())[:8]
            hook = Webhook(id=wid, name=name or url, url=url,
                           events=events, is_active=True,
                           created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            db.add(hook)
            db.commit()
            return {"response": f"Added webhook '{name or url}'", "exit_code": 0}

        elif action == "delete":
            wid = args.get("webhook_id", "")
            hook = db.query(Webhook).filter(Webhook.id == wid).first()
            if not hook:
                return {"error": f"Webhook {wid} not found", "exit_code": 1}
            name = hook.name
            db.delete(hook)
            db.commit()
            return {"response": f"Deleted webhook '{name}'", "exit_code": 0}

        elif action in ("enable", "disable"):
            wid = args.get("webhook_id", "")
            hook = db.query(Webhook).filter(Webhook.id == wid).first()
            if not hook:
                return {"error": f"Webhook {wid} not found", "exit_code": 1}
            hook.is_active = (action == "enable")
            db.commit()
            return {"response": f"Webhook '{hook.name}' {action}d", "exit_code": 0}

        else:
            return {"error": f"Unknown action: {action}", "exit_code": 1}
    except Exception as e:
        logger.error(f"manage_webhooks error: {e}")
        return {"error": str(e), "exit_code": 1}
    finally:
        db.close()


async def do_manage_webhooks(content: str, owner: Optional[str] = None) -> Dict:
    return await asyncio.to_thread(_do_manage_webhooks_sync, content, owner)


# API token management

def _do_manage_tokens_sync(content: str, owner: Optional[str] = None) -> Dict:
    from core.database_models import SessionLocal, ApiToken
    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = args.get("action", "list")
    db = SessionLocal()
    try:
        if action == "list":
            tokens = db.query(ApiToken).all()
            items = [{"id": t.id, "name": t.name, "token_prefix": t.token_prefix + "...",
                       "is_active": t.is_active} for t in tokens]
            return {"response": f"{len(items)} API tokens", "tokens": items, "exit_code": 0}

        elif action == "create":
            import uuid as _uuid, secrets, bcrypt
            from datetime import datetime
            name = args.get("name", "API Token")
            raw_token = secrets.token_urlsafe(32)
            token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
            tid = str(_uuid.uuid4())[:8]
            t = ApiToken(id=tid, name=name, token_hash=token_hash,
                         token_prefix=raw_token[:8], is_active=True,
                         created_at=datetime.utcnow(), updated_at=datetime.utcnow())
            db.add(t)
            db.commit()
            return {"response": f"Created token '{name}'", "token": raw_token, "exit_code": 0}

        elif action == "delete":
            tid = args.get("token_id", "")
            t = db.query(ApiToken).filter(ApiToken.id == tid).first()
            if not t:
                return {"error": f"Token {tid} not found", "exit_code": 1}
            name = t.name
            db.delete(t)
            db.commit()
            return {"response": f"Deleted token '{name}'", "exit_code": 0}

        else:
            return {"error": f"Unknown action: {action}", "exit_code": 1}
    except Exception as e:
        logger.error(f"manage_tokens error: {e}")
        return {"error": str(e), "exit_code": 1}
    finally:
        db.close()


async def do_manage_tokens(content: str, owner: Optional[str] = None) -> Dict:
    return await asyncio.to_thread(_do_manage_tokens_sync, content, owner)
