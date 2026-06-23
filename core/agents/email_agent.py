"""EmailAgent — send, read, and manage emails."""

from __future__ import annotations

import json

from core.agents.base import BaseAgent
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block


class EmailAgent(BaseAgent):
    agent_id = "email"
    capabilities = ["email", "mail", "send", "deliver", "notify"]

    async def execute(self, context=None) -> dict:
        to = context.variables.get("to", "") if context else ""
        subject = context.variables.get("subject", "Build results") if context else "Build results"
        body = context.variables.get("body", "Task completed.") if context else "Task completed."
        attachments = context.variables.get("attachments", []) if context else []

        args = {"to": to, "subject": subject, "body": body}
        if attachments:
            args["attachments"] = attachments

        send_block = ToolBlock(tool_type="send_email",
                               content=json.dumps(args))
        _, send_result = await execute_tool_block(send_block, context=context)

        return {
            "output": send_result.get("output") or "Email sent",
            "exit_code": 0 if send_result.get("sent") else 1,
            "_artifacts": send_result.get("_artifacts", {}),
        }
