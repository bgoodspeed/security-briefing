from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from selectolax.parser import HTMLParser

from ..models import Episode, EpisodeRef
from .base import fuzzy_pick, http_client


RSS_URL = "https://feeds.megaphone.fm/darknetdiaries"
TRANSCRIPT_URL = "https://darknetdiaries.com/transcript/{n}/"
EPISODE_URL = "https://darknetdiaries.com/episode/{n}/"

# Title format: "159: Patreon" -> ep number = 159
_EPNUM_RE = re.compile(r"^\s*(\d{1,5})\s*[:\-]")


class DarknetDiariesFetcher:
    slug = "darknet-diaries"
    display_name = "Darknet Diaries"
    hosts = ["Jack Rhysider"]

    def _parse_feed(self) -> list[dict]:
        with http_client() as client:
            r = client.get(RSS_URL)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        return list(feed.entries)

    def _entry_to_ref(self, entry: dict) -> EpisodeRef | None:
        title = entry.get("title", "")
        m = _EPNUM_RE.match(title)
        if not m:
            return None
        ep_num = m.group(1)
        pub = entry.get("published") or entry.get("updated")
        try:
            pub_date = parsedate_to_datetime(pub) if pub else datetime.now(timezone.utc)
        except (TypeError, ValueError):
            pub_date = datetime.now(timezone.utc)
        return EpisodeRef(
            podcast_slug=self.slug,
            episode_id=ep_num,
            title=title,
            pub_date=pub_date,
            source_url=entry.get("link") or EPISODE_URL.format(n=ep_num),
        )

    def list_episodes(self, limit: int = 10) -> list[EpisodeRef]:
        refs: list[EpisodeRef] = []
        for entry in self._parse_feed():
            ref = self._entry_to_ref(entry)
            if ref is not None:
                refs.append(ref)
            if len(refs) >= limit:
                break
        return refs

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
            refs = self.list_episodes(limit=1)
            if not refs:
                raise LookupError("no episodes in Darknet Diaries feed")
            return refs[0]
        if episode_id:
            target = str(episode_id).lstrip("0") or "0"
            for entry in self._parse_feed():
                ref = self._entry_to_ref(entry)
                if ref and ref.episode_id == target:
                    return ref
            raise LookupError(f"Darknet Diaries episode {episode_id} not in feed")
        if query:
            return fuzzy_pick(query, self.list_episodes(limit=300))
        raise ValueError("must specify latest=True, episode_id, or query")

    def _fetch_transcript(self, ep_num: str) -> str:
        url = TRANSCRIPT_URL.format(n=ep_num)
        with http_client(timeout=60.0) as client:
            r = client.get(url)
            r.raise_for_status()
        return _extract_transcript(r.text)

    def fetch(self, ref: EpisodeRef) -> Episode:
        transcript = self._fetch_transcript(ref.episode_id)
        audio_url: str | None = None
        description = ""
        for entry in self._parse_feed():
            r = self._entry_to_ref(entry)
            if r and r.episode_id == ref.episode_id:
                description = entry.get("summary", "") or entry.get("description", "")
                for enc in entry.get("enclosures", []):
                    if "audio" in enc.get("type", ""):
                        audio_url = enc.get("href") or enc.get("url")
                        break
                break

        return Episode(
            podcast_slug=self.slug,
            episode_id=ref.episode_id,
            title=ref.title,
            pub_date=ref.pub_date,
            source_url=ref.source_url,
            audio_url=audio_url,
            description=description,
            hosts=list(self.hosts),
            guests=_guess_guests(description),
            transcript=transcript,
            transcript_source="official",
            extra={"transcript_url": TRANSCRIPT_URL.format(n=ref.episode_id)},
        )


def _extract_transcript(html: str) -> str:
    tree = HTMLParser(html)
    art = tree.css_first("article.single-post")
    if art is None:
        raise RuntimeError("could not find <article class='single-post'> on transcript page")
    for s in art.css("script, style, .player, .audio"):
        s.decompose()
    raw = art.text(separator="\n", strip=True)

    # Trim everything up to the start-of-recording marker if present.
    marker = raw.find("[START OF RECORDING]")
    if marker > 0:
        raw = raw[marker:]
    # Trim a leading "Episode Show Notes" header if it remains.
    raw = re.sub(r"^Episode Show Notes\s*", "", raw)

    # Collapse runs of blank lines.
    return re.sub(r"\n{3,}", "\n\n", raw).strip()


_GUEST_RE = re.compile(r"\bguest[s]?:?\s*([A-Z][\w'\-\.]+(?:\s+[A-Z][\w'\-\.]+){0,3})", re.IGNORECASE)


def _guess_guests(description: str) -> list[str]:
    """Cheap heuristic — most DD episodes name their guest in show notes.

    Returns an empty list when nothing recognizable is found rather than
    risking false positives. The summarizer can still extract guest info
    from the transcript itself.
    """
    if not description:
        return []
    matches = _GUEST_RE.findall(description)
    return [m.strip() for m in matches][:3]
