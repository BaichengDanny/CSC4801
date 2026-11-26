"""The single deterministic scoring implementation used by both dashboards."""
from .errors import DomainError


# Explicit shared edge-whitespace set; see shared/match.js and SPEC.md.
# Preserve Python's existing whitespace and also strip the BOM JS trimmed.
SKILL_WHITESPACE = (
    '\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020'
    '\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006'
    '\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
)


def normalize_skills(values):
    if not isinstance(values, (list, tuple)) or not all(isinstance(v, str) for v in values):
        raise DomainError(400, 'Skills must be a list of text values.')
    normalized = sorted({v.strip(SKILL_WHITESPACE).lower() for v in values if v.strip(SKILL_WHITESPACE)})
    if len(normalized) > 100 or any(len(v) > 80 for v in normalized):
        raise DomainError(400, 'Use at most 100 skills, each up to 80 characters.')
    return normalized


def score(candidate_skills, required_skills):
    candidate = set(normalize_skills(candidate_skills))
    required = set(normalize_skills(required_skills))
    return 100 if not required else 100 * len(candidate & required) // len(required)
