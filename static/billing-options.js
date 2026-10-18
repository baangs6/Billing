(() => {
 const source=document.querySelector('#billing-data');if(!source)return;
 const data=JSON.parse(source.textContent),form=document.querySelector('#billing-form');
 const customer=document.querySelector('#customer'),walk=document.querySelector('#walk-in'),search=document.querySelector('#customer-search');
 const day=document.querySelector('#invoice-date'),due=document.querySelector('#due-date'),info=document.querySelector('#customer-info');
 const fmt=value=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(value/100);
 function showCustomer(resetDue=false){
  const state=document.querySelector('#walk-in-state'),stateLabel=document.querySelector('#walk-in-state-label');
  if(state){state.disabled=!walk?.checked;stateLabel.hidden=!walk?.checked;}
  const party=data.customers.find(row=>String(row.id)===customer.value);
  info.replaceChildren();
  if(party){
   const values=[['Billing',party.data.address],['Shipping',party.data.shipping_address],['State',party.data.state],['PIN',party.data.pin],['Phone',party.data.phone],['GSTIN',party.data.gstin],['PAN',party.data.pan],['Credit period',(party.data.credit_days||0)+' days'],['Previous balance',fmt(party.previous_balance||0)]];
   for(const [label,value] of values){if(value){const line=document.createElement('span');line.style.display='block';line.textContent=label+': '+value;info.append(line);}}
  }else if(walk?.checked){info.textContent='Anonymous walk-in sale. Full payment is required; no customer profile is created.';}
  if(day.value){due.min=day.value;if(resetDue||!due.value){const date=new Date(day.value+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+(walk?.checked?0:Number(party?.data.credit_days||0)));due.value=date.toISOString().slice(0,10);}}
 }
 customer.addEventListener('change',()=>showCustomer(true));day.addEventListener('change',()=>showCustomer(true));
 walk?.addEventListener('change',()=>{search.disabled=walk.checked;search.value=walk.checked?'Walk-in customer':'';customer.value=walk.checked?'walk-in':'';document.querySelector('#customer-results').hidden=true;customer.dispatchEvent(new Event('change'));});
 document.addEventListener('billing-customer-created',event=>data.customers.push(event.detail));
 if(walk?.checked){search.disabled=true;search.value='Walk-in customer';}showCustomer();
 const popup=document.querySelector('#bank-popup'),quick=document.querySelector('#quick-bank-form');
 document.querySelector('#open-bank-popup')?.addEventListener('click',()=>{popup.showModal();quick.elements.name.focus();});
 document.querySelector('#close-bank-popup')?.addEventListener('click',()=>popup.close());
 quick?.addEventListener('submit',async event=>{
  event.preventDefault();const button=quick.querySelector('[type=submit]'),error=document.querySelector('#quick-bank-error');button.disabled=true;error.hidden=true;
  try{
   const response=await fetch('/accounts',{method:'POST',body:new FormData(quick),headers:{Accept:'application/json'}});
   if(response.redirected||!(response.headers.get('content-type')||'').includes('application/json'))throw Error('Your session or account permissions changed. Sign in again, then retry.');
   const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to save bank account.');
   for(const select of [form.elements.ledger_account,form.elements.print_account]){if(select&&!Array.from(select.options).some(option=>option.value===String(result.account.id)))select.add(new Option(result.account.name,result.account.id));}
   form.elements.print_account.value=String(result.account.id);
   quick.reset();quick.elements.submission.value=Array.from(crypto.getRandomValues(new Uint8Array(32)),byte=>byte.toString(16).padStart(2,'0')).join('');
   popup.close();document.querySelector('#open-bank-popup').focus();
  }catch(reason){error.textContent=reason.message;error.hidden=false;}finally{button.disabled=false;}
 });
})();
