"""BibTeX escaping: special characters and accented Unicode to LaTeX.

Kept apart from the citation formatter so that any record formatter can
import it without importing the formatter itself.
"""

from __future__ import annotations

import unicodedata

# BibTeX special characters that must be escaped.
_BIBTEX_ESCAPES: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "$": r"\$",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Common Unicode → LaTeX replacements (combining diacritics approach).
_UNICODE_TO_LATEX: dict[str, str] = {
    "̀": "`",  # grave
    "́": "'",  # acute
    "̂": "^",  # circumflex
    "̃": "~",  # tilde
    "̄": "=",  # macron
    "̈": '"',  # diaeresis / umlaut
    "̌": "v",  # caron
    "̧": "c",  # cedilla
    "̨": "k",  # ogonek
}


def escape_bibtex(text: str) -> str:
    """Escape special characters and convert Unicode to LaTeX commands.

    Args:
        text: Raw text string.

    Returns:
        BibTeX-safe string with special chars escaped and common
        Unicode accented characters converted to LaTeX commands.
    """
    nfd = unicodedata.normalize("NFD", text)
    result: list[str] = []
    i = 0
    while i < len(nfd):
        ch = nfd[i]
        if (
            i + 1 < len(nfd)
            and unicodedata.category(nfd[i + 1]) == "Mn"
            and nfd[i + 1] in _UNICODE_TO_LATEX
        ):
            accent = _UNICODE_TO_LATEX[nfd[i + 1]]
            base = _BIBTEX_ESCAPES.get(ch, ch)
            result.append(f"{{\\{accent}{base}}}")
            i += 2
        else:
            # Check if this is a base char followed by an unmapped
            # combining mark — normalise back to NFC to avoid orphaning.
            if (
                i + 1 < len(nfd)
                and unicodedata.category(nfd[i + 1]) == "Mn"
                and nfd[i + 1] not in _UNICODE_TO_LATEX
            ):
                composed = unicodedata.normalize("NFC", ch + nfd[i + 1])
                result.append(composed)
                i += 2
            else:
                result.append(_BIBTEX_ESCAPES.get(ch, ch))
                i += 1
    return "".join(result)
