"""Historical diagnostic: the offline/demo calculator retains runtime Unicode casing.
Live portals consume API scores/ranks; this diagnostic is not the live gate.
Known open regression: runtime Unicode lowercase versions disagree.

This is deliberately an independent probe, not a passing CI assertion. It exits
1 when the actual Python and browser JS matchers disagree; retain its report.
--source output/qa-supplement/.baseline verifies the problem predates this work.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unicodedata

ROOT=Path(__file__).resolve().parents[2]
CASES=[
    {'candidate':['\u1c89'],'required':['\u1c8a']},
    {'candidate':['\ua7cb'],'required':['\u0264']},
]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default=str(ROOT))
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--output',default='output/qa-supplement/unicode-version-open.json')
    args=parser.parse_args()
    source=Path(args.source).resolve()
    sys.path.insert(0,str(source))
    from recruiting.matching import score
    program="""const fs=require('fs'),vm=require('vm');const context={window:{}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{const output={node:process.version,unicode:process.versions.unicode,
scores:cases.map(c=>context.window.MWMatch.matchScore(c.candidate,c.required))};
if(process.argv[2]==='browser'){
 const {chromium}=require('playwright');
 const browser=await chromium.launch({headless:true,executablePath:process.env.QA_BROWSER||
   (process.platform==='win32'?'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe':undefined)});
 try {const page=await browser.newPage();await page.addScriptTag({path:process.argv[1]});
 output.browserVersion=browser.version();
 output.browserScores=await page.evaluate(cases=>cases.map(c=>MWMatch.matchScore(c.candidate,c.required)),cases);
 }finally{await browser.close();}
}process.stdout.write(JSON.stringify(output));})().catch(e=>{console.error(e);process.exitCode=2;});"""
    process=subprocess.run([shutil.which('node') or 'node','-e',program,str(source/'shared/match.js'),
                            'browser' if args.browser else 'node'],
                           input=json.dumps(CASES),capture_output=True,text=True,encoding='utf-8',check=True,cwd=ROOT)
    actual=json.loads(process.stdout)
    records=[{**case,'python':score(case['candidate'],case['required']),
              'javascript':actual['scores'][index]} for index,case in enumerate(CASES)]
    if 'browserScores' in actual:
        for index,record in enumerate(records): record['browser']=actual['browserScores'][index]
    report={'browser_version':actual.get('browserVersion'),'source':str(source),'python_unicode':unicodedata.unidata_version,
            'node':actual['node'],'node_unicode':actual['unicode'],'cases':records,
            'differences':sum(r['python']!=r['javascript'] for r in records)}
    path=ROOT/args.output; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    return 1 if report['differences'] else 0

if __name__=='__main__': sys.exit(main())
