# AgentBackend Protocol

The AI execution port. Abstracts "send a prompt, get a response" so the engine
and pipelines are independent of which AI provider or invocation method is used.

---

## Protocol definition

```
AgentBackend:
  run(prompt: string) -> string
```

---

## Contract

- `run()` blocks until the response is complete.
- Returns the raw response as a string. Callers are responsible for parsing
  structure (JSON, verdict keywords, etc.) out of the response.
- Raises (or exits) on unrecoverable failure. Does not return empty string as
  a sentinel for failure — callers may legitimately receive an empty response.
- Tool access (read-only vs. edit) is a backend concern, configured at
  construction time — not passed per call. This means you can construct two
  backend instances with different access levels and pass the right one for
  each role (implement vs. review).

---

## How it fits into ImplementAndReviewInput

Two named fields make the access-level distinction explicit in the type rather
than a runtime detail:

```
ImplementAndReviewInput:
  ...
  implement_agent: AgentBackend   -- edit access; writes code
  review_agent:    AgentBackend   -- read-only access; inspects diff
```

---

## Known adapters

### `ClaudeCliBackend` (current)

Runs the `claude` CLI as a subprocess. Takes a project directory and an access
level (edit tools vs. read-only tools) at construction time. The access level
is passed as an `--allowedTools` flag to the subprocess.

### Future adapters

- `AnthropicSdkBackend` — calls the Anthropic SDK directly (no subprocess)
- `OpenAiBackend` — for cost/speed experiments with different models
- `EchoBackend` — deterministic stub for testing; returns a preset response
