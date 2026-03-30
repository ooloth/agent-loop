# Architecture

## Goal

Decouple the domain logic (analyze, fix, plan, ralph) from the backends it runs
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
│              Feature Pipelines          │  analyze, fix, plan, ralph, watch
│   (orchestrate ports + domain engine)   │
└──────┬─────────────┬────────────────────┘
       │             │
┌──────▼──────┐ ┌────▼────────────────────┐
│   Domain    │ │         Ports           │
│   Engine    │ │  (protocols / interfaces│
│             │ │   the pipelines depend  │
│  loop_until │ │   on, not the reverse)  │
│  _done()    │ │                         │
│             │ │  AgentBackend           │
│             │ │  InteractiveAgentBackend│
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

The engine provides a single entry point and a pluggable strategy protocol:

```
loop_until_done(work: WorkSpec, strategy: LoopStrategy, vcs: VCSBackend, options: LoopOptions) -> LoopResult
```

This is the only place that understands how to run an agent loop to completion.
It has no knowledge of which AI provider, VCS system, or issue tracker is in use.
The strategy owns the loop body; the engine provides the uniform call site and a
seam for future cross-cutting concerns (timing, metrics, error handling).

### WorkSpec

A unit of work to be completed, decoupled from its origin:

```
WorkSpec:
  title:  string  -- display label (may be truncated)
  body:   string  -- full description or goal text
```

Constructed via factory functions: `from_issue(Issue)`, `from_prompt(string)`,
`from_file(path)`.

### LoopOptions

Execution options for a loop run:

```
LoopOptions:
  max_iterations:  integer
  context:         string             -- optional project context prepended to prompts
  on_progress:     ProgressCallback   -- called with EngineEvent instances during execution
```

### LoopResult

Outcome of a loop run:

```
LoopResult:
  converged:    bool     -- true if the strategy signaled completion
  has_changes:  bool     -- true if staged diff is non-empty at the end
  iterations:   integer  -- how many iterations were executed
```

Strategy-specific state (review log, scratchpad, agent responses) lives on the
strategy instances, not on LoopResult. Callers that need strategy-specific data
access it via the strategy object after the loop completes.

### LoopStrategy protocol

```
LoopStrategy:
  execute(work: WorkSpec, vcs: VCSBackend, options: LoopOptions) -> LoopResult
```

### Strategies

#### AntagonisticStrategy

Implement → review → address-feedback loop with two opposing agents. The
implement agent writes code; the review agent inspects the diff and either
approves (LGTM) or requests changes. On rejection, the implement agent
addresses the feedback and the cycle repeats up to max_iterations.

Strategy-specific state after execution:
- `review_log: list<ReviewEntry>` — one entry per review iteration
- `initial_response: string` — the implement agent's first response

#### RalphStrategy

Fresh-eyes iterative refinement with a single agent. Each iteration the agent
sees the current codebase with no memory of prior iterations, compares it
against the goal, and makes one improvement. Commits after each iteration for
crash safety. A scratchpad is extracted from each response and injected into
the next iteration's prompt, giving fresh eyes context without conformity
pressure.

Strategy-specific state after execution:
- `responses: list<string>` — each iteration's agent response
- `scratchpad: string` — the final scratchpad content

### Termination conditions

```
TerminationCondition:
  is_met(response: string) -> bool
```

Two implementations:
- `ReviewApproval` — scans for an LGTM verdict (used by AntagonisticStrategy)
- `OutputSignal` — scans for a completion token on its own line, e.g. `##DONE##`
  (used by RalphStrategy)

### Progress events

Strategies report progress via a callback. Event types:

```
Implemented          -- implement agent completed the initial fix
NoChanges            -- implement agent produced no staged diff
DiffReady            -- a staged diff is ready for review
ReviewApproved       -- review agent approved
ReviewRejected       -- review agent requested changes
AddressedFeedback    -- implement agent addressed review feedback
StepStarted          -- ralph iteration starting
StepCompleted        -- ralph iteration finished (with done flag and scratchpad)
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

Two modes: issue-based and spec-based.

**Issue-based** (`cmd_fix`):

```
IssueTracker.list_ready_issues()          (or get_issue for --issue N)
  → guard: is_ready_to_fix(issue) + is_claimed(issue)
  → for each issue:
      BranchSession(issue, tracker, vcs): (branch management + cleanup)
        loop_until_done(work, AntagonisticStrategy, vcs, options)
        → BranchSession.commit_and_push()
        → IssueTracker.open_pr(issue, branch)
        → IssueTracker.comment_on_pr(pr_ref, review_comment)
```

**Spec-based** (`fix_from_spec`, via `--file` or `--prompt`):

```
guard: no uncommitted changes
VCSBackend.checkout(default) + pull + checkout_new_branch
  → loop_until_done(work, AntagonisticStrategy, vcs, options)
  → commit + push
  → IssueTracker.open_pr (draft)
  → IssueTracker.comment_on_pr(review_trail)
  → cleanup on failure: delete branch, return to default
```

`BranchSession` is a concrete context manager (not a protocol) that handles
branch creation, checkout, issue locking, and cleanup. Used only by issue-based
fix; spec-based fix manages its own branch lifecycle.

### `plan` pipeline

```
InteractiveAgentBackend.session(system_prompt, initial_message?)
```

Launches an interactive planning session. The agent explores the codebase,
discusses options with the user, and writes a plan file to `.plans/`. No
automated loop — the user drives the conversation.

### `ralph` pipeline

```
guard: no uncommitted changes
VCSBackend.checkout(default) + pull + checkout_new_branch
  → loop_until_done(work, RalphStrategy, vcs, options)
  → push
  → IssueTracker.open_pr (draft)
  → comment on PR if incomplete
  → cleanup on failure: delete branch, return to default
```

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

Config:                         -- loaded from .agent-loop.yml
  max_iterations:              integer
  context:                     string
  planning_agent_model?:       string
  planning_agent_effort:       string   -- default "high"
  coding_agent_model?:         string
  coding_agent_effort:         string   -- default "high"
  review_agent_model?:         string
  review_agent_effort:         string   -- default "high"
  analysis_agent_model?:       string
  analysis_agent_effort:       string   -- default "high"
  analyze_prompt?:             string   -- optional; falls back to built-in default
  fix_prompt_template?:        string   -- optional; falls back to built-in default
  review_prompt?:              string   -- optional; falls back to built-in default

Issue:                          -- a work item in the tracker; tracker-agnostic
  number:   integer
  title:    string
  body:     string
  labels:   frozenset<string>

FoundIssue:                     -- output of the analyze step, before filing
  title:    string
  body:     string
  labels:   tuple<string>       -- default empty
```

Agent backends are constructed per-command in the CLI dispatch layer, not
carried on AppContext. Each command wires the agents it needs with the
appropriate model, effort, and tool access settings from Config.

---

## What is NOT abstracted

- **Branch naming** (`fix/issue-{number}`, `fix/<slug>`, `ralph/<slug>`) —
  concrete in each pipeline. `BranchSession` receives the branch name as a
  parameter from the pipeline.
- **Config loading** — stays concrete (YAML → `Config`). The config format is
  an intentional user-facing contract, not a backend concern. Lives in io as
  bootstrap (startup assembly), not as a port-adapter pair.
- **Logging** — stays concrete. It's a cross-cutting concern, not a port. Lives
  in io as observability — the one io subpackage features may import directly.
- **Default prompts** — built-in defaults live alongside each pipeline. Users
  can override any of them via the config file.
