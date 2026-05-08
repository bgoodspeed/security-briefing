from __future__ import annotations

import os

from openai import OpenAI

from ..models import Episode
from .prompt import render


DO_BASE_URL = "https://inference.do-ai.run/v1/"


class DigitalOceanSummarizer:
    """OpenAI-compatible client pointed at DigitalOcean Serverless Inference.

    DigitalOcean's GenAI / Serverless Inference service exposes an
    OpenAI-compatible Chat Completions API at https://inference.do-ai.run/v1/.
    Auth is a Bearer token from a model access key (DIGITAL_OCEAN_MODEL_ACCESS_KEY).
    """

    name = "do"

    def __init__(self, model: str):
        api_key = os.environ.get("DIGITAL_OCEAN_MODEL_ACCESS_KEY")
        if not api_key:
            raise RuntimeError(
                "DIGITAL_OCEAN_MODEL_ACCESS_KEY is not set. Add it to your .env or shell."
            )
        self.model = model
        self.client = OpenAI(base_url=DO_BASE_URL, api_key=api_key)

    def summarize(self, episode: Episode) -> str:
        system, user = render(episode)
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
        return text.strip() + "\n"
