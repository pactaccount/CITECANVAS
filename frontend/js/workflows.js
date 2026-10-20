/* Real upload-scoped workflows. All document/model content is rendered as text. */
class WorkflowsController {
  constructor() {
    this.selected = new Set(); this.known = new Set(); this.busy = new Set();
    for (const [name,title,description] of [
      ['Ask','Ask a question','Ask a specific question, then open the source page to check the answer.'],
      ['Extract','Build a table','Enter up to four details, one per line. Check every AI result against its source.'],
      ['Compare','Compare files','Find exact text changes. Formatting and visual-only changes are not compared.']]) {
      const view=document.getElementById('view'+name);
      view.replaceChildren();
      const card=document.createElement('div');card.className='live-workflow';
      card.innerHTML=`<h1>${title}</h1><p>${description}</p><div class="workflow-sources"></div>${name==='Compare'?'':`<label class="cloud-choice"><input type="checkbox" checked> Use AI analysis for the selected PDFs. You can turn this off before running.</label><label class="workflow-label">${name==='Ask'?'Your question':'Details to collect'}<textarea class="input-text" rows="3" aria-label="${name==='Ask'?'Your question':'Details to collect'}" placeholder="${name==='Ask'?'What is the maximum operating pressure?':'Document title&#10;Reference number&#10;Maximum operating pressure'}"></textarea></label>`}<button class="btn btn-primary workflow-run">${name==='Ask'?'Ask':name==='Extract'?'Build table':'Compare files'}</button><p class="workflow-status" role="status"></p><div class="workflow-results" aria-live="polite"></div>`;
      view.append(card);this[name]={card,result:null};
      card.querySelector('.workflow-run').addEventListener('click',()=>this.run(name));
      card.querySelector('textarea')?.addEventListener('keydown',event=>{if(name==='Ask'&&event.key==='Enter'&&!event.shiftKey){event.preventDefault();this.run(name);}});
      card.querySelector('textarea')?.addEventListener('input',()=>this.invalidate(name));
    }
    const settings=document.querySelector('#settingsModalOverlay .modal-body');
    if(settings){
      const button=document.createElement('button');button.className='btn btn-secondary';button.textContent='Check analysis configuration';
      const output=document.createElement('p');output.setAttribute('role','status');
      button.addEventListener('click',async()=>{button.disabled=true;try{const r=await fetch('/api/health');if(!r.ok)throw Error('Health check failed.');const h=await r.json();output.textContent=`NVIDIA: ${h.modelConfigured?'configured':'missing key'} · Model: ${h.model} · Vector storage: ${h.qdrantConfigured?'Qdrant configured':'local fallback'}. Connection results: ${JSON.stringify(h.lastChecks)}. Configured does not mean a live inference check has completed.`;}catch(e){output.textContent=e.message;}finally{button.disabled=false;}});
      settings.append(button,output);
    }
    this.refresh();
    state.subscribe(event=>{if(['document_added','library_loaded','library_load_error'].includes(event))this.refresh();});
  }
  invalidate(name) {
    this[name].result=null;this[name].card.querySelector('.workflow-results').replaceChildren();
  }
  refresh() {
    const docs=state.getDocuments();
    docs.forEach(doc=>{if(!this.known.has(doc.fileId))this.selected.add(doc.fileId);this.known.add(doc.fileId);});
    for(const name of ['Ask','Extract','Compare']) {
      const card=this[name].card,container=card.querySelector('.workflow-sources');
      const prior=[...container.querySelectorAll('select')].map(s=>s.value);container.replaceChildren();
      if(name==='Compare') {
        for(let i=0;i<2;i++) {
          const label=document.createElement('label');label.className='workflow-label';label.textContent=i?'Second PDF':'First PDF';
          const select=document.createElement('select');select.className='select-input';select.setAttribute('aria-label',label.textContent);
          docs.forEach(d=>{const option=document.createElement('option');option.value=d.fileId;option.textContent=d.filename;select.append(option);});
          select.value=docs.some(d=>d.fileId===prior[i])?prior[i]:(docs[i]?.fileId||'');
          select.addEventListener('change',()=>this.invalidate(name));label.append(select);container.append(label);
        }
      } else {
        const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent=`Choose PDFs (${docs.length} available)`;details.append(summary);
        docs.forEach(doc=>{
          const label=document.createElement('label');label.className='source-choice';
          const input=document.createElement('input');input.type='checkbox';input.value=doc.fileId;input.checked=this.selected.has(doc.fileId);
          input.addEventListener('change',()=>{input.checked?this.selected.add(doc.fileId):this.selected.delete(doc.fileId);for(const task of ['Ask','Extract']){this[task].card.querySelectorAll('.workflow-sources input').forEach(box=>{if(box.value===doc.fileId)box.checked=input.checked;});this.invalidate(task);}});
          label.append(input,document.createTextNode(doc.filename));details.append(label);
        });container.append(details);
      }
      card.querySelector('.workflow-run').disabled=docs.length<(name==='Compare'?2:1)||this.busy.has(name);
      const status=card.querySelector('.workflow-status');
      if(!docs.length) status.textContent='Add a PDF in Documents to start.';
      else if(!this.busy.has(name) && status.textContent==='Add a PDF in Documents to start.') status.textContent='';
    }
  }
  citation(item) {
    const button=document.createElement('button');button.className='btn btn-secondary btn-sm';
    button.textContent=`${item.filename} · page ${item.page}`;
    button.addEventListener('click',()=>state.openEvidence(item.page,item.box||null,item.filename,button,item.fileId));return button;
  }
  async run(name) {
    if(this.busy.has(name))return;
    const card=this[name].card,status=card.querySelector('.workflow-status'),results=card.querySelector('.workflow-results');
    const sourceIds=name==='Compare'?[...card.querySelectorAll('select')].map(s=>s.value):[...this.selected];
    if(!sourceIds.length){status.textContent='Choose at least one PDF.';return;}
    if(name!=='Compare'&&!card.querySelector('.cloud-choice input').checked){status.textContent='Enable cloud analysis above to send the selected PDFs to NVIDIA.';return;}
    const body={sourceIds};if(name==='Ask')body.query=card.querySelector('textarea').value.trim();
    if(name==='Extract')body.fields=card.querySelector('textarea').value.split('\n').map(s=>s.trim()).filter(Boolean);
    if(name==='Ask'&&!body.query){status.textContent='Enter a question.';return;}
    if(name==='Extract'&&(!body.fields.length||body.fields.length>4)){status.textContent='Enter one to four fields, one per line.';return;}
    if(name==='Compare'&&(!sourceIds[0]||sourceIds[0]===sourceIds[1])){status.textContent='Choose two different PDFs.';return;}
    this.busy.add(name);this.invalidate(name);card.querySelector('.workflow-run').disabled=true;
    const locked=[...card.querySelectorAll('input,textarea,select')];locked.forEach(e=>e.disabled=true);
    status.textContent=name==='Compare'?'Comparing document text…':'Finding the most relevant pages…';
    const progressTimer=name==='Compare'?null:setTimeout(()=>{if(this.busy.has(name))status.textContent='Checking the selected pages with AI…';},1200);
    try {
      const response=await fetch('/api/'+name.toLowerCase(),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await response.json();if(!response.ok)throw Error(data.error||'Analysis failed.');
      this[name].result=data;status.textContent=data.message||data.method||'Complete.';
      if(name==='Ask') {
        if(data.answers.length>1){const heading=document.createElement('p');heading.textContent=`Verified findings from ${data.answers.length} source pages:`;results.append(heading);}
        for(const answer of data.answers){const section=document.createElement('section');const p=document.createElement('p');p.textContent=answer.displayAnswer||answer.answer;section.append(p,this.citation(answer));results.append(section);}
        if(data.checkedPages?.length){const p=document.createElement('p');p.textContent='Pages inspected: '+data.checkedPages.map(c=>`${c.filename} p.${c.page}`).join(', ');results.append(p);}
        if(data.warnings?.length){const p=document.createElement('p');p.textContent=data.warnings.join(' ');results.append(p);}
      } else if(name==='Extract') {
        const table=this.table(['PDF','Field','Value','Status','Source','Review']);
        for(const row of data.rows){const tr=document.createElement('tr');[row.filename,row.field,row.value||'Not found',row.status==='not_found'?'Not found':'Check source'].forEach(v=>this.cell(tr,v));
          const source=this.cell(tr,'');if(row.citation)source.append(this.citation(row.citation));
          const review=this.cell(tr,'');const accept=document.createElement('button');accept.className='btn btn-secondary btn-sm';accept.textContent='Accept for session';accept.disabled=!row.citation;
          accept.addEventListener('click',()=>{row.review='Accepted for session';accept.textContent='Accepted';accept.disabled=true;});review.append(accept);table.tBodies[0].append(tr);}
        results.append(table);this.exportButton(results,()=>[['PDF','Field','Value','Status','Review','Page'],...data.rows.map(r=>[r.filename,r.field,r.value,r.status,r.review,r.citation?.page||''])],'evid-extraction.csv');
      } else {
        if(!data.changes.length){const p=document.createElement('p');p.textContent='No text differences found.';results.append(p);}
        const table=this.table(['Change','First PDF','Second PDF']);
        for(const change of data.changes){const tr=document.createElement('tr');this.cell(tr,{replace:'Changed',insert:'Added',delete:'Removed'}[change.kind]||change.kind);
          const a=this.cell(tr,change.before||'—'),b=this.cell(tr,change.after||'—');if(change.sourceA)a.append(this.citation(change.sourceA));if(change.sourceB)b.append(this.citation(change.sourceB));table.tBodies[0].append(tr);}
        results.append(table);if(data.truncated){const p=document.createElement('p');p.textContent=`Showing 200 of ${data.total} change groups. Export includes the shown changes.`;results.append(p);}
        this.exportButton(results,()=>[['Change','First PDF text','Second PDF text'],...data.changes.map(c=>[c.kind,c.before,c.after])],'evid-comparison.csv');
      }
    } catch(error){status.textContent=error.message;this[name].result=null;}
    finally {if(progressTimer)clearTimeout(progressTimer);this.busy.delete(name);locked.forEach(e=>e.disabled=false);this.refresh();}
  }
  cell(tr,text){const td=document.createElement('td');td.textContent=text;tr.append(td);return td;}
  table(headers){const table=document.createElement('table');table.className='workflow-table';const head=table.createTHead().insertRow();headers.forEach(h=>{const th=document.createElement('th');th.textContent=h;head.append(th);});table.createTBody();return table;}
  exportButton(container,rows,filename){const button=document.createElement('button');button.className='btn btn-secondary';button.textContent='Export CSV';button.addEventListener('click',()=>{
    const csv=rows().map(row=>row.map(value=>{let v=String(value??'');if(/^[\s]*[=+@-]/.test(v))v="'"+v;return '"'+v.replaceAll('"','""')+'"';}).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });container.append(button);}
}
