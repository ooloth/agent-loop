import textwrap

RALPH_PROMPT_TEMPLATE = textwrap.dedent("""\
    You are completing a task through iterative refinement. Each time you
    are called, you see the current state of the codebase with fresh eyes
    — you have no memory of previous iterations, but the codebase may
    contain changes from prior steps.

    Your goal:
    {goal}

    Instructions:
    1. Compare the current codebase against the goal
    2. Identify the single most impactful improvement — this could be new
       progress toward the goal, or correcting something a prior step got
       wrong
    3. Make that one change
    4. If acceptance criteria are listed above, verify EACH one against the
       current codebase before deciding whether the goal is complete
    5. If the goal is now FULLY and CORRECTLY achieved, output ##DONE## on
       a line by itself
    6. If work remains or quality could be improved, do NOT output ##DONE##
""")
