from __future__ import annotations

import re
from datetime import datetime, timezone

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from ..models import Episode, EpisodeRef
from .base import fuzzy_pick


CHANNEL_URL = "https://www.youtube.com/@riskybizmedia/videos"
WATCH_URL = "https://www.youtube.com/watch?v={vid}"

# Title formats we know about:
#   "Risky Business (836): You can't patch the bugpocalypse"
#   "Risky Business #836: ..."  (older format)
_MAIN_EPNUM_RE = re.compile(
    r"\bRisky Business\b[^\d#(]{0,5}[#(]?\s*(\d{2,5})\s*[):\-]",
    re.IGNORECASE,
)


class RiskyBusinessFetcher:
    slug = "risky-business"
    display_name = "Risky Business"
    hosts = ["Patrick Gray", "Adam Boileau"]

    def _list_videos(self, limit: int) -> list[dict]:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": max(limit, 50),
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(CHANNEL_URL, download=False)
        return list(info.get("entries", []) or [])

    def _video_to_ref(self, v: dict) -> EpisodeRef:
        title = v.get("title") or ""
        vid = v.get("id") or ""
        m = _MAIN_EPNUM_RE.search(title)
        episode_id = m.group(1) if m else vid
        ts = v.get("timestamp")
        if ts:
            pub_date = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            pub_date = datetime.now(timezone.utc)
        return EpisodeRef(
            podcast_slug=self.slug,
            episode_id=episode_id,
            title=title,
            pub_date=pub_date,
            source_url=WATCH_URL.format(vid=vid),
        )

    def list_episodes(self, limit: int = 10) -> list[EpisodeRef]:
        videos = self._list_videos(limit)
        return [self._video_to_ref(v) for v in videos[:limit]]

    def iter_all_refs(self) -> list[EpisodeRef]:
        return self.list_episodes(limit=10_000)

    def find_episode(
        self,
        *,
        latest: bool = False,
        episode_id: str | None = None,
        query: str | None = None,
    ) -> EpisodeRef:
        if latest:
            # Prefer the most recent MAIN episode (matches the (NNN) format).
            for v in self._list_videos(limit=20):
                ref = self._video_to_ref(v)
                if _MAIN_EPNUM_RE.search(ref.title):
                    return ref
            # Fall back to the newest video of any kind.
            videos = self._list_videos(limit=1)
            if not videos:
                raise LookupError("no Risky Business videos found")
            return self._video_to_ref(videos[0])
        if episode_id:
            target = str(episode_id).strip()
            for v in self._list_videos(limit=300):
                ref = self._video_to_ref(v)
                if ref.episode_id == target:
                    return ref
            raise LookupError(f"Risky Business episode {episode_id} not found in last 300 videos")
        if query:
            return fuzzy_pick(query, self.list_episodes(limit=300))
        raise ValueError("must specify latest=True, episode_id, or query")

    def fetch(self, ref: EpisodeRef) -> Episode:
        # Extract video id from source_url
        vid = ref.source_url.rsplit("=", 1)[-1]
        transcript_text, source_kind = _fetch_youtube_transcript(vid)

        return Episode(
            podcast_slug=self.slug,
            episode_id=ref.episode_id,
            title=ref.title,
            pub_date=ref.pub_date,
            source_url=ref.source_url,
            audio_url=None,
            description="",
            hosts=list(self.hosts),
            guests=[],
            transcript=transcript_text,
            transcript_source=source_kind,
            extra={"youtube_video_id": vid},
        )


def _fetch_youtube_transcript(video_id: str) -> tuple[str, str]:
    """Return (text, source) where source identifies whether the captions
    were manually authored or auto-generated."""
    try:
        api = YouTubeTranscriptApi()
        listing = api.list(video_id)
    except (TranscriptsDisabled, VideoUnavailable) as e:
        raise RuntimeError(f"YouTube transcript unavailable for {video_id}: {e}") from e

    chosen = None
    source_kind = "youtube-manual-captions"
    # Prefer manually-created English captions, else auto-generated English.
    try:
        chosen = listing.find_manually_created_transcript(["en", "en-US", "en-GB"])
    except NoTranscriptFound:
        try:
            chosen = listing.find_generated_transcript(["en", "en-US", "en-GB"])
            source_kind = "youtube-auto-captions"
        except NoTranscriptFound as e:
            raise RuntimeError(
                f"no English transcript (manual or auto) available for {video_id}"
            ) from e

    snippets = chosen.fetch()
    lines = [getattr(s, "text", "").strip() for s in snippets]
    text = "\n".join(line for line in lines if line)
    return text, source_kind
