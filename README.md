# agency

> [!CAUTION]
> **Agency is a research project. If your name is not Michael Uloth, do not use it.**
>
> This software may change or break without notice. No support or warranty is provided. Use at your own risk.

## Overview

Agency is a meta-harness that runs other AI coding agents through automated multi-step workflows.

## Features

- **[analyze](src/agency/features/analyze/)** — scan a codebase for issues and file them in the tracker
- **[fix](src/agency/features/fix/)** — pick up tracked issues (or ad-hoc specs), run an implement→review loop, open PRs
- **[watch](src/agency/features/watch/)** — continuous loop: fix ready issues, analyze when the queue is low, sleep
- **[plan](src/agency/features/plan/)** — interactive session to explore a codebase and produce a structured plan
- **[ralph](src/agency/features/ralph/)** — iterative fresh-eyes refinement toward a goal, committing per iteration

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the layered architecture, domain
types, and feature pipeline overview. Protocol contracts and behavioral
invariants live as docstrings adjacent to the code they describe.

## Configuration

Drop a `.agency/config.yml` in your project root to customize behavior. All
fields are optional — sensible defaults are built in. See the `Config` type in
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
