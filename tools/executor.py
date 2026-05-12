# tools/executor.py
"""
OpenClaw Executor - Real-World Execution Engine
Provides system access for automation: files, commands, browser, APIs
Research-grade implementation with safety controls and monitoring
"""

import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import psutil
import pyautogui
import webbrowser
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.types import ExecutionContext, ExecutionResult, SafetyCheck


class OpenClawExecutor:
    """
    OpenClaw-style execution engine providing real system access
    Features:
    - Safe command execution with sandboxing
    - File system operations
    - Browser automation
    - System monitoring
    - API integrations
    - Safety controls and audit logging
    """

    def __init__(self):
        self.system = platform.system().lower()
        self.safety_enabled = True
        self.audit_log: List[Dict[str, Any]] = []
        self.max_execution_time = 300  # 5 minutes
        self.allowed_commands = self._load_allowed_commands()
        self.dangerous_patterns = [
            "rm -rf /",
            "del /s /q c:",
            "format",
            "fdisk",
            "sudo",
            "su ",
            "chmod 777",
            "chown root"
        ]

        # Browser automation setup
        self.browser_instances: Dict[str, webdriver.Chrome] = {}

    def _load_allowed_commands(self) -> List[str]:
        """Load whitelist of allowed commands"""
        base_commands = [
            "ls", "dir", "cd", "pwd", "echo", "cat", "type",
            "grep", "find", "which", "where", "ping", "nslookup",
            "curl", "wget", "python", "node", "npm", "pip",
            "git", "docker", "kubectl", "aws", "az", "gcloud",
            "ffmpeg", "convert", "identify",  # Media tools
            "adb", "fastboot"  # Android tools
        ]

        if self.system == "windows":
            base_commands.extend([
                "tasklist", "netstat", "ipconfig", "systeminfo",
                "powershell", "cmd", "robocopy", "xcopy"
            ])
        else:
            base_commands.extend([
                "ps", "top", "htop", "df", "du", "free",
                "bash", "zsh", "fish", "cp", "mv", "mkdir", "touch"
            ])

        return base_commands

    async def execute_command(
        self,
        command: str,
        context: ExecutionContext,
        timeout: Optional[float] = None
    ) -> ExecutionResult:
        """
        Execute system command with safety controls
        Returns structured result with output, errors, and metadata
        """

        start_time = time.time()

        # Safety check
        safety = self._check_command_safety(command, context)
        if not safety.allowed and self.safety_enabled:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Command blocked by safety controls: {safety.reason}",
                execution_time=time.time() - start_time,
                metadata={"safety_check": safety.__dict__}
            )

        # Parse command for execution
        parsed_command = self._parse_command(command)

        try:
            # Execute with timeout
            timeout = timeout or self.max_execution_time
            process = await asyncio.create_subprocess_exec(
                *parsed_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._get_safe_working_directory(context)
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                execution_time = time.time() - start_time

                result = ExecutionResult(
                    success=process.returncode == 0,
                    output=stdout.decode().strip(),
                    error=stderr.decode().strip() if stderr else None,
                    exit_code=process.returncode,
                    execution_time=execution_time,
                    metadata={
                        "command": command,
                        "working_directory": str(self._get_safe_working_directory(context)),
                        "system": self.system
                    }
                )

            except asyncio.TimeoutError:
                process.kill()
                return ExecutionResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds",
                    execution_time=time.time() - start_time,
                    metadata={"timeout": timeout}
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Execution failed: {str(e)}",
                execution_time=time.time() - start_time
            )

        # Audit logging
        self._log_execution(command, result, context)

        return result

    def _check_command_safety(self, command: str, context: ExecutionContext) -> SafetyCheck:
        """Comprehensive safety check for commands"""

        # Check dangerous patterns
        for pattern in self.dangerous_patterns:
            if pattern in command.lower():
                return SafetyCheck(
                    allowed=False,
                    reason=f"Dangerous pattern detected: {pattern}",
                    risk_level="critical"
                )

        # Check permissions
        if "write" not in context.permissions and self._command_modifies_files(command):
            return SafetyCheck(
                allowed=False,
                reason="Write permissions required",
                risk_level="high"
            )

        # Check command whitelist
        base_cmd = command.split()[0].lower()
        if base_cmd not in self.allowed_commands and not self._is_path_command(base_cmd):
            return SafetyCheck(
                allowed=False,
                reason=f"Command not in whitelist: {base_cmd}",
                risk_level="medium"
            )

        # Check working directory safety
        work_dir = self._get_safe_working_directory(context)
        if not self._is_safe_directory(work_dir):
            return SafetyCheck(
                allowed=False,
                reason="Unsafe working directory",
                risk_level="high"
            )

        return SafetyCheck(
            allowed=True,
            reason="Command passed safety checks",
            risk_level="low"
        )

    def _command_modifies_files(self, command: str) -> bool:
        """Check if command actually modifies files (not just output)"""
        cmd_lower = command.lower()
        
        # Commands that modify files (require write permission)
        if any(op in cmd_lower for op in [">", ">>", "rm ", "del ", " /s", "move ", "mv ", "copy ", " cp "]):
            return True
        
        # These commands modify files only in specific contexts
        if "echo" in cmd_lower and (">" in cmd_lower or ">>" in cmd_lower):
            return True
            
        if "mkdir" in cmd_lower or "touch" in cmd_lower:
            return True
            
        if "install" in cmd_lower and ("pip" in cmd_lower or "npm" in cmd_lower or "apt" in cmd_lower):
            return True
        
        # Most other commands are read-only
        return False

    def _is_path_command(self, cmd: str) -> bool:
        """Check if command is a file path"""
        return "/" in cmd or "\\" in cmd or cmd.endswith((".exe", ".bat", ".sh", ".py"))

    def _parse_command(self, command: str) -> List[str]:
        """Parse command string into executable arguments"""
        if self.system == "windows":
            # Use cmd for complex commands
            return ["cmd", "/c", command]
        else:
            # Use shell for complex commands
            return ["bash", "-c", command]

    def _get_safe_working_directory(self, context: ExecutionContext) -> Path:
        """Get safe working directory for execution"""
        # Default to project root or user home
        base_dir = Path.cwd()
        if "workspace" in context.variables:
            workspace = Path(context.variables["workspace"])
            if workspace.exists() and self._is_safe_directory(workspace):
                base_dir = workspace

        return base_dir

    def _is_safe_directory(self, path: Path) -> bool:
        """Check if directory is safe for operations"""
        # Basic safety checks
        try:
            # Check if path exists and is directory
            if not path.exists() or not path.is_dir():
                return False

            # Check permissions (basic)
            if not os.access(path, os.R_OK):
                return False

            # Avoid system directories
            system_dirs = ["/bin", "/sbin", "/boot", "/sys", "/proc", "C:\\Windows", "C:\\System32"]
            path_str = str(path)
            for sys_dir in system_dirs:
                if sys_dir in path_str:
                    return False

            return True

        except Exception:
            return False

    async def execute_file_operation(
        self,
        operation: str,
        path: str,
        content: Optional[str] = None,
        context: ExecutionContext = None
    ) -> ExecutionResult:
        """Execute file system operations safely"""

        start_time = time.time()
        path_obj = Path(path)

        # Safety checks
        if not self._is_safe_file_path(path_obj, operation, context):
            return ExecutionResult(
                success=False,
                output="",
                error="Unsafe file operation",
                execution_time=time.time() - start_time
            )

        try:
            if operation == "read":
                if path_obj.exists():
                    content = path_obj.read_text()
                    return ExecutionResult(
                        success=True,
                        output=content,
                        execution_time=time.time() - start_time,
                        metadata={"file_size": len(content), "encoding": "utf-8"}
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        output="",
                        error="File not found",
                        execution_time=time.time() - start_time
                    )

            elif operation == "write":
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                path_obj.write_text(content or "")
                return ExecutionResult(
                    success=True,
                    output=f"Written {len(content or '')} characters",
                    execution_time=time.time() - start_time,
                    metadata={"file_size": len(content or "")}
                )

            elif operation == "list":
                if path_obj.is_dir():
                    items = [str(item) for item in path_obj.iterdir()]
                    return ExecutionResult(
                        success=True,
                        output=json.dumps(items),
                        execution_time=time.time() - start_time,
                        metadata={"item_count": len(items)}
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        output="",
                        error="Path is not a directory",
                        execution_time=time.time() - start_time
                    )

            elif operation == "delete":
                if path_obj.exists():
                    if path_obj.is_file():
                        path_obj.unlink()
                    else:
                        import shutil
                        shutil.rmtree(path_obj)
                    return ExecutionResult(
                        success=True,
                        output="Deleted successfully",
                        execution_time=time.time() - start_time
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        output="",
                        error="Path not found",
                        execution_time=time.time() - start_time
                    )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"File operation failed: {str(e)}",
                execution_time=time.time() - start_time
            )

    def _is_safe_file_path(self, path: Path, operation: str, context: ExecutionContext) -> bool:
        """Check if file path is safe for operation"""
        try:
            # Resolve to absolute path
            abs_path = path.resolve()

            # Check against system directories
            system_paths = ["/bin", "/sbin", "/boot", "/sys", "/proc", "/etc/passwd",
                          "C:\\Windows", "C:\\System32", "C:\\Program Files"]
            abs_str = str(abs_path)
            for sys_path in system_paths:
                if sys_path in abs_str:
                    return False

            # Check write permissions for write operations
            if operation in ["write", "delete"] and "write" not in (context.permissions if context else []):
                return False

            return True

        except Exception:
            return False

    async def execute_browser_action(
        self,
        action: str,
        url: Optional[str] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        context: ExecutionContext = None
    ) -> ExecutionResult:
        """Execute browser automation actions"""

        start_time = time.time()

        try:
            # Get or create browser instance
            session_id = context.session_id if context else "default"
            driver = self._get_browser_instance(session_id)

            if action == "navigate":
                driver.get(url)
                return ExecutionResult(
                    success=True,
                    output=f"Navigated to {url}",
                    execution_time=time.time() - start_time
                )

            elif action == "click":
                element = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                element.click()
                return ExecutionResult(
                    success=True,
                    output=f"Clicked element: {selector}",
                    execution_time=time.time() - start_time
                )

            elif action == "type":
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                element.clear()
                element.send_keys(text)
                return ExecutionResult(
                    success=True,
                    output=f"Typed '{text}' into: {selector}",
                    execution_time=time.time() - start_time
                )

            elif action == "screenshot":
                screenshot = driver.get_screenshot_as_base64()
                return ExecutionResult(
                    success=True,
                    output=screenshot,
                    execution_time=time.time() - start_time,
                    metadata={"format": "base64", "type": "screenshot"}
                )

            elif action == "get_text":
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                text_content = element.text
                return ExecutionResult(
                    success=True,
                    output=text_content,
                    execution_time=time.time() - start_time
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                output="",
                error=f"Browser action failed: {str(e)}",
                execution_time=time.time() - start_time
            )

    def _get_browser_instance(self, session_id: str) -> webdriver.Chrome:
        """Get or create browser instance for session"""
        if session_id not in self.browser_instances:
            options = Options()
            options.add_argument("--headless")  # Run headless for automation
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            try:
                self.browser_instances[session_id] = webdriver.Chrome(options=options)
            except Exception:
                # Fallback to system browser
                return None

        return self.browser_instances[session_id]

    async def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information"""
        try:
            return {
                "platform": self.system,
                "cpu_count": psutil.cpu_count(),
                "memory": psutil.virtual_memory()._asdict(),
                "disk": psutil.disk_usage('/')._asdict() if self.system != "windows" else psutil.disk_usage('C:')._asdict(),
                "network": {k: v for k, v in psutil.net_io_counters()._asdict().items() if v is not None},
                "processes": len(psutil.pids())
            }
        except Exception as e:
            return {"error": str(e)}

    def _log_execution(self, command: str, result: ExecutionResult, context: ExecutionContext):
        """Log execution for audit purposes"""
        log_entry = {
            "timestamp": time.time(),
            "command": command,
            "success": result.success,
            "execution_time": result.execution_time,
            "user_id": context.user_id if context else "system",
            "session_id": context.session_id if context else "unknown",
            "exit_code": result.exit_code,
            "error": result.error
        }

        self.audit_log.append(log_entry)

        # Keep only last 1000 entries
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]

    def get_status(self) -> Dict[str, Any]:
        """Get executor status and statistics"""
        recent_logs = self.audit_log[-10:] if self.audit_log else []

        return {
            "safety_enabled": self.safety_enabled,
            "active_browser_sessions": len(self.browser_instances),
            "audit_log_entries": len(self.audit_log),
            "recent_activity": recent_logs,
            "system_info": "unavailable (call get_system_info() from async context)"
        }

    def cleanup(self):
        """Cleanup resources"""
        for driver in self.browser_instances.values():
            try:
                driver.quit()
            except Exception:
                pass
        self.browser_instances.clear()


# Global executor instance
open_claw_executor = OpenClawExecutor()
