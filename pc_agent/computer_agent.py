import os
import sqlite3
from interpreter import interpreter
from governance.GovernanceValidator import GovernanceValidator
from jarvis_os.runtime.exceptions import GovernanceViolation

class ComputerAgent:
    """
    Autonomous computer control using Open Interpreter.
    """
    def __init__(self, db_path: str = "data/jarvis_os_world.db"):
        self.db_path = db_path
        self.governance = GovernanceValidator()
        
        # Configure interpreter
        interpreter.auto_run = True
        interpreter.llm.model = "ollama/qwen2.5-coder:3b"
        interpreter.llm.api_base = "http://localhost:11434"
        
    def execute_natural_language(self, instruction: str, confirm: bool = True) -> dict:
        """
        Execute instruction after governance check.
        """
        # 1. Governance check
        try:
            # We wrap the instruction in a dict that GovernanceValidator understands
            self.governance.validate_execution({"task": instruction})
        except GovernanceViolation as e:
            return {"status": "blocked", "reason": f"Governance violation: {str(e)}"}
        except Exception as e:
            return {"status": "error", "error": f"Governance check failed: {str(e)}"}
            
        # 2. Execute via interpreter
        print(f"[ComputerAgent] Executing: {instruction}")
        try:
            # Capture output
            result = interpreter.chat(instruction)
            
            # 3. Audit log
            self._log_action(instruction, str(result))
            
            return {
                "status": "success",
                "result": result,
                "instruction": instruction
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "instruction": instruction
            }

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
