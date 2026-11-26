import pytest


@pytest.mark.parametrize(('candidate', 'required', 'expected'), [
    (['Python', 'SQL'], ['Python', 'SQL'], 100),
    (['Python'], ['Python', 'SQL'], 50),
    (['Rust'], ['Python', 'SQL'], 0),
    ([], [], 100),
    ([' PYTHON ', 'python', '', 'SQL'], [' python', 'SQL ', 'sql', ''], 100),
    (['Python'], ['python', 'sql', 'rust'], 33),
])
def test_score_examples_normalization_and_floor(candidate, required, expected):
    from recruiting.matching import score
    result = score(candidate, required)
    assert result == expected
    assert isinstance(result, int)


def test_skill_normalization():
    from recruiting.matching import normalize_skills
    assert normalize_skills([' SQL ', '', 'Python', 'sql']) == ['python', 'sql']
