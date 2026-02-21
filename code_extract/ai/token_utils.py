"""Token counting utilities with optional tiktoken (fallback to heuristic)."""

from __future__ import annotations

_encoder = None
_tiktoken_available: bool | None = None


def has_tiktoken() -> bool:
    """Check if accurate token counting via tiktoken is available."""
    global _tiktoken_available
    if _tiktoken_available is None:
        try:
            import tiktoken  # noqa: F401
            _tiktoken_available = True
        except ImportError:
            _tiktoken_available = False
    return _tiktoken_available


def _get_encoder():
    """Lazy-load the cl100k_base encoder on first call."""
    global _encoder
    if _encoder is None and has_tiktoken():
        import tiktoken
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def estimate_tokens(text: str) -> int:
    """Count tokens for a string.

    Uses tiktoken cl100k_base if available, otherwise falls back to
    ``len(text) / 3.5`` heuristic.
    """
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text))
    return max(1, int(len(text) / 3.5))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text at a token boundary.

    Returns the original text if it fits within *max_tokens*.
    """
    if max_tokens <= 0:
        return ""
    if not text:
        return text
    enc = _get_encoder()
    if enc is not None:
        tokens = enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return enc.decode(tokens[:max_tokens])
    # Heuristic fallback: ~3.5 chars per token
    char_limit = int(max_tokens * 3.5)
    if len(text) <= char_limit:
        return text
    return text[:char_limit]


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Count tokens for an OpenAI-compatible message list.

    Adds ~4 tokens per message for role/separator overhead.
    """
    total = 0
    for msg in messages:
        total += 4  # role + separators overhead
        content = msg.get("content") or ""
        if isinstance(content, str):
            total += estimate_tokens(content)
    return total
