"""Email attachment helpers shared by the MCP email server and tool dispatch."""
from __future__ import annotations

import logging
import mimetypes
import os
from email.message import EmailMessage
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def attach_files_to_msg(msg: EmailMessage,
                        attachments: Iterable[str] | None) -> EmailMessage:
    """Attach readable files to *msg*; nonexistent/unreadable ones are skipped."""
    for path in attachments or []:
        try:
            if not path or not os.path.isfile(str(path)):
                continue
            ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            maintype, _, subtype = ctype.partition("/")
            if not subtype:
                maintype, subtype = "application", "octet-stream"
            with open(path, "rb") as handle:
                payload = handle.read()
            msg.add_attachment(
                payload,
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(str(path)),
            )
        except Exception as exc:  # noqa: BLE001 — one bad file must not block mail
            logger.debug("[email_utils] skipping attachment %s: %s", path, exc)
    return msg
