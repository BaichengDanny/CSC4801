import pytest
from werkzeug.security import check_password_hash


def test_registration_login_and_salted_hashes(app):
    from recruiting.accounts import register, authenticate
    from recruiting.db import get_db
    a = register(' A@EXAMPLE.TEST ', 'long-password', 'Candidate', 'Alex')
    b = register('b@example.test', 'long-password', 'Employer', 'Blair')
    assert a['email'] == 'a@example.test'
    assert a['role'] == 'Candidate'
    assert b['role'] == 'Employer'
    assert authenticate('A@example.test', 'long-password')['id'] == a['id']
    hashes = [r[0] for r in get_db().execute('SELECT password_hash FROM users')]
    assert hashes[0] != hashes[1]
    assert all(check_password_hash(h, 'long-password') for h in hashes)
    assert 'password_hash' not in a
    assert 'password_hash' not in authenticate('a@example.test', 'long-password')


@pytest.mark.parametrize(('email', 'password', 'role', 'name'), [
    ('', 'long-password', 'Candidate', 'Alex'),
    ('invalid', 'long-password', 'Candidate', 'Alex'),
    ('a@example.test', 'short', 'Candidate', 'Alex'),
    ('a@example.test', 'long-password', 'Admin', 'Alex'),
    ('a@example.test', 'long-password', 'Candidate', '  '),
])
def test_invalid_registration(app, email, password, role, name):
    from recruiting.accounts import register
    from recruiting.errors import DomainError
    from recruiting.db import get_db
    with pytest.raises(DomainError) as error:
        register(email, password, role, name)
    assert error.value.status == 400
    assert get_db().execute('SELECT count(*) FROM users').fetchone()[0] == 0


def test_duplicate_and_invalid_login(people):
    from recruiting.accounts import register, authenticate
    from recruiting.errors import DomainError
    with pytest.raises(DomainError) as error:
        register('ALEX@example.test', 'DemoPass123!', 'Employer', 'Other')
    assert error.value.status == 409
    for email, password in [('alex@example.test', 'wrong'), ('missing@example.test', 'wrong')]:
        with pytest.raises(DomainError) as error:
            authenticate(email, password)
        assert error.value.status == 401


def test_profile_skills_and_private_resume(people):
    from recruiting.accounts import profile, update_profile
    from recruiting.errors import DomainError
    c = people['candidate']
    update_profile(c, 'New name', [' SQL ', 'sql', 'Python'], 'Replacement resume')
    p = profile(c, c['id'])
    assert p['display_name'] == 'New name'
    assert p['skills'] == ['python', 'sql']
    assert p['resume'] == 'Replacement resume'
    for actor in [people['candidate2'], people['employer']]:
        with pytest.raises(DomainError) as error:
            profile(actor, c['id'])
        assert error.value.status == 403
    with pytest.raises(DomainError) as error:
        update_profile(people['employer'], 'No', [], 'No')
    assert error.value.status == 403


def test_company_profile(people):
    from recruiting.accounts import company, update_company
    from recruiting.errors import DomainError
    e = people['employer']
    update_company(e, 'New company', 'New description')
    assert company(e)['name'] == 'New company'
    assert company(e)['description'] == 'New description'
    with pytest.raises(DomainError) as error:
        update_company(people['candidate'], 'No', 'No')
    assert error.value.status == 403
