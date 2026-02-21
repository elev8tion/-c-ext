"""Tests for token counting utilities."""

import pytest

from code_extract.ai.token_utils import (
    estimate_tokens,
    truncate_to_tokens,
    estimate_messages_tokens,
    has_tiktoken,
)


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_nonempty_string(self):
        result = estimate_tokens("Hello, world!")
        assert result > 0

    def test_long_string(self):
        text = "word " * 1000
        result = estimate_tokens(text)
        assert result > 100

    def test_returns_int(self):
        assert isinstance(estimate_tokens("test"), int)


class TestTruncateToTokens:
    def test_under_limit(self):
        text = "short text"
        assert truncate_to_tokens(text, 100) == text

    def test_over_limit(self):
        text = "word " * 1000  # many tokens
        result = truncate_to_tokens(text, 10)
        assert len(result) < len(text)

    def test_zero_limit(self):
        assert truncate_to_tokens("hello", 0) == ""

    def test_empty_input(self):
        assert truncate_to_tokens("", 100) == ""


class TestEstimateMessagesTokens:
    def test_empty_list(self):
        assert estimate_messages_tokens([]) == 0

    def test_single_message(self):
        msgs = [{"role": "user", "content": "Hello"}]
        result = estimate_messages_tokens(msgs)
        # At least 4 overhead + some content tokens
        assert result >= 5

    def test_multiple_messages(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        result = estimate_messages_tokens(msgs)
        assert result >= 10  # 4 overhead each + content

    def test_none_content(self):
        msgs = [{"role": "assistant", "content": None}]
        result = estimate_messages_tokens(msgs)
        assert result == 4  # just overhead


class TestHasTiktoken:
    def test_returns_bool(self):
        assert isinstance(has_tiktoken(), bool)


class TestFallbackBehavior:
    def test_fallback_estimate(self):
        """Even without tiktoken, estimate should return a reasonable number."""
        result = estimate_tokens("This is a test sentence with several words.")
        assert result > 0
        assert isinstance(result, int)
