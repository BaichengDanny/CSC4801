from datetime import datetime, timezone

import pytest
from flask.testing import FlaskClient


class MatchworkClient(FlaskClient):
    def post(self, path, *, csrf=True, headers=None, **kwargs):
        if csrf:
            token = self.get('/api/auth/csrf').json['csrfToken']
            headers = {**(headers or {}), 'X-CSRF-Token': token}
        return super().post(path, headers=headers, **kwargs)


@pytest.fixture
def app(tmp_path):
    from recruiting import create_app
    from recruiting.db import migrate

    app = create_app({
        'TESTING': True, 'DATABASE': str(tmp_path / 'test.sqlite3'),
        'SECRET_KEY': 'test-key-not-a-production-secret',
        'NOW': lambda: datetime(2030, 1, 1, 9, tzinfo=timezone.utc),
    })
    app.test_client_class = MatchworkClient
    with app.app_context():
        migrate()
        yield app


@pytest.fixture
def people(app):
    from recruiting.accounts import register, update_company, update_profile

    users = {
        'candidate': register('alex@example.test', 'DemoPass123!', 'Candidate', 'Alex Morgan'),
        'candidate2': register('blair@example.test', 'DemoPass123!', 'Candidate', 'Blair Chen'),
        'employer': register('north@example.test', 'DemoPass123!', 'Employer', 'Taylor Lee'),
        'employer2': register('field@example.test', 'DemoPass123!', 'Employer', 'Sam Rivera'),
    }
    update_profile(users['candidate'], 'Alex Morgan', ['Python', 'SQL'], 'Private resume')
    update_profile(users['candidate2'], 'Blair Chen', ['Python'], '')
    update_company(users['employer'], 'Northstar', 'A small engineering team.')
    update_company(users['employer2'], 'Fieldwork', 'Tools for better work.')
    return users
