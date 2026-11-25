"""Finite semantic mutation experiment; writes ONLY to hidden isolated copies.

python tests/acceptance/mutation_check.py --output output/qa-round2/mutation
Run on Python 3.12 with product test dependencies. No mutation framework needed.
A passing equivalent mutant is excluded from the non-equivalent denominator.
Syntax/collection/environment/time-out errors are never counted as kills.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = 'tests/unit/test_round2_contracts.py::'
SCORE = CONTRACT + 'test_independent_golden_scores'
STATE = CONTRACT + 'test_booking_state_machine_and_exact_future_boundary'
OWNER = CONTRACT + 'test_role_owner_matrix_with_direct_requests'
# Each tuple is one exact, reviewable semantic change, not a regex mass rewrite.
MUTANTS = [
    ('score-empty-zero', 'recruiting/matching.py',
     'return 100 if not required', 'return 0 if not required', SCORE, False),
    ('score-ceiling', 'recruiting/matching.py',
     '100 * len(candidate & required) // len(required)',
     '-(-100 * len(candidate & required) // len(required))', SCORE, False),
    ('score-union', 'recruiting/matching.py',
     'len(candidate & required)', 'len(candidate | required)', SCORE, False),
    ('skills-case-sensitive', 'recruiting/matching.py',
     'v.strip(SKILL_WHITESPACE).lower()', 'v.strip(SKILL_WHITESPACE)', SCORE, False),
    ('skills-keep-whitespace', 'recruiting/matching.py',
     'v.strip(SKILL_WHITESPACE).lower()', 'v.lower()', SCORE, False),
    ('owner-check-disabled', 'recruiting/accounts.py',
     "if actor['id'] != owner_id:", "if False and actor['id'] != owner_id:", OWNER, False),
    ('role-check-disabled', 'recruiting/accounts.py',
     "if actor['role'] != role:", "if False and actor['role'] != role:", OWNER, False),
    ('duplicate-application-check-disabled', 'recruiting/jobs.py',
     "if db.execute('SELECT 1 FROM applications WHERE candidate_id = ? AND job_id = ?', (actor['id'], job_id)).fetchone():",
     "if False and db.execute('SELECT 1 FROM applications WHERE candidate_id = ? AND job_id = ?', (actor['id'], job_id)).fetchone():",
     CONTRACT + 'test_failed_writes_leave_all_related_and_unrelated_rows', False),
    ('job-delete-dependent-check-disabled', 'recruiting/jobs.py',
     "if (db.execute('SELECT 1 FROM applications WHERE job_id = ?', (job_id,)).fetchone()",
     "if False and (db.execute('SELECT 1 FROM applications WHERE job_id = ?', (job_id,)).fetchone()",
     CONTRACT + 'test_failed_writes_leave_all_related_and_unrelated_rows', False),
    ('booking-status-check-disabled', 'recruiting/scheduling.py',
     "if application['status'] != 'Interviewing':",
     "if False and application['status'] != 'Interviewing':", STATE, False),
    ('booking-future-inclusive', 'recruiting/scheduling.py',
     "if availability['starts_at'] <= now_timestamp():",
     "if availability['starts_at'] < now_timestamp():", STATE, False),
    ('booking-owner-check-disabled', 'recruiting/scheduling.py',
     "if availability['employer_id'] != application['employer_id']:",
     "if False and availability['employer_id'] != application['employer_id']:", STATE, False),
    ('booking-conflict-message', 'recruiting/scheduling.py',
     "'Slot already booked'", "'Not available'",
     'tests/unit/test_scheduling.py::test_booking_conflict_contract', False),
    ('json-id-coercion', 'recruiting/api.py',
     'if isinstance(value, bool) or not isinstance(value, (int, str)):',
     'if False and (isinstance(value, bool) or not isinstance(value, (int, str))):',
     CONTRACT + 'test_json_resource_id_does_not_coerce_or_crash', False),
    ('null-json-accepted', 'recruiting/api.py',
     'data = request.get_json(silent=True)',
     'data = request.get_json(silent=True)\n    if data is None:\n        data = {}',
     CONTRACT + 'test_non_object_and_malformed_json_are_rejected', False),
    ('job-id-tie-reversed', 'recruiting/jobs.py',
     "j['title'].lower(), j['id']", "j['title'].lower(), -j['id']",
     CONTRACT + 'test_both_views_recompute_oracle_and_stable_ties', False),
    ('candidate-id-tie-reversed', 'recruiting/jobs.py',
     "a['display_name'].lower(), a['candidate_id']",
     "a['display_name'].lower(), -a['candidate_id']",
     CONTRACT + 'test_both_views_recompute_oracle_and_stable_ties', False),
    ('equivalent-empty-score-expression', 'recruiting/matching.py',
     'return 100 if not required', 'return (50 + 50) if not required', SCORE, True),
]


def files_digest():
    paths = sorted((ROOT/'recruiting').rglob('*.py'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='output/qa-round2/mutation')
    args = parser.parse_args()
    output = (ROOT/args.output).resolve()
    if not output.is_relative_to((ROOT/'output').resolve()):
        raise ValueError('Mutation artifacts must stay inside the ignored output directory')
    output.mkdir(parents=True, exist_ok=True)
    run = output/('.isolated-' + str(time.time_ns()))
    run.mkdir()
    initial = files_digest()
    baseline = subprocess.run([sys.executable, '-m', 'pytest',
                               'tests/unit/test_round2_contracts.py', '-q'],
                              cwd=ROOT, capture_output=True, text=True, timeout=120)
    (output/'baseline.log').write_text(baseline.stdout+baseline.stderr, encoding='utf-8')
    if baseline.returncode:
        raise RuntimeError('Unmutated baseline failed; do not classify mutants')
    def execute(item):
        name, filename, original, replacement, test, equivalent = item
        isolated = run/name
        shutil.copytree(ROOT, isolated, ignore=shutil.ignore_patterns(
            '.git', '.venv', 'output', '__pycache__', '.pytest_cache', 'data',
            'instance', '.env', '.superpowers'))
        file = isolated/filename
        source = file.read_text(encoding='utf-8')
        if source.count(original) != 1:
            return {'name': name, 'status': 'error', 'reason': 'replacement was not unique'}
        mutated = source.replace(original, replacement)
        file.write_text(mutated, encoding='utf-8')
        (output/(name+'.patch.txt')).write_text(
            filename+'\n- '+original+'\n+ '+replacement+'\n', encoding='utf-8')
        record = {'name':name, 'file':filename, 'test':test, 'equivalent':equivalent,
                  'equivalence_reason': '100 == 50 + 50 for every empty-required input' if equivalent else None}
        try:
            compile(mutated, filename, 'exec')
            env = dict(os.environ, PYTHONPATH=str(isolated), PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([sys.executable, '-m', 'pytest', test, '-q',
                                     '--junitxml=result.xml'], cwd=isolated, env=env,
                                    text=True, capture_output=True, timeout=60)
            log = result.stdout+result.stderr
            (output/(name+'.log')).write_text(log,encoding='utf-8')
            suites = ET.parse(isolated/'result.xml').getroot().findall('testsuite')
            failures = sum(int(s.get('failures',0)) for s in suites)
            errors = sum(int(s.get('errors',0)) for s in suites)
            tests = sum(int(s.get('tests',0)) for s in suites)
            record.update(returncode=result.returncode, tests=tests, failures=failures, errors=errors)
            if errors or not tests or result.returncode not in (0,1):
                record['status'] = 'error'
            elif equivalent:
                record['status'] = 'equivalent' if result.returncode == 0 else 'error'
            else:
                record['status'] = 'killed' if failures and result.returncode == 1 else 'survived'
        except (SyntaxError, subprocess.TimeoutExpired, OSError, ET.ParseError) as error:
            record.update(status='error', reason=repr(error))
        print(record['status'].upper(), name, flush=True)
        return record
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(execute, MUTANTS))
    unchanged = initial == files_digest()
    counts = {status:sum(r['status']==status for r in records)
              for status in ('killed','survived','equivalent','error')}
    summary = {'method':'finite, hand-selected semantic mutants', 'counts':counts,
               'valid_non_equivalent':counts['killed']+counts['survived'],
               'source_unchanged':unchanged,'mutants':records}
    (output/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='mutants'},indent=2))
    if not unchanged or counts['error'] or counts['survived']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
