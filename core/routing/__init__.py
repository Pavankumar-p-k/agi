"""core.routing — canonical intent-routing package (ADR: single classifier)."""
from core.routing.request_classifier import RequestMode, ClassifiedRequest, classify_request

__all__ = ["RequestMode", "ClassifiedRequest", "classify_request"]
