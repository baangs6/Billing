(() => {
 const source=document.querySelector('#billing-data'); if(!source)return;
 const customers=JSON.parse(source.textContent).customers;
 const search=document.querySelector('#customer-search'),selected=document.querySelector('#customer'),results=document.querySelector('#customer-results');
 const popup=document.querySelector('#customer-popup'),quick=document.querySelector('#quick-customer-form');
 function choose(customer){selected.value=customer.id;search.value=customer.name;results.hidden=true;selected.dispatchEvent(new Event('change'));}
 function open(){quick.reset();quick.elements.name.value=search.value.trim();document.querySelector('#quick-customer-error').hidden=true;popup.showModal();quick.elements.name.focus();}
 function show(){
  const query=search.value.trim().toLowerCase();results.replaceChildren();
  const matches=customers.filter(c=>[c.name,c.data.phone,c.data.email].join(' ').toLowerCase().includes(query)).slice(0,25);
  matches.forEach(c=>{const button=document.createElement('button');button.type='button';button.className='customer-result';const name=document.createElement('strong'),detail=document.createElement('small');name.textContent=c.name;detail.textContent=[c.data.phone,c.data.email,c.data.state].filter(Boolean).join(' · ');button.append(name,detail);button.addEventListener('click',()=>choose(c));results.append(button)});
  if(!matches.length){const empty=document.createElement('p');empty.textContent='No matching customer found.';results.append(empty)}
  if(popup){const add=document.createElement('button');add.type='button';add.className='customer-result add-result';add.textContent=query?'＋ Add “'+search.value.trim()+'” as a customer':'＋ Add new customer';add.addEventListener('click',open);results.append(add)}
  results.hidden=false;
 }
 search.addEventListener('input',()=>{selected.value='';selected.dispatchEvent(new Event('change'));show()});search.addEventListener('focus',show);
 search.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();results.querySelector('button')?.focus()}if(e.key==='Escape')results.hidden=true;if(e.key==='Enter'){e.preventDefault();results.querySelector('button')?.click()}});
 document.addEventListener('click',e=>{if(!e.target.closest('.customer-lookup'))results.hidden=true});
 document.querySelector('#open-customer-popup')?.addEventListener('click',open);document.querySelector('#close-customer-popup')?.addEventListener('click',()=>popup.close());
 quick?.addEventListener('submit',async e=>{
  e.preventDefault();const button=quick.querySelector('[type=submit]'),error=document.querySelector('#quick-customer-error'),status=document.querySelector('#quick-customer-status');
  button.disabled=true;error.hidden=true;status.textContent=' Saving…';
  try{
   const response=await fetch('/billing/customer',{method:'POST',body:new FormData(quick),headers:{Accept:'application/json'}});
   if(response.redirected)throw Error('Your session or subscription changed. Sign in again in another tab, then retry.');
   if(!(response.headers.get('content-type')||'').includes('application/json'))throw Error(response.status===403?'Your role does not allow adding customers.':'Unable to save. Refresh your session or try again.');
   const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to save customer.');
   customers.push(result.customer);document.dispatchEvent(new CustomEvent('billing-customer-created',{detail:result.customer}));choose(result.customer);popup.close();search.focus();results.hidden=true;
  }catch(reason){error.textContent=reason.message;error.hidden=false}
  finally{button.disabled=false;status.textContent=''}
 });
})();
