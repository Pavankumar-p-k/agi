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
from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.sub_agents.tool")

async def do_sessions_spawn(content: str, **kwargs) -> dict:
    """
    Spawn a sub-agent to complete a task in the background.
    Expects JSON content with: task, agent_id (opt), mode (opt), cleanup (opt), task_name (opt)
    """
    from core.spawning.manager import subagent_manager
    from core.tools.implementations import _parse_tool_args

    try:
        args = _parse_tool_args(content)
    except Exception as _e:
        logger.debug("sub_agents tool parse args failed: %s", _e)
        # Fallback for plain text task
        args = {"task": content.strip()}

    task = args.get("task", "")
    if not task:
        return {"error": "Missing 'task' parameter", "exit_code": 1}

    agent_id = args.get("agent_id", "MAESTRO")
    mode = args.get("mode", "isolated")
    cleanup = args.get("cleanup", "delete")

    parent_key = kwargs.get("_session_key") or "root:default"

    result = await subagent_manager.spawn(
        agent_id=agent_id,
        task=task,
        parent_session_key=parent_key,
        context_mode=mode, # type: ignore
        cleanup=cleanup, # type: ignore
    )

    res_dict = result.to_dict()
    if result.accepted:
        res_dict["response"] = f"Successfully spawned {agent_id} subagent (run_id: {result.run_id})"
        res_dict["exit_code"] = 0
    else:
        res_dict["exit_code"] = 1

    return res_dict
