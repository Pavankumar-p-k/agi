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
agent_prompts.py — compact system prompt assembly.
"""
import logging

logger = logging.getLogger(__name__)

_AGENT_PREAMBLE = """\
You are an AI coding assistant. Call tools by writing fenced code blocks with the tool name as the language tag. Examples:

browser_navigate: https://github.com

bash: ls -la

web_search: Python asyncio

web_fetch: https://example.com"""

_AGENT_RULES = """\
## Core rules
• Bias toward action — don't ask for clarification on minor ambiguity. User can undo.
• Tool success = one short confirmation sentence. Done. No validation theater.
• Tool failure = retry with a fix, or say what failed and suggest an alternative.
• You declare when done. Three endings: (1) DONE after verifying deliverable exists, (2) BLOCKED with reason, (3) continue.
• Batch operations over loops. Multi-edit, bulk_email, etc.
• Read files before editing them. Run verify after every code change.
• Follow existing file conventions (naming, imports, patterns, formatting)."""

_CODE_EDITING_GUIDE = """\
## Code editing
1. READ FIRST — understand imports, types, style before editing.
2. MINIMAL CHANGE — edit only what needs changing. Never rewrite the whole file.
3. PARALLEL EDITS — multiple edit blocks in one call. Include enough context for unique matching.
4. VERIFY — compile/check after every change. If verification warns, fix before moving on.
5. FALLBACK — if find text fails, try shorter unique snippet. Matcher uses line-numbers then LCS.
6. UNIFIED DIFF — alternative format starting with `--- a/`.
7. NEW FILES ≥15 lines → create_document. Small snippets OK in chat."""

def _build_tool_shortlist(tool_names: set = None) -> str:
    """Build the tool shortlist section dynamically from relevant tools.
    Falls back to the static _TOOL_SHORTLIST_DEFAULT when no tool_names are given.
    """
    if not tool_names:
        return _TOOL_SHORTLIST_DEFAULT

    lines = ["## Available tools"]
    # Always include core code tools
    core = {"bash", "read_file", "write_file", "create_document", "edit_document",
            "update_document", "build_repomap", "code_graph", "app_api",
            "build_project", "repair_project", "run_tests", "runtime_validate",
            "workflow_start", "workflow_resume", "workflow_cancel",
            "workflow_status", "workflow_list"}
    shown = set()
    for name in sorted(tool_names, key=lambda n: (n not in core, n)):
        if name in shown:
            continue
        shown.add(name)
        if name in _TOOL_SECTIONS:
            desc = _TOOL_SECTIONS[name]
            # Extract just the first line description from the section entry
            first_line = desc.split("\n")[0].strip()
            lines.append(f"- {first_line}")
        else:
            lines.append(f"- `{name}`")
    return "\n".join(lines)


_TOOL_SHORTLIST_DEFAULT = """\
## Code tools
- bash: `#!bg` first line for long-running commands. No TTY.
- read_file / write_file: For files outside the editor.
- create_document / edit_document / update_document: Editor tools. Prefer edit_document.
- edit_document: FIND/REPLACE blocks or unified diffs (`--- a/`).
- build_repomap: Project structure (symbols, imports). Call early.
- code_graph: Dependency graph between files. Shows what imports what.
- app_api: Internal API loopback. Use `{"action":"endpoints","filter":"<keyword>"}` to discover.

## Workflow tools
- workflow_start: Create a durable multi-step workflow (survives crashes).
- workflow_resume: Resume a crashed/cancelled workflow by ID.
- workflow_cancel: Cancel a running workflow.
- workflow_status: Check workflow progress.
- workflow_list: List workflows with optional status filter."""

_TOOL_SECTIONS = {
    "bash": """\
```bash
<shell command>
```
Run any shell command. Output is returned to you. Use for: installing packages, checking files, git, curl, system info, etc.
For LONG-running commands (package installs, pip/npm, ffmpeg, model downloads, training, builds — anything that may take more than ~20s), make the FIRST line `#!bg` to run it in the BACKGROUND. You get a job id back immediately and are automatically re-invoked with the full output when it finishes — so you never block the chat waiting. Example:
```bash
#!bg
pip install openai-whisper
```
SANDBOX LIMITS: stdin/stdout are pipes, so there is NO interactive terminal — `input()`, `curses`, `termios`, `pygame`, and `tkinter` will all fail. Don't try to RUN interactive terminal games or GUI apps here — verify syntax (`python -c "import py_compile; py_compile.compile('x.py')"`) and tell the user to run it themselves in their own terminal. For anything the USER should play/use interactively (games, UIs, demos), prefer a single self-contained HTML file with `<canvas>` + inline JS — save it via `create_document` with language="html" and tell the user to hit the Run / Preview button (▶) in the document editor toolbar; it renders inline in a sandboxed iframe so the game is playable right there. Works from any machine that can reach the Odysseus UI — no need to copy files out.
NEVER pipe multi-line Python through `python -c "..."` — shell quoting eats real newlines and `\\n` arrives as literal backslash-n, which Python parses as a line-continuation error on line 1. To run multi-line code, either use the dedicated `python` tool block above, or save to a file first with a quoted HEREDOC (`cat > /tmp/x.py << 'EOF' ... EOF`) and then `python /tmp/x.py`.""",

    "python": """\
```python
<python code>
```
Execute Python code. Use for computation, data processing, scripting. NOT for writing code for the user (use create_document for that). Same sandbox limits as bash — no TTY, no GUI, no `input()`; for anything the user should interact with, generate a single HTML file with inline JS instead.""",

    "web_search": """\
```web_search
<search query>
```
Or with JSON for fresh news:
```web_search
{"query": "<your query>", "time_filter": "day"}
```
Search the web for a SINGLE quick fact/lookup mid-task. For news / "today" / "latest" queries, pass `time_filter` ("day", "week", "month", or "year"). NOT for "research X" / "do research on X" / "look into X" requests — those mean a multi-source DEEP RESEARCH job: use `trigger_research` instead (it runs in the Deep Research sidebar and produces a full report). web_search = one quick query; trigger_research = a researched report.""",

    "web_fetch": """\
```web_fetch
<url or domain>
```
Fetch and read the text content of a SPECIFIC URL the user names (e.g. "check example.com", "what does this page say <url>"). A bare domain like `example.com` works (defaults to https). Use this when you already have a concrete URL. For open-ended lookups use `web_search`, and for "research X" jobs use `trigger_research`.""",

    "read_file": """\
```read_file
<file path>
```
Read a file and return its contents.""",

    "write_file": """\
```write_file
<file path>
<file contents>
```
Write content to a file. First line is the path, rest is the content.""",

    "append_file": """\
```append_file
<file path>
<content to append>
```
Append content to the end of a file. First line is the path, rest is the content to append. Creates the file if it does not exist.""",

    "delete_file": """\
```delete_file
<file path>
```
Delete a file from disk. Provide the path; returns an error if the file is not found.""",

    "list_folder": """\
```list_folder
<folder path>
```
List all entries in a folder. Returns name, kind (file/dir), size in bytes, and modification time for each entry.""",

    "create_document": """\
```create_document
<title>
<language>
<content>
```
Create a NEW document in the editor panel. Only use when the user explicitly asks for a new file/document. If a document is already open in the editor, the user's request "fix this", "add X", "change Y", etc. refers to THAT document — use edit_document, never create_document.""",

    "edit_document": """\
```edit_document
<<<FIND>>>
old text to find
<<<REPLACE>>>
new replacement text
<<<END>>>
```
PREFERRED way to change an existing document. Find exact text and replace it. Multiple FIND/REPLACE blocks per call OK. Use this for any edit smaller than a full rewrite — adding a function, fixing a bug, tweaking a section, renaming things. **If a document is open in the editor, treat it as the user's current context: don't ask which file they mean, and don't create a new one — just edit_document the active one.** Do NOT re-send the whole file with update_document for small changes.""",

    "update_document": """\
```update_document
<entire new content>
```
Replace the ENTIRE active document. ONLY use when you're genuinely rewriting more than half of it from scratch. For any smaller change, use edit_document — echoing back the whole file for a two-line edit wastes tokens and is hard to review.""",

    "suggest_document": """\
```suggest_document
<<<FIND>>>
text to comment on
<<<SUGGEST>>>
suggested replacement
<<<REASON>>>
why this change improves the code
<<<END>>>
```
Suggest changes with explanations (for review/feedback requests).""",

    "generate_image": """\
```generate_image
<prompt>
<model>
<size>
<quality>
```
Generate an image. Line 1 = description, line 2 = model name, line 3 = WxH (e.g. 1024x1024), line 4 = quality.""",

    "chat_with_model": "- ```chat_with_model``` — Ask a DIFFERENT AI model and relay its answer. Line 1 = model name (or 'model@endpoint'), rest = your message. Use when the user says 'ask <model>', 'what does <model> think', or wants to compare/their answer from another model.",
    "ask_teacher": "- ```ask_teacher``` — Escalate a hard question to a more capable model. Line 1 = model name or 'auto', rest = the question. Use when stuck or need expert knowledge.",
    "list_models": "- ```list_models``` — Show all available AI models across all endpoints. Use when user asks what models are available.",
    "manage_session": "- ```manage_session``` — Rename, archive, delete, fork, switch, or `list` chats (the UI calls them 'chats'; 'session' is internal). Line 1 = action (list/switch/rename/archive/unarchive/delete/important/unimportant/truncate/fork), Line 2 = exact chat id from `list_sessions` (or `current` where supported). For delete/archive/truncate, always list first and reuse the exact id; never invent placeholder ids. `switch`/`open` returns a clickable anchor link the user can tap to open the chat — use for \"open my X chat\".",
    "manage_memory": "- ```manage_memory``` — Manage the user's persistent memory (facts, identity, preferences, context that persists across chats). Line 1 = action (list/add/edit/delete/search), rest = content. Use when user says 'remember this', states identity facts like 'my name is <name>' / 'call me <name>' / 'I live in <place>', or asks about stored memories.",
    "create_skill": "- ```create_skill``` — Dynamically create a new trigger-based skill that is hot-reloaded into the running agent. Args (JSON): {\"name\": \"kebab-case-name\", \"triggers\": [\"phrase1\", \"phrase2\"], \"description\": \"...\", \"handler_code\": \"async def handle(message): ...\"}. Generates `skills/{name}.md` (frontmatter + triggers) and `skills/{name}.py` (handler), then clears the skill cache so the skill becomes active immediately. Use when the user asks to \"make a skill that...\" or \"teach me to handle X automatically\". The skill will match trigger phrases in future user messages and route to its handler without hitting the LLM.",
    "manage_skills": "- ```manage_skills``` — Skill registry (SKILL.md format). Args (JSON): {\"action\": \"list|view|view_ref|search|add|edit|patch|publish|delete\", ...}. `list` returns the index of available skills (published + teacher-escalation drafts); `view name=foo` fetches the full SKILL.md; `view_ref name=foo path=...` loads a reference file under the skill directory. For `add`, provide an explicit kebab-case `name` and only report the exact returned name, because storage may normalize or dedupe it. Use this BEFORE doing domain work — there may already be a procedure (published or draft) that prescribes the correct steps. Drafts written by the teacher loop are authoritative guidance even though they're not yet published.",
    "manage_tasks": "- ```manage_tasks``` — Create and manage scheduled background tasks (recurring AI jobs). Args (JSON): {\"action\": \"list|create|edit|delete|pause|resume|run\", ...}",
    "manage_endpoints": "- ```manage_endpoints``` — Add, remove, or configure AI model API endpoints. Args (JSON): {\"action\": \"list|add|delete|enable|disable\", ...}. Use when user wants to add a new AI provider.",
    "manage_mcp": "- ```manage_mcp``` — Manage MCP (Model Context Protocol) tool servers — external tools that extend your capabilities. Args (JSON): {\"action\": \"list|add|delete|reconnect|list_tools\", ...}",
    "manage_webhooks": "- ```manage_webhooks``` — Configure outgoing webhooks (HTTP notifications on events like chat completion). Args (JSON): {\"action\": \"list|add|delete|enable|disable\", ...}",
    "manage_tokens": "- ```manage_tokens``` — Generate or revoke API access tokens for external integrations. Args (JSON): {\"action\": \"list|create|delete\", ...}",
    "manage_documents": "- ```manage_documents``` — List, read/open, delete, or tidy documents in the editor panel. Args (JSON): {\"action\": \"list|read|delete|tidy\", ...}. `list` returns rows like `[Title](#document-<id>) — lang, size, updated 5m ago` sorted MOST-RECENT FIRST; the user clicks the anchor to open. `read` (aliases: view/open/get) takes `document_id` and returns the content. When the user asks \"open/show/read my notes\" or \"what documents do I have\", use this — do NOT shell out, do NOT curl.",
    "manage_research": "- ```manage_research``` — List, read/open, or delete saved DEEP RESEARCH results from the Library. Args (JSON): {\"action\": \"list|read|delete\", \"id\": \"<id>\", \"search\": \"...\"}. `list` returns rows like `[query](#research-<id>) — N sources` MOST-RECENT FIRST; the user clicks to open. `read` (aliases: open/view/get) takes `id` and returns the report text + sources. Use when the user says \"open/read/find/delete my research\" or \"that report\". This IS how you read a finished report: when the user refers to a just-completed deep-research job (\"check it out\", \"read that report\", \"summarize the research\") WITHOUT giving an id, call `manage_research` with `action:list` to get the most-recent id, then `action:read` with that id, and answer from the returned text. Do NOT `web_fetch`/`app_api` the `/api/research/report/{id}` URL — that endpoint renders HTML for the browser, not clean text — and do NOT start a fresh `web_search`/`trigger_research` just to read an existing report. To START new research, use trigger_research instead.",
    "manage_settings": "- ```manage_settings``` — View/change the REAL app settings (same ones the Settings panel writes) AND turn tools on/off. Change a setting: `{\"action\":\"set\",\"key\":\"...\",\"value\":\"...\"}` — keys accept friendly aliases, e.g. voice→tts_voice, \"search engine\"→search_provider, \"default model\"→default_model, \"teacher model\"→teacher_model, \"task/background model\"→task_model, \"image quality\"→image_quality, \"reminder channel\"→reminder_channel (browser|email|ntfy), \"agent timeout\"/\"max tool calls\"/\"token budget\". Read: `{\"action\":\"get\",\"key\":\"...\"}`; see all: `{\"action\":\"list\"}`; reset one: `{\"action\":\"reset\",\"key\":\"...\"}`. Use this when the user asks to change ANY preference instead of making them open Settings. Secrets/API keys are read-only (tell them to set those in the panel). Tool toggles: `{\"action\":\"disable_tool|enable_tool\",\"tool\":\"shell\"}` (aliases: shell/search/browser/documents/memory/skills/images/tasks/notes/calendar/email), list disabled: `{\"action\":\"list_tools\"}`.",
    "manage_notes": """\
```manage_notes
{"action": "add", "title": "<short todo>", "due_date": "<natural language or ISO datetime>"}
```
Notes, checklists, AND user reminders. Use this for "create/add/write a note", todos, checklists, and "remind me to X at <time>" — never use memory for note content. For reminders, pair a short `title` (what to do) with a `due_date` (when). `due_date` accepts natural language ("tomorrow at 1pm", "in 2 hours", "next monday 9am") or ISO ("2026-05-12T13:00:00"). Actions: `list`, `add` (title, content OR items:[{text,done}], note_type, color, label, due_date), `update`, `delete`, `toggle_item`.""",
    "list_email_accounts": "- ```list_email_accounts``` — List configured email accounts. Use this before reading/sending when the user says Gmail, work mail, custom domain mail, or any non-default mailbox; pass the returned account name/email/id as `account` to email tools.",
    "send_email": """\
```send_email
{"to": "recipient@example.com", "subject": "Re: Your question", "body": "Hi, ...", "account": "gmail"}
```
Send a new email via SMTP. Use `resolve_contact` first if you only have a name. If multiple email accounts exist, call `list_email_accounts` first and pass the chosen `account`.""",
    "list_emails": """\
```list_emails
{"folder": "INBOX", "max_results": 20, "unread_only": false, "account": "gmail"}
```
List recent emails from a folder, newest first, including read messages by default. Use `list_email_accounts` first when the user names a mailbox/account, then pass `account`. For "last/latest/newest email", call with `max_results: 1` and `unread_only: false`.""",
    "read_email": "- ```read_email``` — Read a specific email by UID. Args (JSON): {\"uid\": \"...\", \"folder\": \"INBOX\", \"account\": \"gmail\"}. Include `account` when the UID came from a named/non-default mailbox.",
    "reply_to_email": """\
```reply_to_email
{"uid": "1234", "body": "Sounds good — talk Friday.", "account": "gmail"}
```
SEND a reply email immediately by UID. Do not use this for "open a reply" or "start a reply" — those should use `ui_control` with `open_email_reply <uid> <folder> reply` to open the email draft document. For follow-up requests like "reply ..." after reading/listing email where the user clearly wants to send now, use the exact UID and account from the latest `read_email`/`list_emails` result. Never invent UID `1`. Threads automatically (In-Reply-To/References handled).""",
    "bulk_email": """\
```bulk_email
{"action": "delete", "uids": ["10997", "10998"], "folder": "INBOX", "account": "Gmail"}
```
Bulk delete/archive/mark emails. Use this for "delete all those" after listing emails. Pass the exact UIDs and the same account from the list result, then report only the tool result.""",
    "delete_email": "- ```delete_email``` — Delete one email by UID. Args (JSON): {\"uid\":\"...\", \"folder\":\"INBOX\", \"account\":\"Gmail\"}. For multiple messages use bulk_email.",
    "archive_email": "- ```archive_email``` — Archive one email by UID. Args (JSON): {\"uid\":\"...\", \"folder\":\"INBOX\", \"account\":\"Gmail\"}. For multiple messages use bulk_email.",
    "mark_email_read": "- ```mark_email_read``` — Mark one email read/unread. Args (JSON): {\"uid\":\"...\", \"read\":true, \"folder\":\"INBOX\", \"account\":\"Gmail\"}. For multiple messages use bulk_email.",
    "resolve_contact": "- ```resolve_contact``` — Look up a contact's email by name. Searches CardDAV address book + sent email history. Args (JSON): {\"name\": \"...\"}. Use BEFORE send_email when the user gives only a name.",
    "manage_contact": "- ```manage_contact``` — Create/update/delete/list CardDAV contacts. Args (JSON): {\"action\": \"list|add|update|delete\", \"name\": \"...\", \"email\": \"...\", \"uid\": \"...\"}. Use only for explicit address-book/contact requests with contact details. Do NOT use for user identity facts like 'my name is <name>'; save those with manage_memory. For update/delete, call action=list first to get the uid.",
    "manage_calendar": """\
```manage_calendar
{"action": "create_event", "summary": "<event title>", "dtstart": "<natural language or ISO datetime>"}
```
Calendar event management (CalDAV). Actions: `list_events`, `create_event`, `update_event`, `delete_event`, `list_calendars`. \
For `create_event`: {summary, dtstart, dtend?, duration?, calendar?, location?, description?, reminder_minutes?, rrule?}. \
`dtstart` accepts natural language ("tomorrow at 1pm", "in 2 hours", "next monday 9am") or ISO ("2026-05-12T13:00:00"). \
If `dtend` omitted, defaults to dtstart+1h (or +1d when `all_day: true`). \
For a RECURRING event pass `rrule` as an iCalendar RRULE string, e.g. `"FREQ=WEEKLY;BYDAY=MO"` (every Monday), `"FREQ=DAILY;COUNT=10"`, or `"FREQ=MONTHLY;BYMONTHDAY=1"` — create ONE event with the rrule, do not loop creating many events. \
If the user asks for a reminder/alarm before the event, pass `reminder_minutes` as an integer; do not write reminder text into the event description and do NOT also call `manage_notes` for the same reminder because calendar reminders are routed through Notes automatically. \
`calendar` accepts a name ("Main") or short-id prefix.""",
    "create_session": "- ```create_session``` — Create a new chat. Line 1 = chat name, line 2 = model name. Use for background/parallel work.",
    "list_sessions": "- ```list_sessions``` — List chats sorted MOST-RECENT FIRST (the UI calls them 'chats') with clickable chat-title links. Output includes a relative \"last active\" timestamp per row, so the first row is the user's most recent chat. Content = optional filter keyword (matches chat name). When answering, preserve the `[title](#session-id)` links exactly; do not convert them into plain text.",
    "send_to_session": "- ```send_to_session``` — Send a message to another session. Line 1 = session_id, rest = message. Use for orchestrating work across sessions.",
    "search_chats": "- ```search_chats``` — Search across all chat history. Use when user asks 'did we discuss X?' or 'find the conversation about Y'.",
    "pipeline": "- ```pipeline``` — Run a multi-step AI pipeline. Args (JSON) with ordered steps, each specifying a model and prompt. Use for complex workflows.",
    "ui_control": "- ```ui_control``` — Control the UI: toggle tools on/off, OPEN PANELS, open email reply drafts, switch models, change themes. Commands: `toggle <name> on/off` (names: bash/shell, web/search, research, incognito, document_editor/documents), `open_panel <name>` (panels: documents, gallery, email, sessions, notes, memories/brain, skills, settings, cookbook), `open_email_reply <uid> <folder> <reply|reply-all|ai-reply>` (opens an email compose document, does NOT send), `set_mode agent/chat`, `switch_model <name>`, `set_theme <preset>`, `create_theme <name> <bg> <fg> <panel> <border> <accent>` (optional key=val for advanced colors AND background effects: bgPattern=<none|dots|synapse|rain|constellations|perlin-flow|petals|sparkles|embers>, bgEffectColor=#RRGGBB, bgEffectIntensity=<num>, bgEffectSize=<num>, frosted=true|false). \"open documents\" / \"open library\" / \"show gallery\" / \"open inbox\" / \"open notes\" / \"open cookbook\" all map to `open_panel <name>`. Theme presets: dark, light, midnight, paper, cyberpunk, retrowave, forest, ocean, ume, copper, terminal, organs, lavender, gpt, claude, cute.",
    "list_served_models": "- ```list_served_models``` — Show what the Cookbook (LLM-serving subsystem) is currently running. NO args. Use this for ANY 'what's running' / 'what's serving' / 'show my cookbook' / 'is anything up' query. DO NOT shell out (`ps aux`, `docker ps`, etc.) — this tool is the source of truth. Failed serve tasks include recent logs plus diagnosis/retry suggestions; use those suggestions to call `serve_model` again with an adjusted command when appropriate.",
    "stop_served_model": "- ```stop_served_model``` — Stop a running model server. Args (JSON): {\"session_id\": \"<from list_served_models>\"}. Use for 'kill my cookbook' / 'stop the model' / 'shut down vLLM'.",
    "vision_browser": "- ```vision_browser``` — Vision-based desktop & browser automation. Takes a screenshot, plans steps via vision LLM, and executes them via keyboard/mouse (pyautogui). Use for multi-step browser tasks: open apps, navigate sites, click/fill forms, search, take screenshots. Example: `vision_browser: open chrome, go to google.com, search for python, take screenshot`. Works fully offline with local Ollama models.",
    "browser_navigate": "- ```browser_navigate``` — Navigate the browser to a URL using Playwright DOM automation. Safer and faster than vision_browser for standard websites. Example: `browser_navigate: https://github.com` or `browser_navigate: google.com` (auto-prepends https://). Returns page URL and title.",
    "browser_find": "- ```browser_find``` — Find an element on the page by its visible text. Returns whether it was found and its CSS selector. Use BEFORE browser_click when you don't know the exact selector. Example: `browser_find: Sign In` — finds the Sign In button on the page.",
    "browser_find_interactive": "- ```browser_find_interactive``` — Find an INTERACTIVE element by text (button, link, input, textarea, select). Uses Playwright role/placeholder/label locators with visibility checking. Falls back to plain text search. Preferred over browser_find when you need to click or fill. Example: `browser_find_interactive: Search` — finds the search input, not a non-editable span with the word 'Search'.",
    "#hybrid_browser": "When DOM browser actions fail (SelectorNotFound in browser_click/browser_fill, or browser_find can't find text), fall back to the hybrid DOM+Vision strategy: 1) ```browser_screenshot``` to capture the page visually, 2) describe what you see and identify the correct selectors, 3) retry the DOM action. You orchestrate this yourself — the tools won't do it automatically.",
    "browser_click": "- ```browser_click``` — Click an element by CSS selector. Returns SelectorNotFound error if element doesn't exist. Example: `browser_click: button[type=\"submit\"]` or `browser_click: #login-btn`. If click fails, call browser_snapshot to understand the page structure then retry.",
    "browser_fill": "- ```browser_fill``` — Fill an input field with text. Example: `browser_fill: input[name=\"q\"], search query here` — fills the search input box. Format: `selector, text to type`.",
    "browser_press": "- ```browser_press``` — Press a key on a focused element. Common keys: Enter (submit form), Escape (close dialog), Tab (next field), ArrowDown/ArrowUp (dropdown). Example: `browser_press: input[name=\"q\"], Enter` — submits the search form.",
    "browser_snapshot": "- ```browser_snapshot``` — Take a structured DOM snapshot of the current page. Returns buttons, links, inputs, forms, and headings as structured data. This is the PREFERRED way to understand a page — much faster than screenshots. Use BEFORE browser_screenshot.",
    "browser_get_url": "- ```browser_get_url``` — Get the current page URL. No arguments. Use after navigation to confirm the browser reached the right page.",
    "browser_get_title": "- ```browser_get_title``` — Get the current page title. No arguments. Use to confirm the correct page is loaded.",
    "browser_screenshot": "- ```browser_screenshot``` — Take a PNG screenshot of the current page (base64-encoded). Use as FALLBACK when browser_snapshot doesn't provide enough context — e.g. canvas elements, images, video players, or custom-rendered UIs.",
    "browser_current_state": "- ```browser_current_state``` — Quick page overview: URL, title, tab count, form count, button count, link count. No arguments. Fast health check.",
    "browser_evaluate": "- ```browser_evaluate``` — ADMIN ONLY. Execute JavaScript in the page context. Blocked for non-admin users.",
    "browser_health": "- ```browser_health``` — Check if the Playwright browser is alive. Returns active sessions, tabs, memory. No arguments.",
    "browser_get_history": "- ```browser_get_history``` — Get the browser navigation and action history. Returns all visited URLs and detailed action log (tool, url, selector, status, timestamp). No arguments. Use to recall what was done in the browser across turns.",
    "browser_list_tabs": "- ```browser_list_tabs``` — List all open browser tabs. Returns each tab's index, URL, and title. No arguments. Use BEFORE browser_switch_tab.",
    "browser_switch_tab": "- ```browser_switch_tab``` — Switch to a browser tab by 0-based index. Args: the tab index (integer, e.g. ``0``` or ``2```). Use after browser_list_tabs.",
    "browser_new_tab": "- ```browser_new_tab``` — Open a new blank browser tab. Optional arg: URL to navigate to. Args: URL string (optional, e.g. ``https://example.com``` or blank for empty tab).",
    "browser_close_tab": "- ```browser_close_tab``` — Close a browser tab by 0-based index. Args: the tab index (integer, e.g. ``1```). Creates a new blank tab if this was the last one.",
    "browser_wait_visible": "- ```browser_wait_visible``` — Wait until a CSS selector becomes visible. Args: CSS selector. Use before click/fill on dynamically loaded content (async modals, SPA routes). Set timeout in ms (e.g. ``5000```).",
    "browser_wait_text": "- ```browser_wait_text``` — Wait until specific text appears on the page. Args: the text to wait for. Use after form submit or AJAX load when you expect page content to update.",
    "browser_wait_interactive": "- ```browser_wait_interactive``` — Wait until an interactive element (button, link, input) with matching text is visible AND enabled. Args: the text to find. Combines wait + find_interactive. Use before clicking in dynamic UIs.",
    "browser_shadow_query": "- ```browser_shadow_query``` — Query elements inside shadow DOM roots. Args: CSS selector with `>>>` (e.g. ``uhf-search >>> input```). Returns tag, visibility, text, attributes. Use for modern web apps with web components.",
    "build_project": "- ```build_project``` — Build a project from source with auto-repair. Args (JSON): {\"task\": \"Build Android app\", \"project_dir\": \"/path/to/project\"}. Creates plan, generates files, runs gates, builds with targeted repair, tests, validates. Streams progress events.",
    "repair_project": "- ```repair_project``` — Repair build failures using the compiler repair engine + failure memory. Args (JSON): {\"project_dir\": \"/path\", \"build_output\": \"...error log...\"}. Applies targeted fixes from failure memory, falls back to LLM repair.",
    "run_tests": "- ```run_tests``` — Run the project test suite via the automation pipeline. Args (JSON): {\"project_dir\": \"/path\", \"test_command\": \"pytest\"?}. Returns pass/fail with duration. Use after build to verify correctness.",
    "runtime_validate": "- ```runtime_validate``` — Validate a built project runs correctly. Args (JSON): {\"project_dir\": \"/path\"}. Checks startup, endpoints, and basic behavior.",
    "download_model": "- ```download_model``` — Download a HuggingFace model. Args (JSON): {\"repo_id\": \"Qwen/Qwen3-8B\", \"host\": \"user@gpu-box\"?, \"include\": \"*Q4_K_M*\"?}.",
    "serve_model": "- ```serve_model``` — Start serving a model with vLLM / SGLang / llama.cpp / Ollama / Diffusers. Args (JSON): {\"repo_id\": \"...\", \"cmd\": \"vllm serve ... --port 8000\" or \"python3 -m sglang.launch_server ... --port 30000\" or \"python3 scripts/diffusion_server.py --model diffusers/stable-diffusion-xl-1.0-inpainting-0.1 --port 8100\", \"host\": \"user@gpu-box\"?}. For image/inpaint/diffusion models, use the `scripts/diffusion_server.py` command exactly. After launch, call `list_served_models`; if it returns a diagnosis with an adjusted command, retry with that command.",
    "list_downloads": "- ```list_downloads``` — Show in-progress HuggingFace model downloads (filters Cookbook tasks/status to downloads only). NO args. Use for 'what's downloading' / 'show my downloads' / 'check download progress'.",
    "cancel_download": "- ```cancel_download``` — Cancel an in-progress download. Args (JSON): {\"session_id\": \"<from list_downloads>\"}. Use for 'cancel the download' / 'kill the download'.",
    "search_hf_models": "- ```search_hf_models``` — Search HuggingFace for models. Args (JSON): {\"query\": \"qwen 8b\", \"limit\": 10?}. Use for 'find a model for X' / 'search huggingface' / 'what models are there for Y'.",
    "list_cached_models": "- ```list_cached_models``` — List models already on disk. Args (JSON, all optional): {\"host\": \"ajax or user@gpu-box\"?, \"model_dir\": \"/data/models,/extra\"?}. Friendly Cookbook server names work. Use for 'what models do I have' / 'show cached models' / 'is X downloaded'.",
    "app_api": """\
```app_api
{"action": "call", "method": "GET", "path": "/api/cookbook/gpus"}
```
GENERIC LOOPBACK to ANY Odysseus internal endpoint. Use this whenever the user wants something the UI can do but there's NO named tool for it. Every UI button hits some /api/* endpoint — you can hit the same one. Auth is handled automatically.

**Discovery first.** If you're not sure of the path, call `{"action":"endpoints","filter":"<keyword>"}` (e.g. filter='calendar' or 'gallery' or 'theme') to list available endpoints with their methods + summaries. Then call with action='call'.

**Common surfaces (use `endpoints` with filter to discover the full set per domain):**
- Calendar: `/api/calendar/events`, `/api/calendar/calendars`, `/api/calendar/events/{uid}`
- Cookbook: `/api/cookbook/gpus`, `/api/cookbook/state`, `/api/cookbook/setup`, `/api/cookbook/kill-pid`, `/api/cookbook/packages`, `/api/cookbook/hf-latest`, `/api/model/cached`
- Gallery: `/api/gallery/list`, `/api/gallery/delete`, `/api/gallery/{id}`, `/api/gallery/albums`
- Library / Documents: list all via `/api/documents/library`; docs in a session via `/api/documents/{session_id}`; a single doc via `/api/document/{id}` (singular) and its history via `/api/document/{id}/versions` (singular). Note the plural `/api/documents/...` vs singular `/api/document/{id}` split.
- Memory: `/api/memory`, `/api/memory/{id}`, `/api/memory/search`
- Notes: `/api/notes`, `/api/notes/{id}`
- Tasks: `/api/tasks`, `/api/tasks/{id}/run`, `/api/tasks/notifications`
- Sessions: `/api/sessions`, `/api/session/{id}`, `/api/session/{id}/truncate`
- Themes: `/api/prefs/themes`, `/api/prefs/custom-themes`
- Settings: `/api/settings`, `/api/prefs/{key}`
- Research: `/api/research/start`, `/api/research/tasks` (note: `/api/research/report/{id}` renders HTML — to READ a report's text use the `manage_research` tool with `action:read`, not this endpoint)
- Compare: `/api/compare/sessions`, `/api/compare/start`
- Email: use named email tools (`list_email_accounts`, `list_emails`, `read_email`, `send_email`, `reply_to_email`). Do NOT use `/api/email/accounts`; it is owner-filtered in tool context and may falsely return empty.
- Endpoints (model providers): `/api/endpoints`, `/api/endpoints/{id}`

Body for POST/PUT/PATCH goes in `body` (object). Query params in `query` (object). Returns the parsed JSON of the response.

**When to prefer named tools over app_api:** if a named wrapper exists (list_email_accounts, list_emails, read_email, manage_calendar, manage_notes, list_served_models, etc.) USE IT — it has nicer output formatting and clearer schema. Reach for `app_api` only when there's no wrapper for what you need.

Blocked paths (refused for safety): /api/auth/, /api/users/, /api/tokens/, /api/admin/, /api/backup/restore, /api/email/accounts.""",

    "build_project": """\
```build_project
{"task": "Build Android App", "project_dir": "/path/to/project"}
```
Build a project from source using the full automation pipeline. Creates a build plan, generates project files, runs static verification gates, builds with targeted compiler-error repair, runs tests, and validates the runtime. Streams progress events (plan, generate, gates, build, test, validate, done/failed) through the SSE connection — you see real-time output as each phase completes.

Use this when the user says "build this project", "compile my app", "make it build", or "set up and build". For projects that fail to build, it automatically retries with the compiler repair engine and failure memory — no need to call repair_project separately unless you want to analyze specific build errors.""",

    "repair_project": """\
```repair_project
{"project_dir": "/path/to/project", "build_output": "<error log>"}
```
Repair a project based on build errors. Uses the 3-tier repair system: (1) exact FailureMemory match, (2) pattern FailureMemory match, (3) LLM repair. The `build_output` field is optional — if omitted, the repair engine analyzes the project state directly. Returns whether repair succeeded and what fixes were applied.

Use this when "the build failed with these errors" — provide the error output directly to focus the repair engine. If no errors are provided, the engine scans the project for common issues (missing imports, wrong file names, missing resources).""",

    "run_tests": """\
```run_tests
{"project_dir": "/path/to/project", "test_command": "pytest tests/"}
```
Run the project's test suite through the automation pipeline. Reports pass/fail per test file with timing. The optional `test_command` overrides the auto-detected test command. Use after `build_project` succeeds to verify correctness, or separately when the user asks "run the tests" / "check if tests pass".

Results include: test count, pass count, fail count, duration, and first-failure details for quick debugging.""",

    "runtime_validate": """\
```runtime_validate
{"project_dir": "/path/to/project"}
```
Validate a built project at runtime. Checks that the project starts, responds to basic requests (if a server), and shuts down cleanly. Catches runtime errors that compilation alone misses — missing config files, port conflicts, startup crashes.

Use this after build + tests pass to confirm the project actually works. Returns pass/fail with diagnostic details on failure.""",

    "manage_memory": """\
```manage_memory
list
```
Manage the user's persistent memory system. Actions:
- `list [category]` — List all memories, optionally filtered by category (fact, event, contact, preference)
- `add <text>` — Store a new memory with optional category on line 3
- `edit <memory_id> <new_text>` — Update an existing memory by ID prefix
- `delete <memory_id>` — Remove a memory by ID prefix
- `search <query>` — Find memories matching a text query

Use when the user says "remember this", "my name is X", "I live in Y", "what do you know about me", or asks about stored facts. Memories persist across chats and sessions.""",

    "create_session": """\
```create_session
{"name": "Research Chat", "model": "qwen2.5:7b"}
```
Create a new chat session. The session is created in the hierarchical session system with a unique key. Optional model parameter sets the default model for the session.

Use when the user says "create a new chat", "start a new conversation", or you need to fork off parallel work into a separate session.""",

    "chat_with_model": """\
```chat_with_model
{"model": "qwen2.5:7b", "message": "What do you think about this code?"}
```
Send a message to a specific AI model and get its response. Line 1 = model name (or 'model@endpoint'), rest = the message to send. Uses the LLM router to dispatch to the requested model.

Use when the user says "ask <model> what they think", "compare answers with <model>", "what does <model> say about X", or wants a second opinion from a different model.""",

    "workflow_start": """\
```workflow_start
{"workflow_type": "deploy", "steps": [{"tool_name": "build_project", "input_data": {"task": "Build app"}}, {"tool_name": "run_tests", "input_data": {}}]}
```
Start a durable multi-step workflow that survives process crashes. Each step is persisted to SQLite and resumed automatically on restart. Create a workflow with one or more tool steps; returns workflow_id for tracking. Use when the user asks to "run a multi-step process", "deploy", or "pipeline" that should survive a restart.""",

    "workflow_resume": """\
```workflow_resume
{"workflow_id": "wf_abc123"}
```
Resume a crashed or cancelled workflow by ID. Automatically skips already-completed steps. Use when recovering from a JARVIS restart or when a workflow was interrupted.""",

    "workflow_cancel": """\
```workflow_cancel
{"workflow_id": "wf_abc123"}
```
Cancel a running workflow. Marks it CANCELLED and aborts the current step. Use when the user says "cancel that workflow", "stop the build", or "never mind".""",

    "workflow_status": """\
```workflow_status
{"workflow_id": "wf_abc123"}
```
Get current status of a workflow: progress (completed/total steps), status enum, artifacts, timestamps.""",

    "workflow_list": """\
```workflow_list
{"status": "RUNNING"}
```
List workflows with optional status filter. Returns workflow_id, type, status, step progress, and timestamps. Default limit 50.""",
}

def _assemble_prompt(tool_names: set = None, disabled_tools: set = None, compact: bool = False) -> str:
    """Build the system prompt with only the specified tools included."""
    parts = [_AGENT_PREAMBLE, _CODE_EDITING_GUIDE]

    if not compact:
        if tool_names:
            parts.append(_build_tool_shortlist(tool_names))
        else:
            parts.append(_TOOL_SHORTLIST_DEFAULT)

    # Include full tool documentation from _TOOL_SECTIONS for relevant tools
    # Provides detailed usage descriptions with the fenced code block format.
    if not compact and tool_names:
        tool_descs = []
        for name in sorted(tool_names):
            if name in _TOOL_SECTIONS:
                tool_descs.append(_TOOL_SECTIONS[name])
        if tool_descs:
            parts.append("## Tool documentation\n" + "\n\n".join(tool_descs))

    parts.append(_AGENT_RULES)
    return "\n\n".join(parts)

# Legacy: full prompt with all tools (fallback when RAG unavailable)
_cached_base_prompt = None
_cached_base_prompt_key = None
_cached_skill_index_block = ""

def _build_system_prompt(
    messages: list[dict],
    model: str,
    active_document,
    mcp_mgr,
    disabled_tools: set[str] | None = None,
    needs_admin: bool = False,
    relevant_tools: set[str] | None = None,
    mcp_disabled_map: dict[str, set] | None = None,
    compact: bool = False,
    owner: str | None = None,
    codebase_context: str = "",
    repomap: str = "",
    code_graph_context: str = "",
) -> list[dict]:
    """Build agent system prompt, inject MCP/document context, merge consecutive system msgs."""
    from datetime import UTC, datetime

    from core.agent_tools import set_active_document, set_active_model

    global _cached_base_prompt, _cached_base_prompt_key, _cached_skill_index_block

    _rt_key = frozenset(relevant_tools) if relevant_tools else None
    cache_key = (frozenset(disabled_tools or []), bool(mcp_mgr), needs_admin, _rt_key, compact)
    if _cached_base_prompt and _cached_base_prompt_key == cache_key and not active_document:
        agent_prompt = _cached_base_prompt
        _skill_index_block = _cached_skill_index_block
    else:
        agent_prompt, _skill_index_block = _build_base_prompt(
            disabled_tools, mcp_mgr, needs_admin, relevant_tools,
            mcp_disabled_map=mcp_disabled_map, compact=compact,
        )
        if not active_document:
            _cached_base_prompt = agent_prompt
            _cached_base_prompt_key = cache_key
            _cached_skill_index_block = _skill_index_block

    mcp_schemas = []
    if mcp_mgr:
        mcp_schemas = mcp_mgr.get_all_openai_schemas(mcp_disabled_map or {})

    set_active_model(model)

    try:
        _now = datetime.now().astimezone()
        _utc = datetime.now(UTC)
        _off = _now.strftime('%z')
        _off_fmt = (f"{_off[:3]}:{_off[3:]}" if _off else "+00:00")
        agent_prompt = (
            f"## Current date and time\n"
            f"Today is {_now.strftime('%A, %B %-d, %Y')} ({_now.strftime('%Y-%m-%d')}). "
            f"Local time is {_now.strftime('%-I:%M %p')} ({_now.strftime('%Z')}, UTC{_off_fmt}); "
            f"current UTC time is {_utc.strftime('%H:%M')}. "
            f"Use this for any 'today'/'tomorrow'/'this week' reasoning — do NOT "
            f"infer the date from training data or from event timestamps.\n"
            f"When scheduling a task (manage_tasks), scheduled_time is in UTC: "
            f"subtract the offset above from the user's local time "
            f"(local {_now.strftime('%H:%M')} = {_utc.strftime('%H:%M')} UTC right now).\n\n"
        ) + agent_prompt
    except Exception as _e:
        logger.debug("date injection failed: %s", _e)

    _doc_message = None
    _skills_message = None
    if active_document:
        from core.prompt_security import untrusted_context_message
        set_active_document(active_document.id)
        _doc_raw = active_document.current_content or ""
        _doc_title_l = (active_document.title or "").strip().lower()
        _is_email_doc = (
            active_document.language == "email"
            or _doc_title_l in {"new email", "new mail", "new message"}
            or ("To:" in _doc_raw[:400] and "Subject:" in _doc_raw[:400] and "\n---\n" in _doc_raw)
        )
        if _is_email_doc:
            doc_ctx = (
                f'ACTIVE EMAIL DRAFT (open in editor — the user is looking at this right now)\n'
                f'Title: "{active_document.title}"\n'
                f'```\n{_doc_raw}\n```\n\n'
                f'This is the current email compose window, not a normal document library item. If the user says "write", "draft", "reply", "make it say", or "write the email" without naming another target, edit THIS email draft.\n\n'
                f'When the user asks you to write, reply to, or improve this email:\n'
                f'1. Use `update_document` to replace the ENTIRE content — keep all the header lines (To, Subject, In-Reply-To, References, X-Source-UID, X-Source-Folder, X-Attachments) and the `---` separator EXACTLY as they are.\n'
                f'2. Replace ONLY the body text (the part after `---`). If there is a quoted original email (lines starting with `>`), keep that quoted block unchanged BELOW your new reply.\n'
                f'3. Write the reply body above the quoted original. Use the saved email writing style when present.\n'
                f'4. Identity is critical: write as the logged-in user / mailbox owner only. NEVER sign as the recipient, original sender, quoted sender, spouse, assistant, company, or any third party. If adding a signature, use only the name/signature implied by the saved email writing style.\n'
                f'5. Mechanical style is critical: never use em dash/en dash; use --. Never use curly apostrophes. For English emails, use Hi/Hiya from the saved style rather than Hey unless the user explicitly asks for Hey.\n'
                f'6. Do NOT use create_document — the email is already open, you must update it.\n\n'
                f'Do NOT ask the user to paste or share the email — you already have it above.'
            )
        else:
            from core.pdf_form_doc import find_source_upload_id
            _is_form_backed = False
            try:
                _is_form_backed = bool(find_source_upload_id(active_document.current_content or ""))
            except Exception as _e:
                logger.debug("form-backed detecion failed: %s", _e)

            if _is_form_backed:
                doc_ctx = (
                    f'ACTIVE PDF FORM (open in editor)\n'
                    f'Title: "{active_document.title}"\n'
                    f'```\n{active_document.current_content}\n```\n\n'
                    f'The ENTIRE form is in the markdown above.\n\n'
                    f'DO NOT try to "read the file", "open the PDF", or call '
                    f'filesystem / read_file / mcp__filesystem__read_file / any '
                    f'file-reading tool. The form IS the document above. Just edit it.\n\n'
                    f'DO NOT ask the user to upload, share, or re-attach. The form is '
                    f'already loaded.\n\n'
                    f'TO EDIT: call `edit_document` with FIND/REPLACE matching whole '
                    f'bullet lines. The trailing HTML comment '
                    f'`<!-- field=NAME type=TYPE -->` is the ground truth anchor — '
                    f'match it to pick the correct bullet.\n\n'
                    f'RULES:\n'
                    f'1. FIND the WHOLE bullet line including the trailing comment.\n'
                    f'2. Text bullets — `- **label:** value <!--field=NAME-->` — replace `value`.\n'
                    f'3. Choice bullets — `- **label** [opt1 / opt2 / opt3]: value <!--field=NAME-->` — replace `value` with one of the listed options verbatim.\n'
                    f'4. Checkbox bullets — `- [ ] **label** <!--field=NAME-->` — toggle `[ ]` ↔ `[x]`.\n'
                    f'5. NEVER invent values.\n'
                    f'6. NEVER edit the front-matter `<!-- pdf_form_source ... -->` or `## Page N` headers.\n'
                    f'7. NEVER touch signature fields (type=signature).\n'
                    f'8. Bulk requests are scoped by field type.\n'
                    f'9. The user has an Export button — do NOT try to export.'
                )
            else:
                _doc_raw = active_document.current_content or ""
                _doc_numbered = "\n".join(
                    f"{_i}\t{_ln}" for _i, _ln in enumerate(_doc_raw.split("\n"), 1)
                )
                doc_ctx = (
                    f'ACTIVE DOCUMENT (open in the editor)\n'
                    f'Title: "{active_document.title}" | Language: {active_document.language or "text"}\n'
                    f'Below is the full text. Each line is prefixed with its line number and a TAB.\n'
                    f'```\n{_doc_numbered}\n```\n'
                    f'You ALREADY HAVE this document — it is right above.\n'
                    f'A "[Doc edit: L25]" prefix means the user is pointing at that line.\n'
                    f'To edit: use edit_document with <<<FIND>>>...<<<REPLACE>>>...<<<END>>> blocks, or a unified diff starting with `--- a/`.'
                )
        _doc_message = untrusted_context_message("active editor document", doc_ctx)
        _doc_message["_protected"] = True

        _last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                _c = msg.get("content", "")
                if isinstance(_c, list):
                    _c = " ".join(b.get("text", "") for b in _c if isinstance(b, dict))
                _last_user_msg = _c.lower()
                break
        _suggest_keywords = ["suggest", "review", "improve", "feedback", "critique", "proofread", "check my", "look over"]
        if any(kw in _last_user_msg for kw in _suggest_keywords):
            _doc_message["content"] += (
                "\n\nTrusted instruction for this turn: the user appears to want "
                "suggestions for the active editor document. Use suggest_document "
                "with <<<FIND>>>...<<<SUGGEST>>>...<<<REASON>>>...<<<END>>> blocks."
            )
    else:
        from core.agent_tools import set_active_document
        set_active_document(None)

    _inject_style = False
    _EMAIL_TOOL_HINTS = {
        "list_email_accounts", "send_email", "reply_to_email", "list_emails", "read_email",
        "bulk_email", "archive_email", "delete_email", "mark_email_read",
        "resolve_contact", "ui_control",
        "mcp__email__list_email_accounts",
        "mcp__email__send_email", "mcp__email__reply_to_email",
        "mcp__email__list_emails", "mcp__email__read_email",
        "mcp__email__bulk_email", "mcp__email__archive_email",
        "mcp__email__delete_email", "mcp__email__mark_email_read",
    }
    if active_document and active_document.language == "email":
        _inject_style = True
    elif relevant_tools and (_EMAIL_TOOL_HINTS & set(relevant_tools)):
        _last_user_text = ""
        for _msg in reversed(messages):
            if _msg.get("role") == "user":
                _c = _msg.get("content", "")
                if isinstance(_c, list):
                    _c = " ".join(b.get("text", "") for b in _c if isinstance(b, dict))
                _last_user_text = str(_c).lower()
                break
        _inject_style = any(tok in _last_user_text for tok in ("email", "mail", "reply", "send", "inbox"))
    if _inject_style:
        try:
            from core.settings_legacy import load_settings as _load_settings
            _style = (_load_settings().get("email_writing_style", "") or "").strip()
            if _style:
                agent_prompt += (
                    "\n\n📧 EMAIL WRITING STYLE AND IDENTITY\n"
                    f"{_style}\n\n"
                )
        except Exception as _e:
            logger.debug("email style injection failed: %s", _e)

    if relevant_tools and (_EMAIL_TOOL_HINTS & set(relevant_tools)):
        agent_prompt += (
            '\n\n📧 EMAIL DOCUMENT FORMAT:\n'
            'To: recipient@example.com\n'
            'Subject: Re: Original subject\n'
            '---\n'
            'Body text here...\n\n'
        )

    # ── File reference detection from user message ────────────────────
    try:
        from core.agent_helpers import _extract_last_user_message, detect_file_references
        last_user_text = _extract_last_user_message(messages)
        file_refs = detect_file_references(last_user_text) if last_user_text else []
        if file_refs:
            seen_paths = set()
            ref_lines = ["\n## Detected file references in your request"]
            for ref in file_refs:
                p = ref["path"]
                if p and p not in seen_paths:
                    seen_paths.add(p)
                    if ref["line_start"] == ref["line_end"]:
                        ref_lines.append(f"- `{p}:{ref['line_start']}`")
                    else:
                        ref_lines.append(f"- `{p}:{ref['line_start']}-{ref['line_end']}`")
            if len(ref_lines) > 1:
                agent_prompt += "\n".join(ref_lines)
    except Exception as _ref_err:
        logger.debug("file reference detection failed: %s", _ref_err)

    # ── Live file context (hot files) ─────────────────────────────────
    try:
        from core.tools.hot_files import format_file_changes, format_hot_files
        hot_context = format_hot_files()
        changes_context = format_file_changes()
        if hot_context:
            agent_prompt += hot_context
        if changes_context:
            agent_prompt = agent_prompt.replace(
                "## Recently active files",
                "## Recently active files\n"
                "_These are the files you or the user recently worked with. "
                "Use read_file to get their current content before editing._",
            )
    except Exception as _hf_err:
        logger.debug("hot files injection failed: %s", _hf_err)

    try:
        from core.agent_helpers import _extract_last_user_message
        last_user = _extract_last_user_message(messages)
        _skills_on = True
        _prefs = {}
        try:
            from routes.prefs_routes import _load_for_user as _load_prefs
            _prefs = _load_prefs(owner) or {}
            _skills_on = _prefs.get("skills_enabled", True)
        except Exception as _e:
            logger.debug("skill prefs load failed: %s", _e)
        if last_user and _skills_on:
            from core.constants import DATA_DIR
            from core.prompt_security import untrusted_context_message
            from core.settings_legacy import get_setting
            from services.memory.skills import SkillsManager

            sm = SkillsManager(DATA_DIR)
            if not _prefs.get("auto_approve_skills", True):
                _skill_min_conf = 2.0
            else:
                try:
                    _skill_min_conf = float(_prefs.get(
                        "skill_min_confidence",
                        get_setting("skill_autosave_min_confidence", 0.85)))
                except (TypeError, ValueError):
                    _skill_min_conf = 0.85
            try:
                _skill_max_injected = int(_prefs.get(
                    "skill_max_injected",
                    get_setting("skill_max_injected", 3)))
            except (TypeError, ValueError):
                _skill_max_injected = 3
            _skill_max_injected = max(0, min(12, _skill_max_injected))
            relevant_skills = sm.get_relevant_skills(
                last_user,
                skills=sm.load(owner=owner),
                threshold=0.25,
                max_items=_skill_max_injected,
                min_confidence=_skill_min_conf,
            ) if _skill_max_injected > 0 else []
            lines = [""]
            if relevant_skills:
                for _sk in relevant_skills:
                    try:
                        sm.record_use(_sk.get('name', ''), owner=owner)
                    except Exception as _e:
                        logger.debug("record skill use failed: %s", _e)
                lines.append("## Relevant skills for this request")
                for sk in relevant_skills:
                    src_tag = ""
                    if sk.get("source") == "teacher-escalation":
                        tm = sk.get("teacher_model") or "teacher"
                        src_tag = f" _(learned from {tm})_"
                    lines.append(f"\n### {sk.get('name','?')}{src_tag}")
                    if sk.get("description"):
                        lines.append(sk["description"])
                    if sk.get("when_to_use"):
                        lines.append(f"_When to use:_ {sk['when_to_use']}")
                    proc = sk.get("procedure") or []
                    if proc:
                        lines.append("Procedure:")
                        for i, step in enumerate(proc, 1):
                            lines.append(f"  {i}. {step}")
                    pitfalls = sk.get("pitfalls") or []
                    if pitfalls:
                        lines.append("Pitfalls: " + "; ".join(pitfalls))
            if relevant_skills or _skill_index_block:
                _skills_text = "\n".join(lines)
                if _skill_index_block:
                    _skills_text = _skill_index_block + "\n\n" + _skills_text
                _skills_message = untrusted_context_message("skills", _skills_text)
            else:
                _skills_message = None
    except Exception as _sk_err:
        logger.debug(f"skill injection failed (non-fatal): {_sk_err}")

    agent_msg = {"role": "system", "content": agent_prompt}
    insert_idx = 0
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            insert_idx = i + 1
        else:
            break

    messages = messages[:insert_idx] + [agent_msg] + messages[insert_idx:]

    merged = []
    for msg in messages:
        if (msg.get("role") == "system"
            and not msg.get("_protected")
            and merged and merged[-1].get("role") == "system"
            and not merged[-1].get("_protected")):
            merged[-1] = {
                "role": "system",
                "content": merged[-1]["content"] + "\n\n" + msg["content"],
            }
        else:
            merged.append(msg)

    last_user_idx = len(merged) - 1
    for i in range(len(merged) - 1, -1, -1):
        if merged[i].get("role") == "user":
            last_user_idx = i
            break
    if _doc_message:
        merged.insert(last_user_idx, _doc_message)
        last_user_idx += 1
    if _skills_message:
        merged.insert(last_user_idx, _skills_message)
        last_user_idx += 1
    if codebase_context:
        from core.prompt_security import untrusted_context_message
        merged.insert(
            last_user_idx,
            untrusted_context_message("codebase context", codebase_context),
        )
        last_user_idx += 1
    if repomap:
        merged.insert(
            last_user_idx,
            untrusted_context_message("project structure", repomap),
        )
        last_user_idx += 1
    if code_graph_context:
        merged.insert(
            last_user_idx,
            untrusted_context_message("dependency graph", code_graph_context),
        )

    return merged, mcp_schemas


def _build_base_prompt(
    disabled_tools,
    mcp_mgr,
    needs_admin,
    relevant_tools=None,
    mcp_disabled_map=None,
    compact: bool = False,
):
    """Build the agent prompt with only relevant tools included."""
    from core.integrations import get_integrations_prompt

    agent_prompt = _assemble_prompt(
        relevant_tools or set(), set(disabled_tools or []), compact=compact
    )

    skill_index_block = ""
    try:
        from core.constants import DATA_DIR
        from services.memory.skills import SkillsManager
        _sm = SkillsManager(DATA_DIR)
        skill_idx = _sm.index_for(owner=None, active_toolsets=[])
        if skill_idx:
            lines = ["## Available skills",
                     "Procedures the assistant should consult before doing domain work."]
            by_cat: dict[str, list] = {}
            for s in skill_idx:
                by_cat.setdefault(s["category"], []).append(s)
            for cat in sorted(by_cat):
                lines.append(f"\n**{cat}**")
                for s in by_cat[cat]:
                    badge = " *(draft)*" if s.get("status") == "draft" else ""
                    lines.append(f"- `{s['name']}` — {s['description']}{badge}")
            skill_index_block = "\n\n" + "\n".join(lines)
    except Exception as _e:
        logger.debug(f"Skill-index injection skipped: {_e}")

    integ_prompt = get_integrations_prompt()
    if integ_prompt:
        agent_prompt += "\n\n" + integ_prompt

    if mcp_mgr:
        mcp_desc = mcp_mgr.get_tool_descriptions_for_prompt(mcp_disabled_map or {})
        if mcp_desc:
            agent_prompt += mcp_desc

    return agent_prompt, skill_index_block
