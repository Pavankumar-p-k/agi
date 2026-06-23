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
"""Fix silent except Exception as e:     logger.warning(f"[SWALLOWED] {e}") blocks across the codebase.
AST-based: finds, patches, verifies compilation."""
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files to skip (reference copies, generated, third-party)
SKIP_FILES = {
    "integrations/JARVIS_FUTURE_UPGRADES/REF_EMAIL_TRIAGE.py",
    "integrations/JARVIS_FUTURE_UPGRADES/REF_RESEARCH_PIPELINE.py",
    "integrations/JARVIS_FUTURE_UPGRADES/REF_HARDWARE_DETECTION.py",
    "integrations/JARVIS_FUTURE_UPGRADES/REF_DEEP_RESEARCH_LOGIC.py",
    "integrations/JARVIS_FUTURE_UPGRADES/REF_SEARCH_PROVIDERS.py",
}

# Specific known instances with line numbers from the audit
# Format: (relative_path, line_number)
TARGETS = [
    ("mcp/email_server.py", 124, "cleanup_email_connection"),
    ("mcp/email_server.py", 212, "fetch_email"),
    ("mcp/email_server.py", 271, "send_email"),
    ("mcp/email_server.py", 492, "handle_email_webhook"),
    ("mcp/email_server.py", 586, "sync_emails"),
    ("mcp/email_server.py", 1515, "email_scheduler_tick"),
    ("core/tools/execution.py", 560, "execute_tool"),
    ("core/tools/execution.py", 642, "process_tool_result"),
    ("core/tools/execution.py", 937, "handle_parallel_execution"),
    ("core/tools/execution.py", 945, "handle_parallel_execution"),
    ("ai_os/docker_sandbox.py", 82, "init_client"),
    ("ai_os/docker_sandbox.py", 118, "exec_python"),
    ("ai_os/docker_sandbox.py", 159, "exec_bash"),
    ("ai_os/docker_sandbox.py", 174, "exec_command"),
    ("routers/setup.py", 180, "install_dependencies"),
    ("routers/setup.py", 193, "install_dependencies"),
    ("routers/setup.py", 222, "configure_environment"),
    ("routers/setup.py", 602, "refresh_routes"),
    ("core/graph/nodes.py", 155, "execute_node"),
    ("core/graph/nodes.py", 161, "execute_node"),
    ("core/graph/nodes.py", 170, "execute_node"),
    ("mcp/memory_server.py", 120, "store_memory"),
    ("mcp/memory_server.py", 146, "recall_memory"),
    ("mcp/memory_server.py", 171, "delete_memory"),
    ("mcp/rag_server.py", 35, "initialize_rag"),
    ("mcp/rag_server.py", 42, "initialize_rag"),
    ("mcp/rag_server.py", 125, "query_rag"),
    ("mcp/image_gen_server.py", 107, "generate_image"),
    ("mcp/image_gen_server.py", 141, "check_image_status"),
    ("automation/pc_automation.py", 146, "execute_pc_action"),
    ("automation/pc_automation.py", 274, "monitor_processes"),
    ("automation/messaging.py", 145, "send_message"),
    ("automation/messaging.py", 178, "poll_inbox"),
    ("core/routes/websocket.py", 211, "handle_websocket_message"),
    ("core/routes/websocket.py", 297, "broadcast_event"),
    ("skills/library/entertainment/spotify/main.py", 73, "spotify_play"),
    ("skills/library/entertainment/spotify/main.py", 120, "spotify_control"),
    ("skills/library/productivity/url_shortener/main.py", 16, "shorten_url"),
    ("skills/library/productivity/url_shortener/main.py", 24, "expand_url"),
    ("routers/screen.py", 40, "capture_screen"),
    ("routers/screen.py", 53, "process_screen"),
    ("jarvis.py", 37, "build_parser_website_commands"),
    ("jarvis.py", 64, "build_parser_governance_commands"),
    ("tools/jarvis_website_cli.py", 151, "generate_website"),
    ("tools/jarvis_website_cli.py", 173, "deploy_website"),
    ("tests/unit/test_ssrf_fuzz.py", 86, "ssrf_fuzz_test"),
    ("tests/unit/test_ssrf_fuzz.py", 144, "ssrf_fuzz_test"),
    ("mcp/server.py", 520, "mcp_handle_request"),
    ("channels/irc_channel.py", 119, "irc_connect"),
    ("core/routes/chat.py", 78, "process_chat_message"),
    ("core/routes/operations.py", 30, "handle_operation"),
    ("core/tools/document_tools.py", 774, "apply_unified_diff"),
    ("assistant/voice_pipeline.py", 143, "process_voice_command"),
    ("pc_agent/computer_agent.py", 100, "control_computer"),
    ("cli_completer.py", 64, "complete_command"),
    ("cli_slash_commands.py", 47, "execute_slash_command"),
    ("ai_os/sandbox_manager.py", 92, "sandbox_execute"),
    ("tests/deep_check_chat.py", 100, "verify_chat_response"),
    ("tools/executor.py", 587, "run_analysis"),
    ("tools/search_tool.py", 142, "perform_search"),
    ("tools/website_generator.py", 774, "generate_website_content"),
]


def patch_file(rel_path: str, line_no: int, context: str) -> bool:
    """Replace 'except Exception:\\n    pass' with logger.warning(...) at given line."""
    full_path = ROOT / rel_path
    if not full_path.exists():
        print(f"  SKIP {rel_path}:{line_no} — file not found")
        return False

    try:
        text = full_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"  SKIP {rel_path}:{line_no} — read error: {e}")
        return False

    lines = text.splitlines(keepends=True)
    # Convert 1-indexed to 0-indexed
    idx = line_no - 1
    if idx >= len(lines):
        print(f"  SKIP {rel_path}:{line_no} — line out of range")
        return False

    line = lines[idx]

    # Only patch if it's an except line that ends with ':'
    stripped = line.strip()
    if not stripped.startswith("except") or not stripped.endswith(":"):
        print(f"  SKIP {rel_path}:{line_no} — not an except line: {stripped!r}")
        return False

    # Check if next non-empty line is just 'pass'
    next_idx = idx + 1
    while next_idx < len(lines) and lines[next_idx].strip() == "":
        next_idx += 1
    if next_idx < len(lines) and lines[next_idx].strip() == "pass":
        # Found: except...:\n    pass
        module_name = rel_path.replace("/", ".").replace("\\", ".").rstrip(".py")
        indent = lines[next_idx][:len(lines[next_idx]) - len(lines[next_idx].lstrip())]
        lines[next_idx] = f"{indent}logger.warning(\"[{module_name}] {context} failed: %s\", e)\n"

        # Ensure there's a logger import
        # Check if the 'import logging' and 'logger = ...' already exist
        has_logging_import = any("import logging" in l for l in lines)
        has_logger_def = any("logger = logging.getLogger" in l or "logger = logging.getChild" in l for l in lines)

        if not has_logger_def:
            # Find good insertion point (after imports, before class/def)
            insert_idx = 0
            for i, l in enumerate(lines):
                if l.startswith("import ") or l.startswith("from "):
                    insert_idx = i + 1
                elif l.startswith("class ") or l.startswith("def ") or l.startswith("@") or l.strip() == "":
                    continue
                elif insert_idx > 0:
                    break

            if not has_logging_import:
                lines.insert(0, "import logging\n")
                insert_idx += 1
                has_logging_import = True

            # Add logger = logging.getLogger(__name__) after imports
            indent_lvl = ""
            lines.insert(insert_idx, f"{indent_lvl}logger = logging.getLogger(__name__)\n")

        full_path.write_text("".join(lines), encoding="utf-8")
        print(f"  FIXED {rel_path}:{line_no} ({context})")
        return True
    else:
        print(f"  SKIP {rel_path}:{line_no} — next line is not 'pass': {lines[next_idx].strip() if next_idx < len(lines) else 'EOF'!r}")
        return False


def verify_compiles(rel_path: str) -> bool:
    """Check that the file still parses as valid Python."""
    full_path = ROOT / rel_path
    try:
        ast.parse(full_path.read_text(encoding="utf-8", errors="replace"))
        return True
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {rel_path}: {e}")
        return False


def main():
    fixed = 0
    skipped = 0
    failed = 0
    for rel_path, line_no, context in TARGETS:
        if rel_path in SKIP_FILES:
            skipped += 1
            continue
        if patch_file(rel_path, line_no, context):
            if verify_compiles(rel_path):
                fixed += 1
            else:
                failed += 1
        else:
            skipped += 1

    print(f"\nDone: {fixed} fixed, {failed} compile errors, {skipped} skipped")


if __name__ == "__main__":
    main()
