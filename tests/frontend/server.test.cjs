const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const sourcePath=path.resolve(__dirname,'../../shared/match.js'),context={window:{}};
vm.runInNewContext(fs.readFileSync(sourcePath,'utf8'),context,{filename:sourcePath});
const {fromServer,byServerRank}=context.window.MWMatch;
test('API projection keeps authoritative zero despite browser Unicode casing',()=>{
 const rows=fromServer([{id:'unicode',score:0,rank:1,title:'\u1c89'},
   {id:'empty',score:100,rank:0,title:'\u1c8a'}]);
 assert.deepEqual(Array.from(rows,r=>[r.id,r.match]),[['empty',100],['unicode',0]]);
});
test('API projection uses ranks without text or ID recomparison',()=>{
 const rows=fromServer([{id:'9007199254740993',score:50,rank:0,title:'\u{10000}'},
   {id:'9007199254740992',score:50,rank:1,title:'\uE000'}]);
 assert.equal(rows[0].id,'9007199254740993');
 assert.ok(byServerRank(rows[0],rows[1])<0);
});
test('API projection rejects missing or invalid facts rather than recalculating',()=>{
 for(const row of [{rank:0},{score:101,rank:0},{score:'0',rank:0},{score:0},{score:0,rank:-1}]){
   assert.throws(()=>fromServer([row]),/authoritative API/);
 }
 assert.throws(()=>byServerRank({},{rank:0}),/authoritative API/);
});
