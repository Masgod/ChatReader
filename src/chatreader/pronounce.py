
"""User pronunciation rules: plain-text, whole-word, case-insensitive replacements on the spoken string."""
import re


def apply_pronunciations(text: str, rules: dict[str, str]) -> str:
    if not rules:
        return text
    table = {k.casefold(): v for k, v in rules.items() if k}
    if not table:
        return text
    keys = sorted(table, key=len, reverse=True)  # longest first, so "hi there" beats "hi"
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in keys) + r")(?!\w)", re.IGNORECASE)
    return pattern.sub(lambda m: table.get(m.group(0).casefold(), m.group(0)), text)  # one pass: a result is never re-matched
