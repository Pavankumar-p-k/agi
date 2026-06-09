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
# Auto-generated schema definitions for create_document, edit_document, edit_file, manage_documents, search_chats, suggest_document, update_document
FUNCTION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "create_document",
            "description": "Create a new document in the editor panel. Use this when the user asks to write, create, build, or generate code, scripts, programs, games, apps, or any substantial content (>15 lines) AND there is no already-open document/email draft that the request refers to. If an email compose draft is open, edit that draft instead of creating another document. NEVER put large code blocks directly in chat — use this tool instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Document title"},
                    "language": {"type": "string", "description": "Programming language or format (e.g. python, javascript, markdown, text)"},
                    "content": {"type": "string", "description": "The document content"}
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit an existing code file on disk using targeted FIND/REPLACE. Creates automatic backups. Preferred over write_file for small changes: add a function, fix a bug, tweak a section, rename things. For more than 50% changes, use write_file instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file to edit (relative to workspace or absolute)"},
                    "edits": {
                        "type": "array",
                        "description": "List of find/replace edits to apply in order. Each edit replaces the first occurrence of 'find' with 'replace'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string", "description": "Exact text to find in the file"},
                                "replace": {"type": "string", "description": "Text to replace it with"}
                            },
                            "required": ["find", "replace"]
                        }
                    }
                },
                "required": ["file_path", "edits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "refactor",
            "description": "Decompose a high-level refactoring goal into actionable steps and execute them. Provide a natural-language goal like 'extract email validation to shared module' or 'rename getData to fetchData everywhere', optionally list the files involved. Can apply specific FIND/REPLACE edits or generate a plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "High-level refactoring goal in natural language"},
                    "files": {"type": "string", "description": "Comma-separated file paths to refactor (optional)"},
                    "edits": {
                        "type": "array",
                        "description": "Optional FIND/REPLACE edits to apply across all files",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string", "description": "Exact text to find"},
                                "replace": {"type": "string", "description": "Text to replace it with"}
                            },
                            "required": ["find", "replace"]
                        }
                    }
                },
                "required": ["goal"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "undo_edit_file",
            "description": "Restore the most recent backup of a file edited with edit_file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to restore"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "batch_edit_file",
            "description": "Edit multiple files at once using a glob pattern. Each matching file gets the same FIND/REPLACE applied in order. Use for renaming across files, fixing a pattern everywhere, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern matching files to edit (e.g. 'src/**/*.py')"},
                    "edits": {
                        "type": "array",
                        "description": "List of find/replace edits to apply to each matched file",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string", "description": "Exact text to find"},
                                "replace": {"type": "string", "description": "Text to replace it with"}
                            },
                            "required": ["find", "replace"]
                        }
                    }
                },
                "required": ["pattern", "edits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_document",
            "description": "PREFERRED way to change an existing document. You can use one of two formats: (1) FIND/REPLACE blocks, or (2) a unified diff (context diff). For FIND/REPLACE, provide multiple find/replace pairs per call. For unified diff, put the full diff (starting with `--- a/`) as the single edit's find text with an empty replace. Use this for any edit smaller than a full rewrite: adding a function, fixing a bug, tweaking a section, renaming things. Do NOT send the whole file back via update_document for small edits — it wastes tokens and is hard to review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "edits": {
                        "type": "array",
                        "description": "List of find/replace edits (first match only per edit). Can target different documents by setting doc_id on each edit. For unified diffs, put the full diff in 'find' and an empty string in 'replace'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string", "description": "Exact text to find in the document, or a unified diff (starts with `--- a/`)"},
                                "replace": {"type": "string", "description": "Text to replace it with (leave empty for unified diffs)"},
                                "doc_id": {"type": "string", "description": "Optional document ID. Defaults to the active document. Use to edit multiple files in one call."}
                            },
                            "required": ["find", "replace"]
                        }
                    }
                },
                "required": ["edits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_document",
            "description": "Suggest improvements to the active document WITHOUT editing it. Creates inline comment bubbles the user can accept or reject. Use when the user asks for suggestions, review, improvements, or feedback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "description": "List of suggested changes with reasons",
                        "items": {
                            "type": "object",
                            "properties": {
                                "find": {"type": "string", "description": "Exact text in the document to suggest changing"},
                                "replace": {"type": "string", "description": "Suggested replacement text"},
                                "reason": {"type": "string", "description": "Brief explanation of why this change helps"}
                            },
                            "required": ["find", "replace", "reason"]
                        }
                    }
                },
                "required": ["suggestions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_document",
            "description": "Replace the ENTIRE active document. ONLY use for genuine full rewrites (>50% of lines changed). For any smaller change, use edit_document — echoing back the whole file for small edits is wasteful.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Complete new document content"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_chats",
            "description": "Search the user's past chat conversations by keyword. Use when the user asks about previous chats, past conversations, or wants to find a discussion they had before. Returns matching sessions with clickable links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword(s) to find in past conversations"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_documents",
            "description": "Manage documents: list all documents (with optional search/language filter), delete documents, or run tidy cleanup.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "delete", "tidy"]},
                    "document_id": {"type": "string", "description": "Document ID (for delete)"},
                    "search": {"type": "string", "description": "Search query (for list)"},
                    "language": {"type": "string", "description": "Filter by language (for list)"},
                    "limit": {"type": "integer", "description": "Max results (for list, default 50)"}
                },
                "required": ["action"]
            }
        }
    },
]
