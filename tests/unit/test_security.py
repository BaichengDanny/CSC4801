def test_sql_metacharacters_remain_bound_values(people, monkeypatch):
    from recruiting import accounts, jobs
    from recruiting.db import get_db
    from recruiting.errors import DomainError
    import pytest
    payload = "x' or 1=1; drop table users;--"
    original = get_db()
    calls = []

    class RecordingConnection:
        def execute(self, sql, parameters=()):
            calls.append((sql, parameters))
            return original.execute(sql, parameters)

    monkeypatch.setattr(accounts, 'get_db', lambda: RecordingConnection())
    with pytest.raises(DomainError) as error:
        accounts.authenticate(payload, 'DemoPass123!')
    assert error.value.status == 401
    assert any(payload in params and payload not in sql for sql, params in calls)
    j = jobs.create_job(people['employer'], payload, payload, ['python'])
    assert jobs.job(people['candidate'], j['id'])['title'] == payload
    assert original.execute('SELECT count(*) FROM users').fetchone()[0] == 4
