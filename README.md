# security-briefing

Pull transcripts of four security podcasts (Risky Business, Critical Thinking, Darknet Diaries, Security Now) and summarize them with an LLM into an actionable digest. Audio is never downloaded; transcripts come from each podcast's existing source.

## Transcript sources

| Podcast            | Source                                                       |
| ------------------ | ------------------------------------------------------------ |
| Security Now       | `grc.com/sn/sn-{N}.txt` (official plain-text)                |
| Darknet Diaries    | `darknetdiaries.com/transcript/{N}/` (official HTML)         |
| Critical Thinking  | `criticalthinkingpodcast.io/episode-{N}-{slug}/` (official)  |
| Risky Business     | YouTube auto-captions on `@riskybizmedia` (no published transcript) |

## Setup

Requires Python 3.12+. Install into a venv (this project assumes `~/venvs/briefing`):

```bash
python3.12 -m venv ~/venvs/briefing            # if it doesn't already exist
~/venvs/briefing/bin/pip install -e .
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY and/or DIGITAL_OCEAN_MODEL_ACCESS_KEY
```

Either activate the venv (`source ~/venvs/briefing/bin/activate`) or call the
binary directly via `~/venvs/briefing/bin/briefing`. A handy alias:

```bash
alias briefing=~/venvs/briefing/bin/briefing
```

## Usage

```bash
# List recent episodes
briefing list security-now --limit 5
briefing list darknet-diaries
briefing list critical-thinking
briefing list risky-business

# Aliases work too: sn, dd, ct, rb
briefing list rb -n 3

# Fetch a transcript (saves to ./episodes/<slug>/<id>/)
briefing fetch security-now --latest
briefing fetch darknet-diaries --episode 100
briefing fetch critical-thinking --search "oauth"
briefing fetch rb --latest

# Summarize a previously-fetched episode
briefing summarize security-now 1076                 # default backend (anthropic)
briefing summarize sn 1076 --backend do              # use DigitalOcean inference
briefing summarize dd 100 --backend do --model llama3.3-70b-instruct

# Fetch + summarize in one step
briefing brief darknet-diaries --latest
briefing brief sn --search "supply chain" --backend do
```

## Output layout

```
episodes/
└── <slug>/<id>/
    ├── metadata.json
    ├── transcript.txt
    └── summary-{backend}-{model}.md
```

Multiple backend/model summaries coexist for the same episode — running `summarize` with a different backend doesn't overwrite the previous one.

## Summary format

Every summary is markdown with four fixed sections:

```
## Topic
2-3 sentences on what the episode is about.

## New tools mentioned
- Tools, libraries, frameworks, services with one-line descriptions.

## Key security insights
- Vulnerabilities, exploits, defensive techniques, attacker behaviors.

## Workflows / techniques
- Concrete step-by-step methodologies that led to a finding.
```

## Backends

- `anthropic` — direct Anthropic API. Default model: `claude-opus-4-7`. Set `ANTHROPIC_API_KEY`.
- `do` — DigitalOcean Serverless Inference (OpenAI-compatible at `https://inference.do-ai.run/v1/`). Default model: `llama3.3-70b-instruct`. Set `DIGITAL_OCEAN_MODEL_ACCESS_KEY`. Override the model with `--model` to use any model in your DO catalog (e.g. `anthropic-claude-sonnet-4-5`, `openai-gpt-4o`).

Default backend is `anthropic`; override per command with `--backend` or globally via `BRIEFING_BACKEND=do` in `.env`.

## Notes

- **Security Now transcripts lag a few hours behind audio.** A 404 on `--latest` likely means GRC hasn't posted the transcript yet — try the previous episode.
- **YouTube auto-captions** for Risky Business are decent but imperfect. Tool names and proper nouns are the most common transcription errors; spot-check the summary's "New tools mentioned" section.
- The `briefing fetch` command is **idempotent** and short-circuits if the episode is already on disk; pass `--force` to re-fetch.
- The `briefing summarize` command **caches** by `<backend>-<model>`; pass `--force` to re-run.
