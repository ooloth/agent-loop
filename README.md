# agency

A meta-harness that runs AI coding agents through automated multi-step workflows — analyze, plan, fix, review, repeat.

## Features

- **[analyze](src/agent_loop/features/analyze/)** — scan a codebase for issues and file them in the tracker
- **[fix](src/agent_loop/features/fix/)** — pick up tracked issues (or ad-hoc specs), run an implement→review loop, open PRs
- **[watch](src/agent_loop/features/watch/)** — continuous loop: fix ready issues, analyze when the queue is low, sleep
- **[plan](src/agent_loop/features/plan/)** — interactive session to explore a codebase and produce a structured plan
- **[ralph](src/agent_loop/features/ralph/)** — iterative fresh-eyes refinement toward a goal, committing per iteration

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the layered architecture, domain
types, and feature pipeline overview. Protocol contracts and behavioral
invariants live as docstrings adjacent to the code they describe.

## Configuration

Drop a `.agent-loop.yml` in your project root to customize behavior. All fields
are optional — sensible defaults are built in. See the `Config` type in
[`ARCHITECTURE.md`](ARCHITECTURE.md#domain-types) for the full schema.

## Inspiration

- [Case Statement: Building a Harness](https://nicknisi.com/posts/case-statement/) + [workos/case](https://github.com/workos/case) by Nick Nisi
- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/) by Ryan Lopopolo
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) by Justin Young
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) by Prithvi Rajasekaran
- [Harness Engineering](https://martinfowler.com/articles/exploring-gen-ai/harness-engineering.html) by Birgitta Böckler
- [Relocating Rigor](https://aicoding.leaflet.pub/3mbrvhyye4k2e) by Chad Fowler
- [Skill Issue: Harness Engineering for Coding Agents](https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents) by Kyle Mistele
- [Engineer the Harness](https://mitchellh.com/writing/my-ai-adoption-journey#step-5-engineer-the-harness) by Mitchell Hashimoto
