DEFAULT_HARD_MAX = 24000


class TokenBudget:
    """Tiered token budget with guaranteed reservations.

    Tiers (in eviction order — lowest priority first):
        system_prompt: always kept, ~XXX tokens
        pinned:    messages explicitly marked as _protected
        recent:    last N user/assistant pairs (guaranteed)
        tool_history: tool-call/tool-result pairs from earlier rounds
        summarized: conversation chunks already compressed into a summary
    """
    __slots__ = ("total", "protected", "recent_pairs")

    def __init__(self, total: int, protected: int = 0, recent_pairs: int = 2):
        self.total = total
        self.protected = protected
        self.recent_pairs = recent_pairs

    @property
    def available(self) -> int:
        return max(0, self.total - self.protected)

    @property
    def recent_budget(self) -> int:
        """Budget reserved for recent conversation pairs."""
        return max(0, int(self.available * 0.4))

    @property
    def history_budget(self) -> int:
        """Budget for older messages after reserving for recent."""
        return max(0, self.available - self.recent_budget)


def compute_input_token_budget(
    soft_budget: int,
    context_length: int,
    is_overridden: bool = False,
    hard_max: int = DEFAULT_HARD_MAX,
) -> TokenBudget:
    if is_overridden:
        total = min(soft_budget, context_length)
    else:
        window_budget = int(context_length * 0.75)
        capped = min(soft_budget, hard_max)
        total = min(window_budget, capped)

    # Reserve for system prompt + pinned messages (~2000 tokens baseline)
    protected = min(2000, total // 3)
    return TokenBudget(total=total, protected=protected, recent_pairs=2)
