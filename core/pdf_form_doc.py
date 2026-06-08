import logging
import re

logger = logging.getLogger(__name__)


def find_source_upload_id(content: str) -> str | None:
    if not content:
        return None
    m = re.search(r'<!--\s*pdf_form_source\s+(\S+)\s*-->', content)
    if m:
        return m.group(1)
    return None
