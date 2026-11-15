"""The single deterministic scoring implementation used by both dashboards."""
from .errors import DomainError


def normalize_skills(values):
    if not isinstance(values, (list, tuple)) or not all(isinstance(v, str) for v in values):
        raise DomainError(400, 'Skills must be a list of text values.')
    normalized = sorted({v.strip().lower() for v in values if v.strip()})
    if len(normalized) > 100 or any(len(v) > 80 for v in normalized):
        raise DomainError(400, 'Use at most 100 skills, each up to 80 characters.')
    return normalized


def score(candidate_skills, required_skills):
    candidate = set(normalize_skills(candidate_skills))
    required = set(normalize_skills(required_skills))
    return 100 if not required else 100 * len(candidate & required) // len(required)
