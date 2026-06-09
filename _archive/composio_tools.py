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

"""composio tools — wrapped as smolagens @tool functions.
Each gracefully says "not connected" if COMPOSIO_API_KEY is missing
or if no OAuth connection exists for the service.
"""
import logging
import os
import json
from typing import Optional

from smolagents import tool

logger = logging.getLogger(__name__)

COMPOSIO_ENABLED = bool(os.environ.get("COMPOSIO_API_KEY"))


def _get_composio():
    if not COMPOSIO_ENABLED:
        return None
    try:
        from composio import Composio
        return Composio()
    except Exception as e:
        logger.exception("[composio] init: %s", e)
        return None


def _check_connected(c, app_slug: str) -> Optional[str]:
    """Check if a connected account exists for the given app slug.
    Returns the connected_account_id if found, None otherwise.
    """
    try:
        accounts = c.connected_accounts.list()
        for acct in getattr(accounts, "items", []):
            slug = getattr(getattr(acct, "toolkit", None), "slug", None)
            if slug == app_slug and getattr(acct, "status", "") == "ACTIVE":
                return getattr(acct, "id", None)
        return None
    except Exception as e:
        logger.exception("[composio] check connected: %s", e)
        return None


def _not_connected_msg(app_name: str) -> str:
    return (
        f"{app_name} is not connected. "
        f"Run: composio add {app_name.lower()}  (opens browser for OAuth). "
        f"Then set COMPOSIO_API_KEY in .env"
    )


@tool
def gmail_send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = "",
) -> str:
    """Sends an email via Gmail using the authenticated Composio connection.
    Args:
        to: Recipient email address
        subject: Email subject line
        body: Email body content (plain text)
        cc: Optional CC recipient(s), comma-separated
    """
    c = _get_composio()
    if c is None:
        return _not_connected_msg("Gmail")
    conn_id = _check_connected(c, "gmail")
    if conn_id is None:
        return _not_connected_msg("Gmail")
    try:
        args = {
            "recipient_email": to,
            "subject": subject,
            "body": body,
        }
        if cc:
            args["cc"] = [e.strip() for e in cc.split(",") if e.strip()]
        result = c.tools.execute(
            slug="GMAIL_SEND_EMAIL",
            arguments=args,
            connected_account_id=conn_id,
            user_id="pavan@jarvis",
            dangerously_skip_version_check=True,
        )
        data = getattr(result, "data", {}) or {}
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        return f"Email sent to {to}: {data.get('id', 'OK')}"
    except Exception as e:
        return f"Failed to send email: {e}"


@tool
def github_create_issue(
    owner: str,
    repo: str,
    title: str,
    body: Optional[str] = "",
) -> str:
    """Creates a GitHub issue in the specified repository using Composio.
    Args:
        owner: GitHub username or organization that owns the repo
        repo: Repository name (without .git)
        title: Issue title
        body: Issue description / body text
    """
    c = _get_composio()
    if c is None:
        return _not_connected_msg("GitHub")
    conn_id = _check_connected(c, "github")
    if conn_id is None:
        return _not_connected_msg("GitHub")
    try:
        args = {
            "owner": owner,
            "repo": repo,
            "title": title,
        }
        if body:
            args["body"] = body
        result = c.tools.execute(
            slug="GITHUB_CREATE_AN_ISSUE",
            arguments=args,
            connected_account_id=conn_id,
            user_id="pavan@jarvis",
            dangerously_skip_version_check=True,
        )
        data = getattr(result, "data", {}) or {}
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        return f"Issue created: {data.get('html_url', data.get('id', 'OK'))}"
    except Exception as e:
        return f"Failed to create GitHub issue: {e}"


@tool
def slack_send_message(
    channel: str,
    message: str,
) -> str:
    """Sends a message to a Slack channel using Composio.
    Args:
        channel: Channel name or ID (e.g., 'general' or 'C123456')
        message: Message text to send
    """
    c = _get_composio()
    if c is None:
        return _not_connected_msg("Slack")
    conn_id = _check_connected(c, "slack")
    if conn_id is None:
        return _not_connected_msg("Slack")
    try:
        args = {
            "channel": channel,
            "markdown_text": message,
        }
        result = c.tools.execute(
            slug="SLACK_SEND_MESSAGE",
            arguments=args,
            connected_account_id=conn_id,
            user_id="pavan@jarvis",
            dangerously_skip_version_check=True,
        )
        data = getattr(result, "data", {}) or {}
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        return f"Message sent to #{channel}: ts={data.get('ts', 'OK')}"
    except Exception as e:
        return f"Failed to send Slack message: {e}"


COMPOSIO_TOOLS = [gmail_send_email, github_create_issue, slack_send_message]
