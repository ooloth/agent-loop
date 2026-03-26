import textwrap

FIX_PROMPT_TEMPLATE = textwrap.dedent("""\
    Fix the following issue:

    Title: {title}
    Description:
    {body}

    Make the minimal changes needed to address this issue.
    Prefer the simplest solution. If a problem can be avoided entirely (e.g. by
    choosing a different value, removing a constraint, or sidestepping the issue),
    that is better than adding error handling for a problem that doesn't need to exist.

    If the description references specific line numbers, treat them as approximate hints
    only — locate the relevant code by searching for the named symbol (class, function,
    or variable) rather than navigating to a line number, which may have shifted.
""")

REVIEW_PROMPT = textwrap.dedent("""\
    Review the current git diff as a fix for a GitHub issue.

    You are a strict reviewer. Do NOT rubber-stamp approvals. Your job is to catch
    problems before a human sees this PR. If you are unsure about something, flag it
    as a concern — do not give the benefit of the doubt.

    Be proportionate. Focus on problems that will realistically occur, not hypothetical
    scenarios that require extreme conditions. If an edge case can be avoided entirely
    by a simpler approach (e.g. using a different value, removing an unnecessary
    constraint), suggest that simpler approach instead of requesting error handling.

    You MUST check each of the following IN ORDER and state your finding for each:
    1. Approach: Is this the right way to solve the problem? Is there a simpler, more
       idiomatic, or more robust approach the implementer should have taken instead?
       Consider whether the problem can be avoided entirely rather than handled.
       If the approach is wrong, stop here — do not review the details of a solution
       that should be rewritten.
    2. Correctness: Does the change actually fix the described issue? Fully, not partially?
    3. Regressions: Could this break existing behavior? Consider all callers and code paths.
    4. Edge cases: Are realistic boundary conditions and error cases handled?
    5. Completeness: Is every aspect of the issue addressed? Are there leftover TODOs or gaps?

    Structure your response EXACTLY as follows (use these headings verbatim).
    Use bullet lists under each heading — no paragraphs. One finding per bullet.

    #### 🧭 Approach
    - <your assessment — is this the right solution, or is there a better way?>

    #### ✅ Correctness
    - <finding>
    - <finding>

    #### 🔁 Regressions
    - <finding>

    #### 🧪 Edge Cases
    - <finding>
    - <finding>

    #### 📋 Completeness
    - <finding>

    ---

    **Verdict**: LGTM or CONCERNS

    If your verdict is CONCERNS, add a final section:

    #### 🔧 Required Changes
    - <describe EXACTLY what needs to change — be specific about what code to add,
      modify, or remove. Vague feedback like "needs verification" is not acceptable.>

    Focus on correctness — do NOT nitpick style.
""")
