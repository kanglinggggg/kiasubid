import re

_DOCUMENT_GENERIC_TOKENS = {
    "attachment",
    "attachments",
    "document",
    "documents",
    "envelope",
    "envelopes",
    "file",
    "files",
    "required",
    "submission",
    "upload",
    "uploads",
}


def display_qualification_code(value: str) -> str:
    """Remove a descriptive prefix only when a compact procurement code is present."""
    raw = " ".join(value.split())
    candidates = re.findall(r"[A-Za-z0-9]+(?:[/.-][A-Za-z0-9]+)+|[A-Za-z]{1,8}\d{1,8}", raw)
    coded = [candidate for candidate in candidates if any(char.isdigit() for char in candidate)]
    return coded[-1].upper() if coded else raw


def qualification_code_key(value: str) -> str:
    return "".join(re.findall(r"[A-Za-z0-9]+", display_qualification_code(value))).upper()


def document_name_key(value: str) -> tuple[str, ...]:
    """Create a conservative identity key while ignoring submission-channel wording."""
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    meaningful: list[str] = []
    for token in tokens:
        if token in _DOCUMENT_GENERIC_TOKENS or token in {"a", "an", "of", "the"}:
            continue
        if token.endswith("s") and len(token) > 4 and token != "cissp":
            token = token[:-1]
        meaningful.append(token)
    return tuple(sorted(meaningful)) if meaningful else tuple(tokens)
