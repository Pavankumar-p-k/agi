from __future__ import annotations

class ThemeManager:
    """
    Manages TUI themes and CSS injections.
    """
    THEMES = {
        "anthropic": {
            "bg": "#30302e",
            "sidebar_bg": "#262624",
            "border": "#3e3e3c",
            "accent": "#c2c0b6",
            "user_border": "blue",
            "agent_border": "green",
        },
        "midnight": {
            "bg": "#0a0a0f",
            "sidebar_bg": "#12121a",
            "border": "#1f1f2e",
            "accent": "#7aa2f7",
            "user_border": "#bb9af7",
            "agent_border": "#7dcfff",
        },
        "solarized": {
            "bg": "#002b36",
            "sidebar_bg": "#073642",
            "border": "#586e75",
            "accent": "#93a1a1",
            "user_border": "#268bd2",
            "agent_border": "#859900",
        }
    }

    @classmethod
    def get_css(cls, theme_name: str) -> str:
        t = cls.THEMES.get(theme_name, cls.THEMES["anthropic"])
        return f"""
        Screen {{ background: {t['bg']}; color: #f0f0f0; }}
        #sidebar {{ background: {t['sidebar_bg']}; border-right: solid {t['border']}; }}
        #hero-banner {{ background: {t['sidebar_bg']}; border-bottom: double {t['border']}; }}
        #chat-stream {{ background: {t['bg']}; }}
        #input-bar {{ background: {t['sidebar_bg']}; border-top: solid {t['border']}; }}
        """
