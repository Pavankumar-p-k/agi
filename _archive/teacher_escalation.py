import logging

logger = logging.getLogger(__name__)


async def run_teacher_inline(
    student_endpoint_url=None,
    student_messages=None,
    student_tool_events=None,
    student_reply="",
    owner=None,
):
    if False:
        yield
