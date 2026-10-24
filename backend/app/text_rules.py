"""Small shared text rules. Words match at a word start, so "run"/"running" match
but "brunch" doesn't."""

import re

_ATHLETIC = re.compile(r"\b(run|runs|running|jog|jogging|gym|workout|yoga|athletic|pilates|hike|hiking|tennis|climb|climbing|spin class)\b", re.IGNORECASE)


def is_athletic(text: str) -> bool:
    return bool(_ATHLETIC.search(text or ""))


def has_word(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}", text, re.IGNORECASE) for w in words)
