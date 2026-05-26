import os
import sqlite3
import base64
import io
from interpreter import interpreter
from governance.GovernanceValidator import GovernanceValidator
from jarvis_os.runtime.exceptions import GovernanceViolation
from ai_os.sandbox import SandboxedExecutor

class ComputerAgent:
    """
    Autonomous computer control using Open Interpreter.
    All execution passes through sandbox + governance.
    Vision context added before each action.
    """
    def __init__(self, db_path: str = "data/jarvis_os_world.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.governance = GovernanceValidator()
        self.sandbox = SandboxedExecutor(timeout=30)
        
        # Configure interpreter
        interpreter.auto_run = False
        interpreter.llm.model = "ollama/qwen2.5-coder:3b"
        interpreter.llm.api_base = "http://localhost:11434"
        
    async def get_screen_context(self) -> str:
        """Take screenshot, describe with gemma4 vision."""
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            from core.llm_router import router as llm_router
            r = await llm_router.acompletion(
                model="vision",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe what is on screen in 2 sentences. Focus on what app is open and what's visible."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    ]
                }],
                timeout=30,
            )
            return r.choices[0].message.content or "Screen capture processed."
        except Exception as e:
            return f"Screen capture: {e}"

    async def execute_natural_language(self, instruction: str, confirm: bool = True) -> dict:
        """
        Execute instruction after vision context + sandbox + governance check.
        """
        try:
            # 1. Governance + Sandbox validation
            self.governance.validate_execution({"task": instruction})
            sb_result = self.sandbox.execute(instruction)
            if not sb_result.get("success", False) and sb_result.get("sandbox_blocked", False):
                return {"status": "blocked", "reason": sb_result.get("error", "Sandbox rejected")}

            # 2. Vision context
            screen_state = await self.get_screen_context()
            vision_context = f"Current screen state: {screen_state}" if "failed" not in screen_state.lower() else ""

            # 3. Execute via interpreter with vision context
            print(f"[ComputerAgent] Executing: {instruction}")
            full_prompt = f"{vision_context}\n\n{instruction}" if vision_context else instruction
            result = interpreter.chat(full_prompt)

            # 4. Audit log
            self._log_action(instruction, str(result))

            return {
                "status": "success",
                "result": result,
                "instruction": instruction,
                "screen_context": screen_state,
            }
        except GovernanceViolation as e:
            return {"status": "blocked", "reason": f"Governance violation: {str(e)}"}
        except Exception as e:
            return {"status": "error", "error": str(e), "instruction": instruction}

    def _log_action(self, instruction: str, result: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pc_agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instruction TEXT,
                result TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("INSERT INTO pc_agent_logs (instruction, result) VALUES (?, ?)", (instruction, result))
        conn.commit()
        conn.close()

# Instance
computer_agent = ComputerAgent()
