# VCSBackend Protocol

The version-control port. Abstracts all VCS operations used by the engine and
fix pipeline: staging, diffing, branching, committing, and pushing.

---

## Protocol definition

```
VCSBackend:
  has_uncommitted_changes()            -> bool    -- true if working tree or index is dirty
  stage_all()                          -> void    -- stage all changes (git add -A equivalent)
  diff_staged()                        -> string  -- return staged diff; empty string if none
  checkout(branch: string)             -> void    -- switch to an existing branch
  pull(branch: string)                 -> void    -- pull latest from remote
  checkout_new_branch(branch: string)  -> void    -- create/reset and switch to branch
  commit(message: string)              -> void    -- commit staged changes
  push(branch: string)                 -> void    -- push branch to remote
  delete_branch(branch: string)        -> void    -- delete a local branch
```

---

## Contract

- `has_uncommitted_changes()` checks both the working tree and the index. Used
  as a guard by pipelines that manage their own branches (fix-from-spec, ralph)
  to prevent starting work on a dirty tree.
- `stage_all()` is idempotent. Calling it when nothing has changed is safe.
- `diff_staged()` returns an empty string (not null, not an error) when there
  are no staged changes. Callers use the empty-string check to detect "no work
  was done" and short-circuit the review loop.
- `checkout_new_branch()` resets the branch if it already exists, so a prior
  failed attempt doesn't block a retry.
- `push()` uses force-with-lease semantics to avoid overwriting unexpected
  remote changes while still allowing re-pushes of amended fix branches.

---

## How it fits in

The engine uses `stage_all()` and `diff_staged()` via `ImplementAndReviewInput.vcs`.
`BranchSession` uses the full protocol via `AppContext.vcs` for branch lifecycle
management. Both take `VCSBackend` — the engine simply doesn't call the workflow
methods, which is enforced by its own input type, not by a narrower protocol.

---

## Known adapters

### `GitBackend` (current)

Wraps the `git` CLI via a shared subprocess transport in the io layer.

### Future adapters

- `NullVCSBackend` — no-op staging, returns a preset diff string; useful for
  testing the engine without touching the filesystem.
