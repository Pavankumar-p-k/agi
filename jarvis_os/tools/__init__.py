from __future__ import annotations

import os

from ..browser import LocalBrowserController
from .ai_tools import register_ai_tools
from .automation_tools import register_automation_tools
from .browser_tools import register_browser_tools
from .coding_tools import register_coding_tools
from .communication_tools import register_communication_tools
from .file_tools import register_file_tools
from .internet_tools import register_internet_tools
from .system_tools import register_system_tools
from .tool_registry import ToolRegistry


def create_tool_registry(config, memory, models) -> ToolRegistry:
    registry = ToolRegistry(config=config, memory=memory, models=models)
    registry.browser_controller = LocalBrowserController(
        {
            "profile_dir": config.data_dir / "browser" / f"profile_{os.getpid()}",
            "headless": bool(getattr(config, "browser_headless", True)),
        }
    )
    register_browser_tools(registry)
    register_system_tools(registry)
    register_file_tools(registry)
    register_internet_tools(registry)
    register_coding_tools(registry)
    register_ai_tools(registry)
    register_automation_tools(registry)
    register_communication_tools(registry)
    registry.register_aliases(
        {
            "browser_open": "open_browser",
            "browser_launch": "open_browser",
            "open_site": "open_browser",
            "browser_search": "search_google",
            "google_search": "search_google",
            "search_web": "search_google",
            "browser_summary": "summarize_page",
            "page_summarize": "summarize_page",
            "page_summary": "summarize_page",
            "page_scrape": "scrape_page",
            "page_extract": "scrape_page",
            "url_open": "open_url",
            "file_read": "read_file",
            "file_open": "read_file",
            "text_file_read": "read_file",
            "file_write": "write_file",
            "file_save": "write_file",
            "text_file_write": "write_file",
            "file_list": "list_directory",
            "dir_list": "list_directory",
            "directory_list": "list_directory",
            "folder_list": "list_directory",
            "file_find": "search_files",
            "file_lookup": "search_files",
            "directory_search": "search_files",
            "web_lookup": "web_search",
            "internet_search": "web_search",
            "search_internet": "web_search",
            "news_fetch": "rss_news_fetch",
            "news_rss": "rss_news_fetch",
            "headline_fetch": "rss_news_fetch",
            "url_fetch": "fetch_url",
            "http_fetch": "fetch_url",
            "file_download": "download_file",
            "url_download": "download_file",
            "shell_run": "run_terminal_command",
            "terminal_run": "run_terminal_command",
            "command_run": "run_terminal_command",
            "system_info": "system_information",
            "host_info": "system_information",
            "device_info": "system_information",
            "cpu_stats": "cpu_usage",
            "processor_usage": "cpu_usage",
            "memory_stats": "memory_usage",
            "ram_usage": "memory_usage",
            "app_open": "open_application",
            "application_open": "open_application",
            "code_generate": "generate_code",
            "codegen": "generate_code",
            "starter_code": "generate_code",
            "code_analyze": "analyze_code",
            "code_review": "analyze_code",
            "repo_analyze": "analyze_code",
            "code_debug": "debug_code",
            "bug_diagnose": "debug_code",
            "error_analyze": "debug_code",
            "python_run": "run_python",
            "python_execute": "run_python",
            "script_run": "run_python",
            "git_check": "git_status",
            "git_state": "git_status",
            "git_snapshot": "git_status",
            "git_save": "git_commit",
            "git_publish": "git_push",
            "notify": "send_notification",
            "notification_send": "send_notification",
            "desktop_notify": "send_notification",
            "email_send": "send_email",
            "mail_send": "send_email",
            "outbound_email": "send_email",
            "workflow_run": "workflow_runner",
            "workflow_execute": "workflow_runner",
            "pipeline_run": "workflow_runner",
            "schedule": "schedule_task",
            "task_schedule": "schedule_task",
            "job_schedule": "schedule_task",
            "task_repeat": "repeat_task",
            "job_repeat": "repeat_task",
            "schedule_list": "list_schedules",
            "schedule_show": "list_schedules",
            "schedule_remove": "cancel_schedule",
            "schedule_delete": "cancel_schedule",
            "text_summarize": "summarize_text",
            "content_summarize": "summarize_text",
            "text_classify": "classify_text",
            "content_classify": "classify_text",
            "entity_extract": "extract_entities",
            "named_entity_extract": "extract_entities",
            "doc_generate": "generate_documentation",
            "documentation_generate": "generate_documentation",
            "event_log_append": "log_event",
            "event_log_read": "read_event_log",
            "event_history": "read_event_log",
        }
    )
    return registry
