"""QA3-04 regression for the real authoritative score chain.

Default: authenticated Flask API -> the product frontend consumer, including
both original counterexamples. --browser runs full deployed API/page regression.
--legacy-functions retains the original local-demo diagnostic (still exits 1
for runtime casing differences); that calculator is not used by live portals.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

ROOT=Path(__file__).resolve().parents[2]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='output/qa3-04/unicode-api-contract.json')
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--legacy-functions',action='store_true')
    parser.add_argument('--source',help='Source tree for the preserved legacy diagnostic only')
    args=parser.parse_args()
    if args.legacy_functions or args.source:
        command=[sys.executable,str(ROOT/'tests/acceptance/legacy_unicode_probe.py'),'--output',args.output]
        if args.source:command+=['--source',args.source]
        if args.browser:command+=['--browser']
    elif args.browser:
        destination=ROOT/args.output
        destination.parent.mkdir(parents=True,exist_ok=True)
        artifacts=Path(tempfile.mkdtemp(prefix='unicode-browser-',dir=destination.parent))
        env=dict(os.environ,QA_OUTPUT=str(artifacts))
        result=subprocess.run([shutil.which('node') or 'node',str(ROOT/'tests/browser/authoritative.cjs')],
                              cwd=ROOT,env=env)
        # A fresh per-run directory prevents stale results masking a driver crash.
        destination.write_text((artifacts/'results.json').read_text(encoding='utf-8'),encoding='utf-8')
        return result.returncode
    else:
        command=[sys.executable,str(ROOT/'tests/acceptance/matching_parity.py'),'--unicode-only','--output',args.output]
    return subprocess.run(command,cwd=ROOT).returncode

if __name__=='__main__':sys.exit(main())
