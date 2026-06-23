"""Email utility functions shared between MCP server and tool layer."""

import logging
import mimetypes
import os
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def attach_files_to_msg(msg: EmailMessage, attachments: list) -> None:
    """Attach files to an EmailMessage.

    Each attachment is either:
    - a file path string (read the file, guess MIME type from extension)
    - a dict with keys: path, filename, data (binary), mime_type
    """
    for att in attachments:
        if isinstance(att, str):
            path = att
            filename = os.path.basename(path)
            data = None
            mime_type = None
        elif isinstance(att, dict):
            path = att.get("path", "")
            filename = att.get("filename", os.path.basename(path) if path else "attachment")
            data = att.get("data")
            mime_type = att.get("mime_type")
        else:
            continue
        if data is None and path:
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except Exception as exc:
                logger.warning("[email_utils] Cannot read attachment %s: %s", path, exc)
                continue
        if data is None:
            continue
        if not mime_type:
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"
        main_type, sub_type = mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream")
        msg.add_attachment(data, maintype=main_type, subtype=sub_type, filename=filename)
