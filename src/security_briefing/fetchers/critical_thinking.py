from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from selectolax.parser import HTMLParser

from ..models import Episode, EpisodeRef
from .base import fuzzy_pick, http_client


RSS_URL = "https://media.rss.com/ctbbpodcast/feed.xml"  # 301 → cohostpodcasting
EPISODES_INDEX = "https://www.criticalthinkingpodcast.io/episodes/"
SITE_BASE = "https://www.criticalthinkingpodcast.io"

# Title format: "Episode 173: Bug Bounty is Dead and AI Killed it."
_EPNUM_RE = re.compile(r"Episode\s+(\d{1,5})[:\s\-]", re.IGNORECASE)


class CriticalThinkingFetcher:
    slug = "critical-thinking"
    display_name = "Critical Thinking — Bug Bounty Podcast"
    hosts = ["Justin Gardner", "Joseph Thacker", "Brandyn Murtagh"]

    def __init__(self) -> None:
        self._url_index: dict[str, str] | None = None  # ep_num -> full URL

    def _parse_feed(self) -> list[dict]:
        with http_client() as client:
            r = client.get(RSS_URL)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        return list(feed.entries)

    def _entry_to_ref(self, entry: dict) -> EpisodeRef | None:
        title = entry.get("title", "")
        m = _EPNUM_RE.search(title)
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
            source_url=self._episode_url(ep_num, title),
        )

    # --- URL discovery -----------------------------------------------------

    def _build_url_index(self) -> dict[str, str]:
        if self._url_index is not None:
            return self._url_index
        with http_client() as client:
            r = client.get(EPISODES_INDEX)
            r.raise_for_status()
        tree = HTMLParser(r.text)
        index: dict[str, str] = {}
        for a in tree.css("a[href]"):
            href = a.attributes.get("href") or ""
            m = re.match(r"^/?(episode-(\d{1,5})-[a-z0-9\-]+)/?$", href)
            if m:
                ep_num = m.group(2)
                full = href if href.startswith("http") else f"{SITE_BASE}/{m.group(1)}/"
                index.setdefault(ep_num, full)
        self._url_index = index
        return index

    def _episode_url(self, ep_num: str, title: str) -> str:
        # Try the index first (ground truth); fall back to deterministic slug.
        try:
            idx = self._build_url_index()
            if ep_num in idx:
                return idx[ep_num]
        except Exception:
            pass
        slug = _slugify_title_after_episode(title)
        return f"{SITE_BASE}/episode-{ep_num}-{slug}/"

    # --- public API --------------------------------------------------------

    def list_episodes(self, limit: int = 10) -> list[EpisodeRef]:
        refs: list[EpisodeRef] = []
        for entry in self._parse_feed():
            ref = self._entry_to_ref(entry)
            if ref is not None:
                refs.append(ref)
            if len(refs) >= limit:
                break
        return refs

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
                raise LookupError("no Critical Thinking episodes in feed")
            return refs[0]
        if episode_id:
            target = str(episode_id).lstrip("0") or "0"
            for entry in self._parse_feed():
                ref = self._entry_to_ref(entry)
                if ref and ref.episode_id == target:
                    return ref
            raise LookupError(f"Critical Thinking episode {episode_id} not in feed")
        if query:
            return fuzzy_pick(query, self.list_episodes(limit=300))
        raise ValueError("must specify latest=True, episode_id, or query")

    def fetch(self, ref: EpisodeRef) -> Episode:
        with http_client(timeout=60.0) as client:
            r = client.get(ref.source_url)
            r.raise_for_status()
        transcript = _extract_transcript(r.text)

        description = ""
        audio_url: str | None = None
        for entry in self._parse_feed():
            r2 = self._entry_to_ref(entry)
            if r2 and r2.episode_id == ref.episode_id:
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
            guests=[],
            transcript=transcript,
            transcript_source="official",
        )


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LEAD_EP_RE = re.compile(r"^\s*episode\s+\d+\s*[:\-]?\s*", re.IGNORECASE)


def _slugify_title_after_episode(title: str) -> str:
    rest = _LEAD_EP_RE.sub("", title)
    return _NON_ALNUM_RE.sub("-", rest.lower()).strip("-")


def _extract_transcript(html: str) -> str:
    tree = HTMLParser(html)
    node = tree.css_first("#transcript")
    if node is None:
        raise RuntimeError("could not find #transcript on episode page")
    for s in node.css("script, style"):
        s.decompose()
    raw = node.text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", raw).strip()
