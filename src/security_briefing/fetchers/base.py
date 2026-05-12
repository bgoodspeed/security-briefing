from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx
from rapidfuzz import process, fuzz

from ..models import Episode, EpisodeRef


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)


def http_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def fuzzy_pick(query: str, refs: list[EpisodeRef], threshold: int = 60) -> EpisodeRef:
    """Return the best matching EpisodeRef by title.

    Raises LookupError if no match clears `threshold`.
    """
    if not refs:
        raise LookupError("no episodes to search")
    titles = [r.title for r in refs]
    match = process.extractOne(query, titles, scorer=fuzz.WRatio)
    if match is None:
        raise LookupError(f"no fuzzy match for {query!r}")
    _, score, idx = match
    if score < threshold:
        raise LookupError(
            f"no episode matched {query!r} above threshold {threshold} "
            f"(best: {refs[idx].title!r}, score={score})"
        )
    return refs[idx]


@runtime_checkable
class Fetcher(Protocol):
    slug: str
    display_name: str
    hosts: list[str]

    def list_episodes(self, limit: int = 10) -> list[EpisodeRef]: ...

    def find_episode(
        self,
        *,
        latest: bool = False,
        episode_id: str | None = None,
        query: str | None = None,
    ) -> EpisodeRef: ...

    def fetch(self, ref: EpisodeRef) -> Episode: ...

    def iter_all_refs(self) -> list[EpisodeRef]:
        """Return refs for every episode known to this fetcher.

        Default implementation just asks list_episodes for a large page;
        override when the upstream feed truncates (e.g., Security Now's
        RSS only carries ~10 entries).
        """
        ...
