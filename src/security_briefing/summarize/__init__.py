from __future__ import annotations

import os
from pathlib import Path

from .. import storage
from ..models import Episode

DEFAULT_BACKEND = "anthropic"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
DEFAULT_DO_MODEL = "llama3.3-70b-instruct"


def _resolve_backend(name: str | None):
    name = (name or os.environ.get("BRIEFING_BACKEND") or DEFAULT_BACKEND).lower()
    if name in ("anthropic", "claude"):
        from .anthropic_backend import AnthropicSummarizer
        return AnthropicSummarizer, "anthropic", DEFAULT_ANTHROPIC_MODEL
    if name in ("do", "digitalocean", "digital-ocean"):
        from .digitalocean_backend import DigitalOceanSummarizer
        return DigitalOceanSummarizer, "do", DEFAULT_DO_MODEL
    raise ValueError(f"unknown backend {name!r}; expected 'anthropic' or 'do'")


def _resolve_model(backend_name: str, model: str | None) -> str:
    if model:
        return model
    if backend_name == "anthropic":
        return os.environ.get("BRIEFING_ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
    return os.environ.get("BRIEFING_DO_MODEL") or DEFAULT_DO_MODEL


def run(
    episode: Episode,
    *,
    backend: str | None = None,
    model: str | None = None,
    force: bool = False,
) -> tuple[Path, str]:
    cls, backend_name, _ = _resolve_backend(backend)
    chosen_model = _resolve_model(backend_name, model)

    cache_path = storage.summary_path(
        episode.podcast_slug, episode.episode_id, backend_name, chosen_model
    )
    if cache_path.exists() and not force:
        return cache_path, cache_path.read_text(encoding="utf-8")

    summarizer = cls(model=chosen_model)
    text = summarizer.summarize(episode)
    saved = storage.save_summary(
        episode.podcast_slug, episode.episode_id, backend_name, chosen_model, text
    )
    return saved, text
