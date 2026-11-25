"""One command for backend units, actual frontend units, and matching parity.

Requires Python 3.12 with requirements.txt and Node.js 24; Playwright is only
needed for separate browser acceptance. No browser or application server is used.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-concurrency',action='store_true')
    parser.add_argument('--junitxml')
    args=parser.parse_args()
    node=shutil.which('node')
    if not node:
        raise SystemExit('Node.js 24 is required for frontend units. Install it as documented in INSTALL.md.')
    sys.path.insert(0,str(ROOT))
    import pytest
    pytest_args=['tests' if args.include_concurrency else 'tests/unit','-q']
    if args.junitxml: pytest_args.append('--junitxml='+args.junitxml)
    code=pytest.main(pytest_args)
    if code: return int(code)
    commands=[
        [node,'--test',*[str(p.relative_to(ROOT)) for p in sorted((ROOT/'tests/frontend').glob('*.test.cjs'))]],
        [sys.executable,'tests/acceptance/matching_parity.py'],
    ]
    for command in commands:
        result=subprocess.run(command,cwd=ROOT)
        if result.returncode: return result.returncode
    return 0

if __name__=='__main__': sys.exit(main())
