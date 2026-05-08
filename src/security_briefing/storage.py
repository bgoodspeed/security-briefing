from __future__ import annotations

import os
import re
from pathlib import Path

from .models import Episode, EpisodeRef, dump_json, load_json


def project_root() -> Path:
    env = os.environ.get("BRIEFING_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd() / "episodes"


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def safe_id(text: str) -> str:
    """Make a filesystem-safe id from arbitrary text."""
    return _SLUG_RE.sub("-", text.lower()).strip("-")


def episode_dir(podcast_slug: str, episode_id: str) -> Path:
    return project_root() / podcast_slug / safe_id(episode_id)


def save_episode(episode: Episode) -> Path:
    d = episode_dir(episode.podcast_slug, episode.episode_id)
    d.mkdir(parents=True, exist_ok=True)
    dump_json(d / "metadata.json", episode.metadata_jsonable())
    (d / "transcript.txt").write_text(episode.transcript, encoding="utf-8")
    return d


def load_episode(podcast_slug: str, episode_id: str) -> Episode:
    d = episode_dir(podcast_slug, episode_id)
    metadata = load_json(d / "metadata.json")
    transcript = (d / "transcript.txt").read_text(encoding="utf-8")
    return Episode.from_metadata(metadata, transcript)


def episode_exists(podcast_slug: str, episode_id: str) -> bool:
    d = episode_dir(podcast_slug, episode_id)
    return (d / "metadata.json").exists() and (d / "transcript.txt").exists()


def summary_path(podcast_slug: str, episode_id: str, backend: str, model: str) -> Path:
    d = episode_dir(podcast_slug, episode_id)
    safe_model = safe_id(model)
    return d / f"summary-{backend}-{safe_model}.md"


def save_summary(
    podcast_slug: str,
    episode_id: str,
    backend: str,
    model: str,
    text: str,
) -> Path:
    path = summary_path(podcast_slug, episode_id, backend, model)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
