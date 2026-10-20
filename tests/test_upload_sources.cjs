const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
function store(fetch = async () => ({ok:true,json:async()=>({documents:[]})})) {
  const context = vm.createContext({window:{}, document:{addEventListener(){}}, fetch, setTimeout});
  for (const file of ['data.js','state.js']) vm.runInContext(fs.readFileSync(path.join(root,'frontend/js',file),'utf8'),context);
  // These tests intentionally opt into the fixture; application startup does not.
  vm.runInContext(`state.project = JSON.parse(JSON.stringify(PHARMA_SAMPLE_PROJECT));
    state.viewerFileId = state.project.masterFile.fileId;
    state.selectedSources = new Set(state.project.subdocuments.map(s => s.subdocId));`, context);
  return context.window.state;
}
function record(id, pages=12) {
  return {docId:id.repeat(64), filename:'research-paper.pdf', totalPages:pages,
    pageImageBase:`public/pages/${id.repeat(64)}`,pageText:{1:`${id} research text`},
    subdocuments:[{subdocId:'subdoc_1',title:'Paper',startPage:1,endPage:pages}]};
}
test('different PDFs with the same filename remain independent sources and sections',()=>{
  const state=store(), a=state.registerUploadedDocument(record('a')),b=state.registerUploadedDocument(record('b',2));
  assert.equal(state.getDocuments().length,3);
  assert.notEqual(a.subdocuments[0].subdocId,b.subdocuments[0].subdocId);
  assert.equal(state.project.subdocuments.length,8);
  assert.equal(state.selectedSources.size,8);
});
test('same content is not counted twice, even after restoring saved uploads',async()=>{
  const data=record('a');const state=store(async()=>({ok:true,json:async()=>({documents:[data]})}));
  state.registerUploadedDocument(data);await state.loadUploadedDocuments();
  assert.equal(state.uploadedDocuments.length,1);
});
test('uploaded viewer bounds and citations cannot leak across files',()=>{
  const state=store(),a=state.registerUploadedDocument(record('a')),b=state.registerUploadedDocument(record('b',2));
  state.openEvidence(12,null,a.filename,null,a.fileId);assert.equal(state.viewerPage,12);
  state.setViewerPage(99);assert.equal(state.viewerPage,12);
  state.openEvidence(99,null,b.filename,null,b.fileId);assert.equal(state.viewerPage,2);
  state.openEvidence(2,{xmin:1,ymin:1,xmax:2,ymax:2},'sample citation');
  assert.equal(state.viewerFileId,state.project.masterFile.fileId);
  state.setViewerPage(3);assert.equal(state.viewerBox,null);
});
test('missing sources and incomplete server records fail rather than use sample pages',()=>{
  const state=store();assert.throws(()=>state.registerUploadedDocument({...record('a'),pageImageBase:null}));
  assert.throws(()=>state.openEvidence(1,null,'missing',null,'missing-file'));
  assert.equal(state.uploadedDocuments.length,0);
});
test('reviewing an uploaded section cannot modify a sample section',()=>{
  const state=store(),a=state.registerUploadedDocument(record('a'));
  state.saveBoundaryReview({...a.subdocuments[0],title:'Reviewed paper'});
  assert.equal(a.subdocuments[0].metadataStatus,'User-confirmed');
  assert.equal(state.project.subdocuments[0].metadataStatus,'Suggested (AI)');
});
test('failed restoration reports an error without fabricating an upload',async()=>{
  const state=store(async()=>{throw new Error('offline');});let error;
  state.subscribe((event,payload)=>{if(event==='library_load_error')error=payload;});
  await state.loadUploadedDocuments();assert.equal(error,'offline');assert.equal(state.uploadedDocuments.length,0);
});
