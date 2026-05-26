"""core/morning_digest.py
Personalized morning brief — weather, reminders, AI news, GitHub activity.
Scheduled daily@09:00 by JarvisScheduler.
"""

import asyncio
import json
import logging
from datetime import datetime, date

from .llm_router import complete as llm_complete
from .database import AsyncSessionLocal, Reminder
from .integrations import get_weather
from sqlalchemy import select

logger = logging.getLogger("morning_digest")

USER_NAME = "Pavan"
DEFAULT_LOCATION = "Gudlavalleru"


async def generate_morning_digest(user_id: str = "default") -> str:
    """
    Pulls data from multiple sources and generates
    a personalized morning brief for the user.
    Like Claude Cowork's morning digest.
    """
    sections = []

    # 1. Weather
    try:
        weather = await asyncio.to_thread(get_weather, DEFAULT_LOCATION)
        sections.append(f"Weather in {DEFAULT_LOCATION}: {weather}")
    except Exception as e:
        logger.warning(f"[DIGEST] Weather failed: {e}")

    # 2. Today's reminders
    try:
        reminders = await _get_todays_reminders(user_id)
        if reminders:
            items = [f"- {r}" for r in reminders]
            sections.append("Reminders today:\n" + "\n".join(items))
        else:
            sections.append("No reminders for today.")
    except Exception as e:
        logger.warning(f"[DIGEST] Reminders failed: {e}")

    # 3. AI news via SearXNG
    try:
        news = await _search_news("AI news today 2026", max_results=3)
        if news:
            headlines = [n.get("title", n.get("url", "")) for n in news[:3]]
            sections.append("Latest AI news:\n" + "\n".join(f"- {h}" for h in headlines))
    except Exception as e:
        logger.warning(f"[DIGEST] News failed: {e}")

    # 4. GitHub activity via Composio
    try:
        gh = await _get_github_activity()
        if gh:
            sections.append(f"GitHub: {gh}")
    except Exception:
        pass

    # 5. Date info
    today = date.today()
    sections.append(f"Today is {today.strftime('%A, %B %d, %Y')}.")

    raw = "\n\n".join(sections)
    prompt = f"""Write a friendly 3-sentence morning brief for {USER_NAME} from this data.
Be warm, concise, and personal. Greet them by name.

Data:
{raw}

Return ONLY the brief, 3-4 sentences max."""

    result = await llm_complete("chat", [{"role": "user", "content": prompt}])
    digest = result.strip()
    if "```" in digest:
        digest = digest.split("```")[1].split("```")[0].strip() if "```" in digest else digest

    logger.info("[DIGEST] Morning digest generated")
    return digest


async def _get_todays_reminders(user_id: str) -> list[str]:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    async with AsyncSessionLocal() as session:
        stmt = select(Reminder).where(
            Reminder.remind_at >= today_start,
            Reminder.remind_at <= today_end,
            Reminder.is_done == False,
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [f"{r.title}" + (f" - {r.description}" if r.description else "") for r in rows]


async def _search_news(query: str, max_results: int = 3) -> list:
    try:
        from tools.search_tool import search_engine
        results = await asyncio.wait_for(
            search_engine.search_async(query, max_results=max_results),
            timeout=5,
        )
        return results if isinstance(results, list) else []
    except Exception:
        try:
            from tools.search_tool import search_engine
            results = search_engine.search(query)
            return results[:max_results] if isinstance(results, list) else []
        except Exception:
            return []


async def _get_github_activity() -> str:
    try:
        from core.composio_tools import get_github_activity
        result = get_github_activity()
        if isinstance(result, str):
            return result
        return ""
    except Exception:
        return ""
