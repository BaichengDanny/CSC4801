"""Historical comparison of the offline/demo calculator with Python.
Live portals consume API scores/ranks; this diagnostic is not the live gate.
Compare Python services with the real shared/match.js on identical inputs.

No JS algorithm is duplicated. Fixed examples have independent spec expectations;
generated cases use Python as a differential reference, not as a correctness proof.
"""
import argparse
from fractions import Fraction
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
SEED=48012027

def dataset():
    examples=[
      (['Python','SQL'],['Python','SQL'],100),(['Python'],['Python','SQL'],50),
      (['Rust'],['Python','SQL'],0),([],[],100),(['a'],['a','b','c'],33),
      (['a','b'],['a','b','c'],66),(['\ufeffPython'],['Python'],100),
      (['\u0085Python\u001c'],['Python'],100),
      (['\u200bPython'],['Python'],0),(['e\u0301'],['é'],0),
      (['ΟΣ','İ','É','中文'],['ος','i\u0307','é','中文'],100)]
    cases=[{'candidate':c,'required':r,'expected':e,'kind':'golden'} for c,r,e in examples]
    whitespace=['\t','\n','\v','\f','\r',' ','\u001c','\u001d','\u001e','\u001f','\u0085',
      '\u00a0','\u1680','\u2000','\u2001','\u2002','\u2003','\u2004','\u2005',
      '\u2006','\u2007','\u2008','\u2009','\u200a','\u2028','\u2029',
      '\u202f','\u205f','\u3000','\ufeff']
    for char in whitespace:
        cases.append({'candidate':[char+'Python'+char,char],
                      'required':['Python'],'expected':100,'kind':'trim-boundary'})
    rng=random.Random(SEED)
    vocab=['python','sql','rust','c++','c#','go','机器学习','é','e\u0301','Δ','ΟΣ',
           'İ','ı','ß','ẞ','\U00010400','\U00010428','😀','\u200bPython','\u180eSQL']
    for index in range(600):
        c=rng.sample(vocab,rng.randrange(0,9)); r=rng.sample(vocab,rng.randrange(0,9))
        cases.append({'candidate':c,'required':r,'kind':'generated'})
        # A metamorphic partner is compared independently in both engines.
        cases.append({'candidate':[rng.choice(whitespace)+s+rng.choice(whitespace) for s in c+c],
                      'required':[rng.choice(whitespace)+s+rng.choice(whitespace) for s in r+r],
                      'kind':'generated-variant','pair':len(cases)-1})
    job_groups=[
      [{'id':str(i),'seq':i,'title':title,'match':50} for i,title in [(10,'ALPHA'),(2,'alpha')]],
      [{'id':'2','title':'alpha','match':50},{'id':'10','title':'ALPHA','match':50}][::-1],
      [{'id':str(i),'seq':i,'title':'same','match':100} for i in (9007199254740993,9007199254740992)],
      [{'id':'2','title':'\U00010000','match':50},{'id':'1','title':'\ue000','match':50}],
      [{'id':'3','title':'Z','match':100},{'id':'2','title':'A','match':33},{'id':'1','title':'a','match':66}]
    ]
    applicant_groups=[
      [{'candidateId':str(i),'name':title,'match':50} for i,title in [(10,'ALEX'),(2,'alex')]],
      [{'candidateId':'2','name':'\U00010000','match':50},{'candidateId':'1','name':'\ue000','match':50}],
      [{'candidateId':str(i),'name':'same','match':66} for i in (9007199254740993,9007199254740992)]
    ]
    return {'cases':cases,'jobGroups':job_groups,'applicantGroups':applicant_groups}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='output/qa-supplement/parity.json')
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT))
    from recruiting.matching import score
    data=dataset()
    result=subprocess.run([os.environ.get('NODE_BINARY') or shutil.which('node') or 'node',
                           str(ROOT/'tests/frontend/match_bridge.cjs')],
                          input=json.dumps(data,ensure_ascii=True),encoding='utf-8',
                          capture_output=True,check=True,timeout=30)
    js=json.loads(result.stdout)
    failures=[]
    for index,case in enumerate(data['cases']):
        py=score(case['candidate'],case['required']); actual=js['scores'][index]
        record={'index':index,**case,'python':py,'javascript':actual}
        if py!=actual or ('expected' in case and (py!=case['expected'] or actual!=case['expected'])):
            failures.append(record)
        if 'pair' in case:
            partner=data['cases'][case['pair']]
            if py!=score(partner['candidate'],partner['required']):
                failures.append({**record,'reason':'Python metamorphic difference'})
            if actual!=js['scores'][case['pair']]:
                failures.append({**record,'reason':'JS metamorphic difference'})
    for name,key,id_key,title_key in [('jobs','jobGroups','id','title'),
                                      ('applicants','applicantGroups','candidateId','name')]:
        for index,group in enumerate(data[key]):
            expected=[row[id_key] for row in sorted(group,key=lambda x:(
                -x['match'],x[title_key].lower(),int(x[id_key])))]
            if js[name][index]!=expected:
                failures.append({'kind':name,'index':index,'input':group,
                                 'expected':expected,'javascript':js[name][index]})
    report={'seed':SEED,'score_cases':len(data['cases']),'job_sort_groups':len(data['jobGroups']),
            'applicant_sort_groups':len(data['applicantGroups']),'failures':failures,'inputs':data}
    output=ROOT/args.output; output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=True,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key not in ('inputs','failures')}))
    print('Failures:',len(failures))
    for failure in failures[:8]: print(json.dumps(failure,ensure_ascii=True))
    return 1 if failures else 0

if __name__=='__main__': sys.exit(main())
