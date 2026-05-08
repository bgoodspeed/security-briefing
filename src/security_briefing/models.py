from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

TranscriptSource = Literal["official", "youtube-auto-captions", "youtube-manual-captions"]


@dataclass
class EpisodeRef:
    podcast_slug: str
    episode_id: str
    title: str
    pub_date: datetime
    source_url: str

    def to_jsonable(self) -> dict[str, Any]:
        d = asdict(self)
        d["pub_date"] = self.pub_date.isoformat()
        return d


@dataclass
class Episode:
    podcast_slug: str
    episode_id: str
    title: str
    pub_date: datetime
    source_url: str
    audio_url: str | None
    description: str
    hosts: list[str]
    guests: list[str]
    transcript: str
    transcript_source: TranscriptSource
    extra: dict[str, Any] = field(default_factory=dict)

    def metadata_jsonable(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("transcript")
        d["pub_date"] = self.pub_date.isoformat()
        return d

    @classmethod
    def from_metadata(cls, data: dict[str, Any], transcript: str) -> Episode:
        d = dict(data)
        d["pub_date"] = datetime.fromisoformat(d["pub_date"])
        d["transcript"] = transcript
        return cls(**d)


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
