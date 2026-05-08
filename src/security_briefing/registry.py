from __future__ import annotations

from .fetchers.base import Fetcher
from .fetchers.darknet_diaries import DarknetDiariesFetcher
from .fetchers.security_now import SecurityNowFetcher
# Risky Business and Critical Thinking imported lazily — they need
# yt-dlp / network setup that takes longer.


_ALIASES: dict[str, str] = {
    "sn": "security-now",
    "dd": "darknet-diaries",
    "rb": "risky-business",
    "ct": "critical-thinking",
    "security_now": "security-now",
    "darknet_diaries": "darknet-diaries",
    "risky_business": "risky-business",
    "critical_thinking": "critical-thinking",
}


def _build_registry() -> dict[str, Fetcher]:
    reg: dict[str, Fetcher] = {
        SecurityNowFetcher.slug: SecurityNowFetcher(),
        DarknetDiariesFetcher.slug: DarknetDiariesFetcher(),
    }
    # Lazy-imported fetchers
    try:
        from .fetchers.critical_thinking import CriticalThinkingFetcher
        reg[CriticalThinkingFetcher.slug] = CriticalThinkingFetcher()
    except ImportError:
        pass
    try:
        from .fetchers.risky_business import RiskyBusinessFetcher
        reg[RiskyBusinessFetcher.slug] = RiskyBusinessFetcher()
    except ImportError:
        pass
    return reg


_REGISTRY: dict[str, Fetcher] | None = None


def all_slugs() -> list[str]:
    return sorted(_registry().keys())


def get_fetcher(slug_or_alias: str) -> Fetcher:
    reg = _registry()
    key = slug_or_alias.lower().strip()
    key = _ALIASES.get(key, key)
    if key not in reg:
        raise KeyError(
            f"unknown podcast {slug_or_alias!r}. Known: {', '.join(sorted(reg))}"
        )
    return reg[key]


def _registry() -> dict[str, Fetcher]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY
