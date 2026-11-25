const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const context={window:{}};
const sourcePath=path.resolve(__dirname,'../../shared/match.js');
vm.runInNewContext(fs.readFileSync(sourcePath,'utf8'),context,{filename:sourcePath});
const {matchScore,hasSkill,compareJobs,compareApplicants}=context.window.MWMatch;
test('shared matcher: explicit whitespace, BOM and non-whitespace boundaries',()=>{
  for(const prefix of ['\uFEFF','\u0085','\u001C','\u00A0','\u2003','\u3000']){
    assert.equal(matchScore([prefix+'Python'+prefix],['python']),100);
    assert.equal(hasSkill([prefix+'Python'],prefix+'PYTHON'),true);
  }
  assert.equal(matchScore(['\u200BPython'],['Python']),0);
  assert.equal(matchScore(['e\u0301'],['é']),0);
});
test('shared matcher: course golden scores and flooring',()=>{
  for(const [c,r,expected] of [[['Python','SQL'],['Python','SQL'],100],
    [['Python'],['Python','SQL'],50],[['Rust'],['Python','SQL'],0],[[],[],100],
    [['a'],['a','b','c'],33],[['a','b'],['a','b','c'],66]]){
    assert.equal(matchScore(c,r),expected);
  }
});
test('shared sorter: code points and exact integer IDs',()=>{
  for(const comparator of [compareJobs,compareApplicants]){
    const rows=[{id:'9007199254740993',candidateId:'9007199254740993',seq:9007199254740993,title:'same',name:'same',match:50},
      {id:'9007199254740992',candidateId:'9007199254740992',seq:9007199254740992,title:'SAME',name:'SAME',match:50}];
    assert.equal(rows.sort(comparator)[0].id,'9007199254740992');
    const names=[{id:'2',candidateId:'2',title:'\u{10000}',name:'\u{10000}',match:50},
      {id:'1',candidateId:'1',title:'\uE000',name:'\uE000',match:50}];
    assert.equal(names.sort(comparator)[0].id,'1');
  }
});
