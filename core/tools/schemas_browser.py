FUNCTION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate the browser to a URL. Returns page loaded status and current URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full URL (including https://) to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_find",
            "description": "Find all elements on the page whose visible text matches the given text. Returns matching elements with their selectors, text, and tag info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Visible text to search for on the page"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_find_interactive",
            "description": "Find interactive elements (links, buttons, inputs) whose visible text contains the given text. Returns matching elements with selectors suitable for click/fill.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to search for in interactive elements"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on the page identified by a CSS selector. Optionally force-click even if hidden.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the element to click"},
                    "force": {"type": "boolean", "description": "Force click even if element is hidden", "default": False}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Fill a form field (input, textarea, etc.) identified by a CSS selector with the given text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the form field"},
                    "text": {"type": "string", "description": "Text to type into the field"}
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press",
            "description": "Press a keyboard key (e.g. 'Enter', 'Escape', 'Tab') on a focused element or the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of element to press key on (empty for page-level)"},
                    "key": {"type": "string", "description": "Key to press (e.g. 'Enter', 'ArrowDown', 'Escape')"}
                },
                "required": ["selector", "key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Get a snapshot of the current page content as visible text. Use this after navigation to see what the page contains.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_url",
            "description": "Get the current URL of the browser tab.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_title",
            "description": "Get the title of the current browser tab.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a screenshot of the current page and return the image data.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_current_state",
            "description": "Get the full current state of the page including URL, title, visible text, and interactive elements.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_evaluate",
            "description": "Execute arbitrary JavaScript code in the browser page context and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "js": {"type": "string", "description": "JavaScript code to execute in the page"}
                },
                "required": ["js"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_history",
            "description": "Get the navigation history of the current browser tab.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_list_tabs",
            "description": "List all open browser tabs with their titles and indices.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_switch_tab",
            "description": "Switch to a different browser tab by its index (0-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "0-based index of the tab to switch to"}
                },
                "required": ["index"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_new_tab",
            "description": "Open a new browser tab, optionally navigating to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Optional URL to navigate to in the new tab"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close_tab",
            "description": "Close a browser tab by its index (0-based). If no index given, closes the current tab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "0-based index of the tab to close (default: current tab)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait_visible",
            "description": "Wait for an element identified by CSS selector to become visible on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to wait for"},
                    "timeout": {"type": "integer", "description": "Maximum wait time in milliseconds", "default": 10000}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait_text",
            "description": "Wait for text to appear on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to wait for on the page"},
                    "timeout": {"type": "integer", "description": "Maximum wait time in milliseconds", "default": 10000}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait_interactive",
            "description": "Wait for an interactive element containing the given text to become visible and actionable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to search for in interactive elements"},
                    "timeout": {"type": "integer", "description": "Maximum wait time in milliseconds", "default": 10000}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_shadow_query",
            "description": "Query elements inside a Shadow DOM by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the shadow host element"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_health",
            "description": "Check if the browser is still alive and responsive.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vision_browser",
            "description": "Process a screenshot of the current browser page through a vision model to extract and interpret visual information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "A description of what to look for or analyze in the current browser view"}
                },
                "required": ["content"]
            }
        }
    },
]
