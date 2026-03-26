# Architecture

## Goal

Decouple the domain logic (analyze, implement, review) from the backends it runs
on (AI provider, VCS, issue tracker), so that:

- The engine is independently testable without subprocesses
- Pipelines can target GitLab, Linear, or other backends without forking
- New use cases (e.g. reviewing PRs instead of issues) can reuse the engine

---

## Layers

```
┌─────────────────────────────────────────┐
│              CLI / Entrypoints          │  cli.py
│         (parse args, load config)       │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│              Feature Pipelines          │  analyze/, fix/, watch/
│   (orchestrate ports + domain engine)   │
└──────┬─────────────┬────────────────────┘
       │             │
┌──────▼──────┐ ┌────▼────────────────────┐
│   Domain    │ │         Ports           │
│   Engine    │ │  (protocols / interfaces│
│             │ │   the pipelines depend  │
│  implement  │ │   on, not the reverse)  │
│  _and_      │ │                         │
│  review()   │ │  AgentBackend           │
│             │ │  VCSBackend             │
│             │ │  IssueTracker           │
└─────────────┘ └────────────┬────────────┘
                             │
               ┌─────────────▼────────────┐
               │         Adapters         │
               │  (concrete backends)     │
               │                          │
               │  ClaudeCliBackend        │
               │  GitBackend              │
               │  GitHubTracker           │
               └─────────────────────────┘
```

---

## File structure

```
src/agent_loop/
  domain/                   # cross-cutting domain concepts — no I/O ever
    issues.py               # Issue, FoundIssue
    config.py               # Config TypedDict, DEFAULT_CONFIG
    context.py              # AppContext (composition root threaded through pipelines)
    protocols.py            # AgentBackend, VCSBackend, IssueTracker
  io/                       # cross-cutting helpers — all I/O and side effects
    config.py               # load_config()
    logging.py              # log, log_step, log_detail
    process.py              # run() — generic subprocess helper used by all adapters
    adapters/               # concrete protocol implementations
      claude_cli.py         # ClaudeCliBackend
      git.py                # GitBackend
      github.py             # GitHubTracker
  features/                 # use cases that orchestrate domain + io
    analyze/                # analyze pipeline
      prompts.py            # ANALYZE_PROMPT default
    fix/                    # fix pipeline
      engine.py             # implement_and_review() + input/output types + helpers
      prompts.py            # FIX_PROMPT_TEMPLATE, REVIEW_PROMPT defaults
      review.py             # format_review_comment() — formats review trail for PR
    watch/                  # watch pipeline
  cli.py                    # composition root — wires everything together
```

---

## Domain engine

`features/fix/engine.py`

The engine is the only place that understands the implement→review→address loop.
It has no knowledge of which AI provider, VCS system, or issue tracker is in use.

It receives `AgentBackend` and `VCSBackend` via `ImplementAndReviewInput` and
uses them for all I/O. It emits `ImplementAndReviewResult` — a pure value with
no side effects remaining.

```python
@dataclass(frozen=True)
class ImplementAndReviewInput:
    title: str
    body: str
    implement_agent: AgentBackend   # edit tools — writes code
    review_agent: AgentBackend      # read-only tools — inspects diff
    vcs: VCSBackend
    max_iterations: int
    context: str
    fix_prompt_template: str
    review_prompt: str

@dataclass(frozen=True)
class ImplementAndReviewResult:
    review_log: list[ReviewEntry]   # one entry per review iteration
    converged: bool                 # True if reviewer approved
    has_changes: bool               # True if staged diff is non-empty
    implement_response: str         # agent's response to the initial fix prompt
```

See: `specs/agent-backend.md`, `specs/vcs-backend.md`

---

## Feature pipelines

### `analyze` pipeline

```
AgentBackend.run(analyze_prompt)
  → parse JSON from response
  → IssueTracker.list_open_titles()       (dedup)
  → IssueTracker.create_issue(found)      (for each new issue)
```

### `fix` pipeline

```
IssueTracker.list_ready_issues()          (or get_issue for --issue N)
  → guard: is_ready_to_fix(issue) + is_claimed(issue)
  → for each issue:
      BranchSession(issue, tracker, git): (branch management + cleanup)
        implement_and_review(engine_input)
        → BranchSession.commit_and_push()
        → IssueTracker.open_pr(issue, branch)
        → IssueTracker.comment_on_pr(pr_ref, review_comment)
```

`BranchSession` is a concrete context manager (not a protocol) that handles
branch creation, checkout, and cleanup. It wraps a `GitBackend` for the
workflow-level git operations (checkout, branch, commit, push) that sit outside
the engine.

### `watch` pipeline

```
loop:
  fix pipeline (if ready issues exist)
  analyze pipeline (if len(tracker.list_awaiting_review()) < cap)
  sleep(interval)
```

The backpressure check uses `list_awaiting_review()` — issues with the
`needs-human-review` label — not a general open-issue count.

---

## Domain types

```python
# Composition root — wired once in cli.py, passed to every pipeline command
@dataclass(frozen=True)
class AppContext:
    project_dir: Path
    config: Config
    agent: AgentBackend
    tracker: IssueTracker

# Config loaded from .agent-loop.yml — required keys plus optional prompt overrides
class Config(TypedDict):
    max_iterations: int   # required
    context: str          # required (empty string is valid)
    # Optional prompt overrides (fall back to prompts.py defaults when absent):
    analyze_prompt: str
    fix_prompt_template: str
    review_prompt: str

# Core issue representation — used across all pipelines
@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: frozenset[str]

# Output of the analyze step — before filing in a tracker
@dataclass(frozen=True)
class FoundIssue:
    title: str
    body: str
    labels: list[str] = field(default_factory=list)
```

`Issue` and `FoundIssue` live in `domain/issues.py`. `AppContext` lives in
`domain/context.py`. `Config` lives in `domain/config.py`. All are tracker-agnostic.

---

## What is NOT abstracted

- **Branch naming** (`fix/issue-{number}`) — concrete in the fix pipeline; if a
  different tracker uses different identifiers, the `BranchSession` receives the
  branch name as a parameter from the pipeline.
- **Config loading** — stays concrete (`yaml` → `Config` TypedDict). The config
  format is an intentional user-facing contract, not a backend concern.
- **Logging** — stays concrete. It's a cross-cutting concern, not a port.
- **Default prompts** — `analyze/prompts.py` and `fix/prompts.py` hold the
  behavioral defaults. Users can override any of them via `.agent-loop.yml`.
