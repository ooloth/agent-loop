import textwrap

ANALYZE_PROMPT = textwrap.dedent("""\
    Analyze this codebase for issues. For each issue found, respond with a JSON array
    of objects, each with:
      - "title": short summary (suitable for a GitHub issue title)
      - "body": issue description formatted in markdown using EXACTLY this structure:

        ## 🐛 Problem
        One or two sentences describing what is wrong.

        ## 📍 Location
        - `path/to/file.py` — `ClassName.method_name()` or `function_name`
        - (list each relevant location as a bullet)
        - Use symbol names (class, function, variable), NOT line numbers — line
          numbers go stale as code changes and make issues brittle.

        ## 💥 Impact
        - What happens as a result
        - Why it matters
        - How severe (e.g. crash, silent data loss, cosmetic)

        ## 🔄 Current Behavior
        What the code does now (briefly, with a short code snippet if helpful).

        ## ✅ Expected Behavior
        What the code should do instead.

        Use bullet lists instead of paragraphs where possible. Keep it scannable.

      - "labels": optional list of additional labels (e.g. "bug", "refactor", "performance")

    Focus on real, actionable problems — not style nitpicks.
    Respond ONLY with the JSON array, no other text.
""")
