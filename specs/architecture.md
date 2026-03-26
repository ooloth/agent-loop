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
│              CLI / Entrypoints          │
│         (parse args, load config)       │
└────────────────────┬────────────────────┘
                     │
┌────────────────────▼────────────────────┐
│              Feature Pipelines          │  analyze, fix, watch
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

## Domain engine

`implement_and_review(task: ImplementAndReviewInput) -> ImplementAndReviewResult`

The engine is the only place that understands the implement→review→address loop.
It has no knowledge of which AI provider, VCS system, or issue tracker is in use.

It receives `AgentBackend` and `VCSBackend` via `ImplementAndReviewInput` and
uses them for all I/O. It emits `ImplementAndReviewResult` — a pure value with
no side effects remaining.

```
ImplementAndReviewInput:
  title:                string        -- issue title
  body:                 string        -- issue description
  implement_agent:      AgentBackend  -- edit access; writes code
  review_agent:         AgentBackend  -- read-only access; inspects diff
  vcs:                  VCSBackend
  max_iterations:       integer
  context:              string        -- optional project context prepended to prompts
  fix_prompt_template:  string        -- template for the initial fix prompt
  review_prompt:        string        -- base prompt for the reviewer

ImplementAndReviewResult:
  review_log:           list<ReviewEntry>  -- one entry per review iteration
  converged:            bool               -- true if reviewer approved
  has_changes:          bool               -- true if staged diff is non-empty
  implement_response:   string             -- agent response to initial fix prompt

ReviewEntry:
  iteration:  integer
  approved:   bool
  feedback:   string
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
      BranchSession(issue, tracker, vcs): (branch management + cleanup)
        implement_and_review(engine_input)
        → BranchSession.commit_and_push()
        → IssueTracker.open_pr(issue, branch)
        → IssueTracker.comment_on_pr(pr_ref, review_comment)
```

`BranchSession` is a concrete context manager (not a protocol) that handles
branch creation, checkout, and cleanup. It takes `VCSBackend` for the
workflow-level git operations that sit outside the engine.

### `watch` pipeline

```
loop:
  fix pipeline (if ready issues exist)
  analyze pipeline (if tracker.list_awaiting_review().count < cap)
  sleep(interval)
```

The backpressure check uses `list_awaiting_review()` — issues pending human
triage — not a general open-issue count.

---

## Domain types

```
AppContext:                     -- composition root; passed to every pipeline command
  project_dir:  path
  config:       Config
  tracker:      IssueTracker
  vcs:          VCSBackend
  read_agent:   AgentBackend   -- read-only; used by analyze + fix review
  edit_agent:   AgentBackend   -- edit access; used by fix implement

Config:                         -- loaded from .agent-loop.yml
  max_iterations:       integer
  context:              string
  analyze_prompt?:      string  -- optional; falls back to built-in default
  fix_prompt_template?: string  -- optional; falls back to built-in default
  review_prompt?:       string  -- optional; falls back to built-in default

Issue:                          -- a work item in the tracker; tracker-agnostic
  number:   integer
  title:    string
  body:     string
  labels:   set<string>

FoundIssue:                     -- output of the analyze step, before filing
  title:    string
  body:     string
  labels:   list<string>        -- default empty
```

---

## What is NOT abstracted

- **Branch naming** (`fix/issue-{number}`) — concrete in the fix pipeline; if a
  different tracker uses different identifiers, `BranchSession` receives the
  branch name as a parameter from the pipeline.
- **Config loading** — stays concrete (YAML → `Config`). The config format is
  an intentional user-facing contract, not a backend concern.
- **Logging** — stays concrete. It's a cross-cutting concern, not a port.
- **Default prompts** — built-in defaults live alongside each pipeline. Users
  can override any of them via the config file.
