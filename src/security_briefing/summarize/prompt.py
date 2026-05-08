from __future__ import annotations

from ..models import Episode


SYSTEM = (
    "You summarize security podcast episodes for an offensive-security "
    "practitioner who does not have time to listen. Be terse, technical, "
    "and concrete. Only mention tools/techniques/insights that are "
    "explicitly discussed in the transcript — do NOT invent or extrapolate."
)


USER_TEMPLATE = """Summarize this podcast episode.

Podcast: {podcast}
Episode: {title}
Episode ID: {episode_id}
Hosts: {hosts}
Guests: {guests}
Date: {pub_date}
Source: {source_url}

Transcript:
<<<TRANSCRIPT
{transcript}
TRANSCRIPT>>>

Produce markdown in EXACTLY this structure. If a section has nothing to
report, write "_None discussed._" — never skip a heading.

## Topic
2–3 sentences on what the episode is about.

## New tools mentioned
- `<tool name>` — what it is. Include URL/repo only if mentioned in the transcript.

## Key security insights
- 1–2 sentences each. Vulnerabilities, exploits, defensive techniques, attacker behaviors.
  Cite the speaker (e.g. "Gibson:") when attribution matters.

## Workflows / techniques
- Concrete step-by-step methodologies that led to a finding or were used as a process.
  Each bullet should be specific enough that a reader could attempt it.
"""


def render(episode: Episode) -> tuple[str, str]:
    """Return (system, user) prompts for the given episode."""
    user = USER_TEMPLATE.format(
        podcast=episode.podcast_slug,
        title=episode.title,
        episode_id=episode.episode_id,
        hosts=", ".join(episode.hosts) or "—",
        guests=", ".join(episode.guests) or "—",
        pub_date=episode.pub_date.date().isoformat(),
        source_url=episode.source_url,
        transcript=episode.transcript,
    )
    return SYSTEM, user
