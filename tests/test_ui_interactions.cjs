const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
function environment() {
  const handlers = {};
  const fitButton = {};
  const context = vm.createContext({window:{}, document:{
    addEventListener(type,handler){handlers[type]=handler;},
    getElementById(){return fitButton;}
  },setTimeout,getComputedStyle(){return {paddingLeft:'12px',paddingRight:'12px'};}});
  for (const file of ['data.js','state.js','viewer.js','ask.js']) {
    vm.runInContext(fs.readFileSync(path.join(root,'frontend/js',file),'utf8'),context);
  }
  return {context,handlers,state:context.window.state,fitButton};
}
function escape() {return {key:'Escape',preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}};}
test('opening the app as a disk file redirects before application assets load',()=>{
  const html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  let destination;
  vm.runInNewContext(script,{location:{protocol:'file:',replace(url){destination=url;}}});
  assert.equal(destination,'http://localhost:8000/');
  destination=undefined;
  vm.runInNewContext(script,{location:{protocol:'http:',replace(url){destination=url;}}});
  assert.equal(destination,undefined);
});
test('Escape closes the calculation dialog without closing the source viewer',()=>{
  const {state,handlers}=environment();
  state.isViewerOpen=true;state.isCalcModalOpen=true;
  state.activeModal={id:'calcModalOverlay',classList:{contains(){return true;}}};
  const event=escape();handlers.keydown(event);
  assert.equal(state.isCalcModalOpen,false);assert.equal(state.isViewerOpen,true);
  assert.equal(event.stopped,true);assert.equal(event.prevented,true);
});
for (const id of ['uploadModalOverlay','reportModalOverlay']) {
  test(`Escape delegates ${id} closing and does not reach the viewer`,()=>{
    const {state,handlers}=environment();state.isViewerOpen=true;
    state.activeModal={id,classList:{contains(){return true;}}};let requested;
    state.subscribe((event,payload)=>{if(event==='modal_close_requested')requested=payload;});
    const event=escape();handlers.keydown(event);
    assert.equal(requested,id);assert.equal(event.stopped,true);assert.equal(state.isViewerOpen,true);
  });
}
test('zoom expands the scrollable page width instead of translating its left edge out of reach',()=>{
  const {context,state,fitButton}=environment();state.viewerZoom=2;
  const fake={stage:{style:{}},viewport:{clientWidth:321}};
  vm.runInContext('EvidenceViewerController.prototype.applyZoom',context).call(fake);
  assert.equal(fake.stage.style.width,'594px');assert.equal(fake.stage.style.transform,'none');
  assert.equal(fitButton.textContent,'200% · Fit');
});
test('Fit resets both horizontal and vertical scroll after zooming',()=>{
  const {context,state}=environment();state.viewerZoom=2;
  const fake={stage:{style:{}},viewport:{scrollTop:500,scrollLeft:200}};
  vm.runInContext('EvidenceViewerController.prototype.fitToWidth',context).call(fake);
  assert.equal(state.viewerZoom,1);assert.equal(fake.viewport.scrollTop,0);assert.equal(fake.viewport.scrollLeft,0);
});
test('feedback is recorded locally once and labeled with its session scope',()=>{
  const {context,state}=environment();const submit={disabled:false,textContent:''};
  const fake={reportReasonSelect:{value:'Wrong Value Extracted'},reportNotesInput:{value:'Test feedback'},activeReportTarget:{query:'Pressure?'},btnSubmitReport:submit,btnCancelReport:{textContent:'Cancel'}};
  const record=vm.runInContext('AskController.prototype.submitReport',context);
  record.call(fake);record.call(fake);
  assert.equal(state.issueReports.length,1);assert.equal(state.issueReports[0].notes,'Test feedback');
  assert.equal(submit.disabled,true);assert.match(submit.textContent,/session/);
});
