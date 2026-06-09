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

"""Integration tests for JARVIS Subagent Spawning subsystem."""
import pytest
import asyncio
from unittest.mock import patch
from core.spawning import subagent_manager, SubagentStore, SpawnResult
from core.session import session_manager
from core.result import Ok

@pytest.fixture
def clean_store():
    """Ensure a clean state for spawning store."""
    # In a real integration test, we might use a test DB.
    # For now, we'll assume the manager's store is available.
    yield subagent_manager.store

@pytest.mark.asyncio
async def test_spawn_lifecycle(clean_store):
    """Test spawning an agent and its lifecycle transitions."""
    task = "Find the meaning of life"
    agent_id = "MAESTRO"
    
    with patch("core.sub_agents.base_agent.complete") as mock_complete:
        mock_complete.return_value = Ok("The answer is 42.")
        
        # 1. Spawn
        result = await subagent_manager.spawn(agent_id, task)
        assert result.accepted
        run_id = result.run_id
        
        # 2. Check store - should be 'running' or 'completed' quickly
        # Since it's an async task, we might need to wait a bit
        for _ in range(10):
            run = await clean_store.get_run(run_id)
            if run["status"] == "completed":
                break
            await asyncio.sleep(0.1)
            
        assert run["status"] == "completed"
        assert "42" in run["result_text"]
        assert run["outcome"] == "ok"

@pytest.mark.asyncio
async def test_spawn_depth_limit():
    """Test that spawning depth is enforced."""
    # Create a session with max depth
    deep_key = "agent:test:spawn:deep"
    session = session_manager.create_session(deep_key)
    session.data["spawn_depth"] = subagent_manager.max_depth
    
    result = await subagent_manager.spawn("MAESTRO", "Too deep", parent_session_key=deep_key)
    assert not result.accepted
    assert "depth" in result.error.lower()

@pytest.mark.asyncio
async def test_steer_injection():
    """Test steering an agent by injecting guidance."""
    # 1. Start a slow/dummy agent (mocked)
    with patch("core.sub_agents.base_agent.complete") as mock_complete:
        # Create a future that we can resolve later to simulate a long run
        fut = asyncio.Future()
        mock_complete.return_value = fut
        
        result = await subagent_manager.spawn("MAESTRO", "Wait for guidance")
        run_id = result.run_id
        child_key = result.child_session_key
        
        # 2. Steer
        steer_msg = "Focus on the science part"
        ok = await subagent_manager.steer(run_id, steer_msg)
        assert ok
        
        # 3. Verify conversation file
        from core.session import ConversationManager
        conv = ConversationManager(session_id=child_key.replace(':', '_'))
        conv.load()
        assert any(steer_msg in m["content"] for m in conv.messages)
        
        # Cleanup
        fut.set_result(Ok("Done"))
        await asyncio.sleep(0.1)

@pytest.mark.asyncio
async def test_orphan_recovery_simulated():
    """Simulate orphan recovery from persisted session files."""
    import uuid
    u_id = uuid.uuid4().hex[:8]
    run_id = f"run_orphan_{u_id}"
    child_key = f"agent:maestro:spawn:orphan_{u_id}"
    task = "Recover me"
    
    # 1. Create a fake run in 'running' state
    await subagent_manager.store.create_run(
        run_id, "MAESTRO", "root:default", child_key, task, depth=1
    )
    await subagent_manager.store.update_status(run_id, "running")
    
    # 2. Create a fake session file
    from core.session import SESSION_DIR
    import json
    safe_key = child_key.replace(':', '_')
    session_file = SESSION_DIR / f"hier_{safe_key}.json"
    session_file.write_text(json.dumps({
        "key": child_key,
        "data": {},
        "created_at": "...",
        "updated_at": "..."
    }))
    
    # 3. Run recovery
    from core.spawning.orphan import orphan_recovery
    
    with patch("core.sub_agents.base_agent.complete") as mock_complete:
        mock_complete.return_value = Ok("Recovered!")
        
        # We need to bypass the grace period or set it to 0
        with patch.object(subagent_manager.store, "list_orphans", wraps=subagent_manager.store.list_orphans) as mock_list:
            # Force list_orphans to return our fake run
            run_data = await subagent_manager.store.get_run(run_id)
            mock_list.return_value = [run_data]
            
            await orphan_recovery.recover()
            
        # 4. Verify run was resumed and completed
        for _ in range(10):
            run = await subagent_manager.store.get_run(run_id)
            if run["status"] == "completed":
                break
            await asyncio.sleep(0.1)
            
        assert run["status"] == "completed"
        assert "Recovered" in run["result_text"]
        
    # Cleanup
    if session_file.exists(): session_file.unlink()
    await subagent_manager.store.delete_run(run_id)
