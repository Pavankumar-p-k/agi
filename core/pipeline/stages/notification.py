"""NotificationStage — publishes build/chat completion events to notification system."""
from __future__ import annotations

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext


class NotificationStage(PipelineStage):
    """Publish completion/ failure notifications via EventBus."""

    @property
    def name(self) -> str:
        return "notification"

    async def execute(self, context: PipelineContext) -> StageResult:
        try:
            from core.event_bus import global_event_bus, Event
            from notifications.notifier import notifier

            # Determine event type based on execution state
            if context.execution_state == "completed":
                event_type = "build_completed"
                payload = {
                    "project": context.activity_id,
                    "goal": context.raw_input[:100],
                    "status": "success",
                }
            elif context.execution_state in ("failed", "error"):
                event_type = "build_failed"
                payload = {
                    "project": context.activity_id,
                    "goal": context.raw_input[:100],
                    "error": context.error or "Unknown error",
                }
            else:
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

            # Publish to EventBus
            await global_event_bus.publish(Event(
                type=event_type,
                source="pipeline.notification",
                payload=payload,
            ))

            # Also send via notifier (email, push, WebSocket)
            await notifier.notify(
                project=context.activity_id or "unknown",
                event=event_type,
                data=payload,
            )

        except Exception as e:
            # Notification failure should not fail the pipeline
            import logging
            logging.getLogger(__name__).warning("NotificationStage failed: %s", e)

        return StageResult(outcome=StageOutcome.CONTINUE, context=context)