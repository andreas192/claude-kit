from kit.errors import KitError

FENCE = "---"


def parse_frontmatter(text: str) -> dict[str, str]:
    """Return the `key: value` lines between the leading `---` lines as raw strings."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FENCE:
        raise KitError("missing frontmatter: the file must start with a --- line")
    pairs: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == FENCE:
            return pairs
        key, sep, value = line.partition(":")
        if sep:
            pairs[key.strip()] = value.strip()
    raise KitError("unterminated frontmatter: no closing --- line")
