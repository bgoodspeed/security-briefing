from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ..models import Episode, EpisodeRef
from .base import fuzzy_pick, http_client


RSS_URL = "https://feeds.twit.tv/sn.xml"
TRANSCRIPT_URL = "https://www.grc.com/sn/sn-{n}.txt"

# Match leading episode number: "SN 1076: ..." or "Security Now 1076: ..." etc.
_EPNUM_RE = re.compile(r"\b(?:SN|Security Now)\s*[#]?\s*(\d{1,5})\b", re.IGNORECASE)


class SecurityNowFetcher:
    slug = "security-now"
    display_name = "Security Now"
    hosts = ["Steve Gibson", "Leo Laporte"]

    def _parse_feed(self, limit: int | None = None) -> list[dict]:
        with http_client() as client:
            r = client.get(RSS_URL)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        entries = list(feed.entries)
        if limit is not None:
            entries = entries[:limit]
        return entries

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
            source_url=entry.get("link", ""),
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
                raise LookupError("no episodes found in Security Now feed")
            return refs[0]
        if episode_id:
            # Walk all entries (feed is bounded) for an exact match
            for entry in self._parse_feed():
                ref = self._entry_to_ref(entry)
                if ref and ref.episode_id == str(episode_id).lstrip("0"):
                    return ref
                if ref and ref.episode_id == str(episode_id):
                    return ref
            raise LookupError(f"Security Now episode {episode_id} not in current feed")
        if query:
            return fuzzy_pick(query, self.list_episodes(limit=200))
        raise ValueError("must specify latest=True, episode_id, or query")

    def _fetch_transcript(self, ep_num: str) -> str:
        url = TRANSCRIPT_URL.format(n=ep_num)
        with http_client(timeout=60.0) as client:
            r = client.get(url)
            r.raise_for_status()
            text = r.text
        return _clean_grc_transcript(text)

    def fetch(self, ref: EpisodeRef) -> Episode:
        transcript = self._fetch_transcript(ref.episode_id)
        # Pull audio enclosure + description from the same feed entry by
        # walking the feed once. Cheap relative to the transcript fetch.
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
            guests=[],
            transcript=transcript,
            transcript_source="official",
            extra={"transcript_url": TRANSCRIPT_URL.format(n=ref.episode_id)},
        )


_DESCRIPTION_RE = re.compile(r"^DESCRIPTION:\s*", re.MULTILINE)


def _clean_grc_transcript(text: str) -> str:
    """Drop GRC's URL/format header rows but keep DESCRIPTION onward.

    The .txt files start with `GIBSON RESEARCH ... / SERIES / EPISODE /
    DATE / TITLE / HOSTS / SOURCE / ARCHIVE` boilerplate that is noise
    for an LLM. Everything from `DESCRIPTION:` down — episode synopsis
    plus the full speaker-tagged dialogue — is useful.
    """
    m = _DESCRIPTION_RE.search(text)
    if m:
        return text[m.start():].lstrip()
    return text
