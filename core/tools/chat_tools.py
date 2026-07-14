import logging
import uuid
import time

logger = logging.getLogger(__name__)

MEMORY_STORE = None


def _ensure_memory():
    global MEMORY_STORE
    if MEMORY_STORE is not None:
        return
    try:
        from core.constants import DATA_DIR as _data_dir
        from memory.crud_store import CrudStore
        MEMORY_STORE = CrudStore(_data_dir)
    except Exception as e:
        logger.warning("Memory init failed: %s", e)


async def do_manage_memory(content: str, **kwargs) -> dict:
    _ensure_memory()
    if not MEMORY_STORE:
        return {"error": "Memory store not available", "exit_code": 1}

    import json
    try:
        args = json.loads(content) if content.strip() else {}
    except json.JSONDecodeError:
        lines = content.strip().split("\n", 2)
        action = lines[0].strip().lower() if lines else ""
        args = {"action": action}
        if action == "add":
            args["text"] = lines[1].strip() if len(lines) > 1 else ""
            args["category"] = lines[2].strip().lower() if len(lines) > 2 else "fact"
        elif action == "edit":
            args["memory_id"] = lines[1].strip() if len(lines) > 1 else ""
            args["text"] = lines[2].strip() if len(lines) > 2 else ""
        elif action == "delete":
            args["memory_id"] = lines[1].strip() if len(lines) > 1 else ""
        elif action == "search":
            args["text"] = lines[1].strip() if len(lines) > 1 else ""
        elif action == "list":
            args["category"] = lines[1].strip().lower() if len(lines) > 1 and lines[1].strip() else ""
        else:
            return {"error": f"Unknown action '{action}'. Use: list, add, edit, delete, search", "exit_code": 1}

    action = args.get("action", "")

    if action == "list":
        category = args.get("category", "")
        memories = MEMORY_STORE.list_all(category=category) if category else MEMORY_STORE.list_all()
        if not memories:
            msg = "No memories found"
            if category:
                msg += f" in category '{category}'"
            return {"output": msg + ".", "memories": []}
        lines = [f"Found {len(memories)} memory entries:"]
        for m in memories[:100]:
            cat = m.get("category", "fact")
            mid = m.get("id", "?")[:8]
            text = m.get("text", "")
            lines.append(f"  [{cat}] `{mid}` — {text[:200]}")
        if len(memories) > 100:
            lines.append(f"  ... and {len(memories) - 100} more")
        return {"output": "\n".join(lines), "count": len(memories)}

    elif action == "add":
        text = args.get("text", "")
        category = args.get("category", "fact")
        if not text:
            return {"error": "Memory text cannot be empty", "exit_code": 1}
        entry = MEMORY_STORE.add(text, source="ai_agent", category=category)
        all_m = MEMORY_STORE.load_all()
        all_m.append(entry)
        MEMORY_STORE.save(all_m)
        if MEMORY_STORE.vector_healthy:
            MEMORY_STORE.vector_add(entry["id"], text)
        return {"output": f"Memory added: [{category}] {text}", "id": entry["id"][:8]}

    elif action == "edit":
        memory_id = args.get("memory_id", "")
        new_text = args.get("text", "")
        if not memory_id or not new_text:
            return {"error": "edit needs memory_id and text", "exit_code": 1}
        old = MEMORY_STORE.update(memory_id, text=new_text)
        if old is None:
            return {"error": f"Memory '{memory_id}' not found", "exit_code": 1}
        full_id = old["id"]
        if MEMORY_STORE.vector_healthy:
            MEMORY_STORE.vector_remove(full_id)
            MEMORY_STORE.vector_add(full_id, new_text)
        return {"output": f"Memory updated: {new_text}"}

    elif action == "delete":
        memory_id = args.get("memory_id", "")
        if not memory_id:
            return {"error": "delete needs memory_id", "exit_code": 1}
        all_m = MEMORY_STORE.load_all()
        full_id = None
        for m in all_m:
            if m.get("id", "").startswith(memory_id):
                full_id = m["id"]
                break
        if not full_id:
            return {"error": f"Memory '{memory_id}' not found", "exit_code": 1}
        MEMORY_STORE.delete(memory_id)
        if MEMORY_STORE.vector_healthy and full_id:
            MEMORY_STORE.vector_remove(full_id)
        return {"output": f"Memory deleted (id: {memory_id})"}

    elif action == "search":
        query = args.get("text", "")
        if not query:
            return {"error": "search needs text (query)", "exit_code": 1}
        results = MEMORY_STORE.get_relevant_memories(query, threshold=0.05, max_items=20)
        if not results:
            return {"output": f"No memories found matching '{query}'.", "memories": []}
        lines = [f"Found {len(results)} matching memories:"]
        for m in results:
            cat = m.get("category", "fact")
            mid = m.get("id", "?")[:8]
            text = m.get("text", "")
            lines.append(f"  [{cat}] `{mid}` — {text}")
        return {"output": "\n".join(lines), "count": len(results)}

    return {"error": f"Unknown action '{action}'", "exit_code": 1}


async def do_create_session(content: str, **kwargs) -> dict:
    import json
    try:
        args = json.loads(content) if content.strip() else {}
    except json.JSONDecodeError:
        lines = content.strip().split("\n", 1)
        name = lines[0].strip() if lines else "New Chat"
        model = lines[1].strip() if len(lines) > 1 else ""
        args = {"name": name, "model": model}

    name = args.get("name", "New Chat") or "New Chat"
    model = args.get("model", "")
    session_key = f"chat:{uuid.uuid4().hex[:12]}"

    try:
        from core.session import session_manager
        session = session_manager.create_session(session_key)
        session.set("name", name)
        if model:
            session.set("model", model)
        return {
            "output": f"Session created: {name} (key: {session_key})",
            "session_key": session_key,
            "name": name,
            "model": model,
        }
    except Exception as e:
        logger.warning("Session creation failed: %s", e)
        return {"error": f"Failed to create session: {e}", "exit_code": 1}


async def do_chat_with_model(content: str, **kwargs) -> dict:
    import json
    try:
        args = json.loads(content) if content.strip() else {}
    except json.JSONDecodeError:
        lines = content.strip().split("\n", 1)
        model = lines[0].strip() if lines else ""
        message = lines[1].strip() if len(lines) > 1 else content
        args = {"model": model, "message": message}

    model = args.get("model", "")
    message = args.get("message", "")
    if not message:
        return {"error": "No message provided", "exit_code": 1}

    try:
        from core.pipeline.internal_client import prompt as llm_prompt
        system = "You are a helpful assistant. Answer the user's question concisely."
        text = await llm_prompt(message, system=system, metadata={"model": model or "chat"})
        return {"output": text, "model": model or "default"}
    except Exception as e:
        logger.warning("chat_with_model failed: %s", e)
        return {"error": f"Chat failed: {e}", "exit_code": 1}
