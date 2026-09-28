"""Final metrics computation for agent loop responses."""


def _estimate_tokens(text: str) -> int:
    return max(1, round(len(text or "") / 4))


def _compute_final_metrics(
    *,
    messages=None,
    full_response: str = "",
    total_duration: float = 0.0,
    time_to_first_token: float | None = 0.0,
    context_length: int = 0,
    real_input_tokens: int = 0,
    real_output_tokens: int = 0,
    has_real_usage: bool = False,
    tool_events=None,
    round_texts=None,
    model: str = "",
    last_round_input_tokens: int = 0,
    prep_timings: dict | None = None,
    **kwargs,
) -> dict:
    """Compute the final metrics block for a completed chat response."""
    if has_real_usage:
        input_tokens = real_input_tokens
        output_tokens = real_output_tokens
        usage_source = "real"
    else:
        # Estimation mirrors the legacy counter: ~4 chars/token per message.
        input_tokens = max(1, sum(
            _estimate_tokens(str(m.get("content", "")))
            for m in (messages or []) if isinstance(m, dict)
        ))
        output_tokens = _estimate_tokens(full_response)
        usage_source = "estimated"

    tps = round(output_tokens / total_duration, 2) if total_duration > 0 else 0

    effective_input = last_round_input_tokens or input_tokens
    context_pct = (
        round(min(effective_input / context_length * 100, 100.0), 1)
        if context_length > 0 else 0
    )

    metrics: dict = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "usage_source": usage_source,
        "tokens_per_second": tps,
        "response_time": round(total_duration, 2),
        "time_to_first_token": round(time_to_first_token, 2) if time_to_first_token else 0,
        "context_percent": context_pct,
        "context_length": context_length,
        "model": model,
    }

    if prep_timings:
        metrics["agent_prep_time"] = round(sum(prep_timings.values()), 2)
        # Model wait = first-token wait minus all local prep (1.25 - 0.65 = 0.6).
        metrics["agent_model_wait_time"] = round(
            max(0.0, (time_to_first_token or 0.0) - metrics["agent_prep_time"]), 2)
        metrics["agent_prep_breakdown"] = dict(prep_timings)

    if tool_events:
        metrics["tool_events"] = list(tool_events)
    if round_texts:
        metrics["round_texts"] = list(round_texts)

    return metrics


__all__ = ["_compute_final_metrics"]
