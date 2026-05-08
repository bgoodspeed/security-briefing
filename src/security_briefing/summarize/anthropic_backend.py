from __future__ import annotations

import os

import anthropic

from ..models import Episode
from .prompt import render


class AnthropicSummarizer:
    name = "anthropic"

    def __init__(self, model: str):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env or shell."
            )
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key)

    def summarize(self, episode: Episode) -> str:
        system, user = render(episode)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Concatenate any text blocks the model returned.
        parts: list[str] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "\n".join(parts).strip() + "\n"
