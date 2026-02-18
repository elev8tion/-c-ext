"""DeepSeek AI integration for context-aware code analysis chat."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class AIModel(Enum):
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_CODER = "deepseek-coder"
    DEEPSEEK_REASONER = "deepseek-reasoner"


@dataclass
class AIConfig:
    api_key: str = ""
    model: AIModel = AIModel.DEEPSEEK_CODER
    temperature: float = 0.1
    max_tokens: int = 4000
    base_url: str = "https://api.deepseek.com/v1"

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
