from __future__ import annotations

import sys
from typing import Optional

import typer
from dotenv import load_dotenv

from . import storage
from .registry import all_slugs, get_fetcher

load_dotenv()

app = typer.Typer(
    add_completion=False,
    help="Pull transcripts of security podcasts and summarize them with an LLM.",
    no_args_is_help=True,
)


def _resolve_ref(podcast: str, latest: bool, episode: str | None, search: str | None):
    f = get_fetcher(podcast)
    selectors = [bool(latest), bool(episode), bool(search)]
    if sum(selectors) != 1:
        typer.echo(
            "must pass exactly one of --latest / --episode N / --search 'term'",
            err=True,
        )
        raise typer.Exit(2)
    try:
        return f, f.find_episode(latest=latest, episode_id=episode, query=search)
    except LookupError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command("list")
def list_cmd(
    podcast: str = typer.Argument(..., help=f"Podcast slug. One of: {', '.join(all_slugs())}"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max episodes to list."),
):
    """List recent episodes for a podcast."""
    f = get_fetcher(podcast)
    refs = f.list_episodes(limit=limit)
    if not refs:
        typer.echo(f"no episodes found for {f.display_name}", err=True)
        raise typer.Exit(1)
    for r in refs:
        typer.echo(f"{r.episode_id:>5}  {r.pub_date.date()}  {r.title}")


@app.command("fetch")
def fetch_cmd(
    podcast: str = typer.Argument(..., help=f"Podcast slug. One of: {', '.join(all_slugs())}"),
    latest: bool = typer.Option(False, "--latest", help="Fetch the most recent episode."),
    episode: Optional[str] = typer.Option(None, "--episode", "-e", help="Fetch by episode number/id."),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Fuzzy search by title."),
    force: bool = typer.Option(False, "--force", help="Re-fetch even if already on disk."),
):
    """Fetch a transcript and metadata, save to ./episodes/<slug>/<id>/."""
    f, ref = _resolve_ref(podcast, latest, episode, search)

    if not force and storage.episode_exists(ref.podcast_slug, ref.episode_id):
        typer.echo(f"already on disk: {ref.title} (use --force to re-fetch)")
        d = storage.episode_dir(ref.podcast_slug, ref.episode_id)
        typer.echo(f"  {d}")
        return

    typer.echo(f"fetching: {f.display_name} — {ref.title}")
    try:
        ep = f.fetch(ref)
    except Exception as e:
        typer.echo(f"error fetching transcript: {e}", err=True)
        raise typer.Exit(1) from e
    path = storage.save_episode(ep)
    typer.echo(
        f"saved {len(ep.transcript):,} chars from {ep.transcript_source} → {path}"
    )


@app.command("fetch-all")
def fetch_all_cmd(
    podcast: str = typer.Argument(..., help=f"Podcast slug. One of: {', '.join(all_slugs())}"),
    delay: float = typer.Option(0.5, "--delay", help="Seconds to sleep between requests (be polite to upstream)."),
    skip_existing: bool = typer.Option(True, "--skip-existing/--no-skip-existing", help="Skip episodes already on disk."),
    reverse: bool = typer.Option(False, "--reverse", help="Iterate oldest-first instead of newest-first."),
):
    """Fetch every available episode for a podcast.

    Continues past per-episode errors. Prints a final tally of saved /
    skipped / failed.
    """
    import time

    f = get_fetcher(podcast)
    typer.echo(f"enumerating episodes for {f.display_name}…")
    refs = f.iter_all_refs()
    if reverse:
        refs = list(reversed(refs))
    typer.echo(f"  → {len(refs)} candidate episodes")

    saved = skipped = failed = 0
    for i, ref in enumerate(refs, start=1):
        prefix = f"[{i:>4}/{len(refs)}] {ref.episode_id:>5}"
        if skip_existing and storage.episode_exists(ref.podcast_slug, ref.episode_id):
            typer.echo(f"{prefix} skip (cached): {ref.title[:80]}")
            skipped += 1
            continue
        try:
            ep = f.fetch(ref)
            storage.save_episode(ep)
            typer.echo(
                f"{prefix} ok ({len(ep.transcript):>7,} chars, {ep.transcript_source}): {ref.title[:70]}"
            )
            saved += 1
        except Exception as e:
            typer.echo(f"{prefix} FAIL: {ref.title[:60]} — {e}", err=True)
            failed += 1
        if delay:
            time.sleep(delay)

    typer.echo(f"\n=== {f.display_name}: saved={saved} skipped={skipped} failed={failed} ===")


@app.command("summarize")
def summarize_cmd(
    podcast: str = typer.Argument(...),
    episode_id: str = typer.Argument(..., help="Episode id (e.g. 1076 or 100)"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b", help="anthropic | do"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name (overrides default)"),
    force: bool = typer.Option(False, "--force", help="Re-summarize even if cached."),
):
    """Summarize a previously-fetched episode using an LLM backend."""
    from .summarize import run as run_summary  # lazy import to avoid SDK load on plain list/fetch

    slug = get_fetcher(podcast).slug
    if not storage.episode_exists(slug, episode_id):
        typer.echo(
            f"no transcript on disk for {slug}/{episode_id}. run `briefing fetch` first.",
            err=True,
        )
        raise typer.Exit(1)
    ep = storage.load_episode(slug, episode_id)
    try:
        path, summary = run_summary(ep, backend=backend, model=model, force=force)
    except Exception as e:
        typer.echo(f"summarization failed: {e}", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"summary → {path}\n")
    typer.echo(summary)


@app.command("summarize-all")
def summarize_all_cmd(
    podcast: str = typer.Argument(..., help=f"Podcast slug. One of: {', '.join(all_slugs())}"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    delay: float = typer.Option(0.0, "--delay", help="Pause between calls (seconds)."),
    force: bool = typer.Option(False, "--force"),
):
    """Summarize every episode on disk for a podcast. Skips cached summaries."""
    from .summarize import run as run_summary

    slug = get_fetcher(podcast).slug
    base = storage.project_root() / slug
    if not base.exists():
        typer.echo(f"no episodes on disk for {slug}", err=True)
        raise typer.Exit(1)

    eps_ids = sorted(
        (p.name for p in base.iterdir() if (p / "transcript.txt").exists()),
        key=lambda x: (-_int_or_zero(x), x),
    )
    typer.echo(f"summarizing {len(eps_ids)} episodes of {slug}…")

    import time
    saved = skipped = failed = 0
    for i, eid in enumerate(eps_ids, 1):
        prefix = f"[{i:>4}/{len(eps_ids)}] {eid:>5}"
        try:
            ep = storage.load_episode(slug, eid)
            if not ep.transcript.strip():
                typer.echo(f"{prefix} skip (empty transcript)")
                skipped += 1
                continue
            path, _ = run_summary(ep, backend=backend, model=model, force=force)
            typer.echo(f"{prefix} ok → {path.name}")
            saved += 1
        except Exception as e:
            typer.echo(f"{prefix} FAIL — {e}", err=True)
            failed += 1
        if delay:
            time.sleep(delay)

    typer.echo(f"\n=== {slug}: saved={saved} skipped={skipped} failed={failed} ===")


def _int_or_zero(s: str) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


@app.command("brief")
def brief_cmd(
    podcast: str = typer.Argument(...),
    latest: bool = typer.Option(False, "--latest"),
    episode: Optional[str] = typer.Option(None, "--episode", "-e"),
    search: Optional[str] = typer.Option(None, "--search", "-s"),
    backend: Optional[str] = typer.Option(None, "--backend", "-b"),
    model: Optional[str] = typer.Option(None, "--model", "-m"),
    force: bool = typer.Option(False, "--force"),
):
    """Fetch + summarize in one step."""
    from .summarize import run as run_summary

    f, ref = _resolve_ref(podcast, latest, episode, search)
    if force or not storage.episode_exists(ref.podcast_slug, ref.episode_id):
        typer.echo(f"fetching: {f.display_name} — {ref.title}")
        ep = f.fetch(ref)
        storage.save_episode(ep)
    else:
        typer.echo(f"using cached transcript for {ref.title}")
        ep = storage.load_episode(ref.podcast_slug, ref.episode_id)

    path, summary = run_summary(ep, backend=backend, model=model, force=force)
    typer.echo(f"\nsummary → {path}\n")
    typer.echo(summary)


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main() or 0)
