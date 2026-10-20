const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
function clean(fetch=async()=>({ok:true,json:async()=>({documents:[]})})) {
  const context=vm.createContext({window:{},document:{addEventListener(){}},setTimeout,fetch});
  vm.runInContext(fs.readFileSync(path.join(root,'frontend/js/state.js'),'utf8'),context);
  return {context,state:context.window.state};
}
test('startup is empty without loading the sample fixture',()=>{
  const {state}=clean();
  assert.equal(state.project.isSampleProject,false);
  assert.equal(state.getDocuments().length,0);
  for (const key of ['conversation','savedFindings','issueReports','customFields','extractionRows']) assert.equal(state[key].length,0,key);
  assert.equal(state.selectedSources.size,0);assert.equal(state.expandedBundles.size,0);
  assert.equal(state.viewerFileId,null);assert.equal(state.isViewerOpen,false);assert.equal(state.extractStep,1);
});
test('sample analysis controllers remain inactive and require no sample DOM or data',()=>{
  const {context}=clean();
  for (const [file,name] of [['ask','Ask'],['extract','Extract'],['compare','Compare']]) {
    vm.runInContext(fs.readFileSync(path.join(root,`frontend/js/${file}.js`),'utf8'),context);
    assert.doesNotThrow(()=>vm.runInContext(`new ${name}Controller()`,context));
  }
});
test('restoring an empty catalog never adds a sample or a demonstration answer',async()=>{
  const {state}=clean();await state.loadUploadedDocuments();
  assert.equal(state.getDocuments().length,0);assert.equal(state.conversation.length,0);
  assert.throws(()=>state.openEvidence(1));
});
test('a real upload restores as the only source in a clean workspace',async()=>{
  const id='a'.repeat(64),doc={docId:id,filename:'My paper.pdf',totalPages:2,pageImageBase:`public/pages/${id}`,subdocuments:[{title:'My paper',startPage:1,endPage:2}]};
  const {state}=clean(async()=>({ok:true,json:async()=>({documents:[doc]})}));await state.loadUploadedDocuments();
  assert.equal(state.getDocuments().length,1);assert.equal(state.getDocuments()[0].filename,'My paper.pdf');
  state.openEvidence(99,null,doc.filename,null,id);assert.equal(state.viewerPage,2);
  assert.equal(state.extractionRows.length,0);assert.equal(state.conversation.length,0);
});
test('entry page has no automatic sample script, PDF image, or populated analysis tables',()=>{
  const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
  assert.doesNotMatch(html,/<script[^>]*src="js\/data.js"/);
  assert.doesNotMatch(html,/<img[^>]*src="public\/pages/);
  assert.doesNotMatch(html,/id="(?:compareTableBody|extractMatrixTable|conversationFeed)"/);
  assert.match(html,/id="btnFirstUpload"/);assert.match(html,/href="guide.html"/);
});
