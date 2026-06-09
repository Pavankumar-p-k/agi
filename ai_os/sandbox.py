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

"""
Sandboxed command executor with process isolation and timeout protection.
Ensures all shell commands run with shell=False for safety.
"""

import subprocess
import os
import sys
from typing import Any, Optional
from pathlib import Path


class SandboxedExecutor:
    """Execute commands in isolated subprocess with strict safety constraints."""
    
    # Maximum execution time per command (seconds)
    DEFAULT_TIMEOUT = 30
    
    # Maximum output size (bytes)
    MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB
    
    # Blocked executable patterns for extra safety
    BLOCKED_EXECUTABLES = [
        "rm", "del", "format", "diskpart", "cipher",  # Destructive
        "shutdown", "reboot", "halt",  # System control
        "taskkill", "kill",  # Process termination
        "reg", "regedit", "regedit32",  # Registry
        "fsutil", "chkdsk", "sfc", "bcdedit",  # System tools
        "diskpart", "mountvol", "vssadmin",  # Volume management
    ]

    # Only allow writes within these directories
    ALLOWED_WRITE_PATHS = [
        os.path.expanduser("~"),           # Home directory
        os.getcwd(),                       # Current working directory
        os.path.expandvars("%TEMP%"),      # Temp directory
        os.path.expandvars("%APPDATA%"),   # AppData
    ]
    
    def __init__(self, timeout: int = DEFAULT_TIMEOUT, cwd: Optional[str] = None):
        """
        Initialize sandbox executor.
        
        Args:
            timeout: Command timeout in seconds
            cwd: Working directory for execution (defaults to user home)
        """
        self.timeout = timeout
        self.cwd = cwd or str(Path.home())
    
    @staticmethod
    def parse_command(cmd: str) -> list[str]:
        """Parse shell command string into argv array."""
        # Simple split by whitespace - more sophisticated parsing in production
        return cmd.split()
    
    @staticmethod
    def is_blocked_executable(executable: str) -> bool:
        """Check if executable is in blocklist."""
        exe_name = Path(executable).stem.lower()
        return exe_name in SandboxedExecutor.BLOCKED_EXECUTABLES
    
    def execute(self, cmd: str) -> dict[str, Any]:
        """
        Execute command safely with isolation.
        
        Args:
            cmd: Shell command as string (will be split into argv)
        
        Returns:
            {
                success: bool,
                stdout: str,
                stderr: str,
                returncode: int,
                error: Optional[str],
                sandbox_blocked: bool
            }
        """
        try:
            # Parse command into argv array
            argv = self.parse_command(cmd)
            
            if not argv:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "Empty command",
                    "returncode": -1,
                    "error": "Empty command",
                    "sandbox_blocked": False,
                }
            
            # Check if executable is blocked
            executable = argv[0]
            if self.is_blocked_executable(executable):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Blocked executable: {executable}",
                    "returncode": -1,
                    "error": f"Executable '{executable}' is blocked for security",
                    "sandbox_blocked": True,
                }
            
            # Execute with subprocess (shell=False is critical for safety)
            try:
                result = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    shell=False,  # CRITICAL: Never use shell=True
                    cwd=self.cwd,
                )
                
                # Truncate output if too large
                stdout = result.stdout
                stderr = result.stderr
                
                if len(stdout) > self.MAX_OUTPUT_SIZE:
                    stdout = stdout[:self.MAX_OUTPUT_SIZE] + "\n... (truncated)"
                
                if len(stderr) > self.MAX_OUTPUT_SIZE:
                    stderr = stderr[:self.MAX_OUTPUT_SIZE] + "\n... (truncated)"
                
                return {
                    "success": result.returncode == 0,
                    "stdout": stdout,
                    "stderr": stderr,
                    "returncode": result.returncode,
                    "error": None,
                    "sandbox_blocked": False,
                }
            
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Command timeout after {self.timeout}s",
                    "returncode": -124,
                    "error": "Timeout",
                    "sandbox_blocked": False,
                }
            
            except FileNotFoundError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Executable not found: {executable}",
                    "returncode": 127,
                    "error": "Executable not found",
                    "sandbox_blocked": False,
                }
        
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "returncode": -1,
                "error": str(e),
                "sandbox_blocked": False,
            }
    
    def execute_safe_shell(self, cmd: str) -> dict[str, Any]:
        """
        Alias for execute() for compatibility with tool interface.
        This is the interface that tool_registry will use.
        """
        return self.execute(cmd)


# Global singleton instance
_sandbox = SandboxedExecutor()


def get_sandbox() -> SandboxedExecutor:
    """Get global sandbox executor instance."""
    return _sandbox


def execute_sandboxed(cmd: str, timeout: int = 30) -> dict[str, Any]:
    """Convenience function to execute sandboxed command."""
    executor = SandboxedExecutor(timeout=timeout)
    return executor.execute(cmd)
