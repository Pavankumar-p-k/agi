from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config_schema import jarvis_config, SandboxPolicy

logger = logging.getLogger("jarvis.ai_os.sandbox_manager")

@dataclass
class SandboxInstance:
    id: str
    container_id: str
    workspace_path: str
    policy: SandboxPolicy
    type: str = "default"  # "default" or "browser"
    last_used: float = field(default_factory=time.time)

class SandboxManager:
    """Manages Docker sandbox instances with policy enforcement and lifecycle control."""

    def __init__(self):
        self.config = jarvis_config.sandbox
        self._instances: Dict[str, SandboxInstance] = {}
        self._client = None
        self._available = False
        self._lock = asyncio.Lock()
        
        # Ensure workspace root exists
        os.makedirs(self.config.workspace_root, exist_ok=True)

    async def _get_client(self):
        if self._client:
            return self._client
        try:
            import docker
            self._client = await asyncio.to_thread(docker.from_env)
            await asyncio.to_thread(self._client.ping)
            self._available = True
            return self._client
        except Exception as e:
            self._available = False
            logger.warning("[SandboxManager] Docker not available: %s", e)
            return None

    def _match_policy(self, tool_name: str, policy: SandboxPolicy) -> bool:
        """Check if a tool is allowed by the policy using glob matching."""
        # Deny list takes precedence
        for pattern in policy.deny_tools:
            if fnmatch.fnmatch(tool_name, pattern):
                return False
        
        # Check allow list
        for pattern in policy.allow_tools:
            if fnmatch.fnmatch(tool_name, pattern):
                return True
        
        return False

    async def get_instance(self, session_id: str, sandbox_type: str = "default", policy: Optional[SandboxPolicy] = None) -> Optional[SandboxInstance]:
        """Get or create a sandbox instance for a session."""
        key = f"{session_id}:{sandbox_type}"
        async with self._lock:
            if key in self._instances:
                instance = self._instances[key]
                instance.last_used = time.time()
                return instance

            client = await self._get_client()
            if not client:
                return None

            instance_id = f"jarvis-sandbox-{session_id}-{sandbox_type}"
            workspace = os.path.join(self.config.workspace_root, session_id)
            os.makedirs(workspace, exist_ok=True)

            eff_policy = policy or self.config.default_policy
            image = self.config.browser_image if sandbox_type == "browser" else self.config.image

            try:
                # Cleanup existing container with same name if any
                try:
                    old = await asyncio.to_thread(client.containers.get, instance_id)
                    await asyncio.to_thread(old.remove, force=True)
                except Exception as e:
                    logger.warning("[ai_os.sandbox_manager] sandbox_execute failed: %s", e)

                # Create container
                binds = {
                    os.path.abspath(workspace): {'bind': '/workspace', 'mode': 'rw'}
                }
                
                # For browser, we might need more capabilities or shared memory
                extra_params = {}
                if sandbox_type == "browser":
                    extra_params["shm_size"] = "2g"
                
                container = await asyncio.to_thread(
                    client.containers.run,
                    image=image,
                    name=instance_id,
                    command="tail -f /dev/null", # Keep alive
                    detach=True,
                    mem_limit=eff_policy.max_memory,
                    nano_cpus=int(eff_policy.max_cpu * 1e9),
                    network_disabled=not eff_policy.allow_network,
                    volumes=binds if eff_policy.allow_bind_mounts else None,
                    working_dir="/workspace",
                    restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
                    **extra_params
                )

                instance = SandboxInstance(
                    id=session_id,
                    container_id=container.id,
                    workspace_path=workspace,
                    policy=eff_policy,
                    type=sandbox_type
                )
                self._instances[key] = instance
                return instance
            except Exception as e:
                logger.error("[SandboxManager] Failed to create %s sandbox for %s: %s", sandbox_type, session_id, e)
                return None

    async def exec(self, session_id: str, tool_name: str, cmd: List[str], env: Optional[Dict] = None, sandbox_type: str = "default") -> Dict[str, Any]:
        """Execute a command in the session's sandbox."""
        instance = await self.get_instance(session_id, sandbox_type=sandbox_type)
        if not instance:
            return {"success": False, "error": f"{sandbox_type} Sandbox not available"}

        if not self._match_policy(tool_name, instance.policy):
            return {"success": False, "error": f"Tool '{tool_name}' blocked by sandbox policy"}

        client = await self._get_client()
        try:
            container = await asyncio.to_thread(client.containers.get, instance.container_id)
            
            # Use asyncio.wait_for for timeout
            exec_res = await asyncio.to_thread(
                container.exec_run,
                cmd=cmd,
                environment=env,
                workdir="/workspace"
            )
            
            return {
                "success": exec_res.exit_code == 0,
                "exit_code": exec_res.exit_code,
                "stdout": exec_res.output.decode('utf-8', errors='replace'),
                "stderr": "" # Docker exec_run combines stdout/stderr in output unless specified
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def stop_instance(self, session_id: str):
        """Stop and remove a sandbox instance."""
        async with self._lock:
            instance = self._instances.pop(session_id, None)
            if not instance:
                return
            
            client = await self._get_client()
            try:
                container = await asyncio.to_thread(client.containers.get, instance.container_id)
                await asyncio.to_thread(container.remove, force=True)
                # Optionally cleanup workspace
                # shutil.rmtree(instance.workspace_path, ignore_errors=True)
            except Exception as e:
                logger.warning("[SandboxManager] Failed to stop sandbox %s: %s", session_id, e)

    async def run_gc(self):
        """Cleanup idle containers."""
        now = time.time()
        to_stop = []
        async with self._lock:
            for sid, inst in self._instances.items():
                if now - inst.last_used > self.config.gc_interval_seconds:
                    to_stop.append(sid)
        
        for sid in to_stop:
            logger.info("[SandboxManager] GC: Stopping idle sandbox %s", sid)
            await self.stop_instance(sid)

# Global singleton
sandbox_manager = SandboxManager()
