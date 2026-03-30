from agent_loop.domain.context import AppContext
from agent_loop.domain.ports.agent_backend import InteractiveAgentBackend
from agent_loop.features.plan.prompts import PLAN_SYSTEM_PROMPT
from agent_loop.io.observability.logging import log


def cmd_plan(ctx: AppContext, agent: InteractiveAgentBackend, *, idea: str | None = None) -> None:
    """Launch an interactive planning session to produce a ralph-ready plan file."""
    plans_dir = ctx.project_dir / ".plans"
    plans_dir.mkdir(exist_ok=True)

    system_prompt = PLAN_SYSTEM_PROMPT
    if ctx.config.context:
        system_prompt = f"Project context:\n{ctx.config.context}\n\n{system_prompt}"

    log(f"📋 Planning session — plans will be written to {plans_dir.relative_to(ctx.project_dir)}/")

    agent.session(system_prompt=system_prompt, initial_message=idea)
