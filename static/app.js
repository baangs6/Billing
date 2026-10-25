document.querySelectorAll('.confirm').forEach(form=>form.addEventListener('submit',e=>{if(!confirm(form.dataset.confirm))e.preventDefault()}));
document.querySelectorAll('[data-search]').forEach(input=>input.addEventListener('input',()=>filterTable(input.dataset.search)));
document.querySelectorAll('select[data-category]').forEach(input=>input.addEventListener('change',()=>filterTable(input.dataset.category)));
document.querySelector('select[name=direction]')?.addEventListener('change',function(){document.querySelector('input[name=quantity]').min=this.value==='set'?'0':'0.001'});
function filterTable(id){const search=document.querySelector(`[data-search="${id}"]`)?.value.toLowerCase()||'',category=document.querySelector(`select[data-category="${id}"]`)?.value||'';document.querySelectorAll(`#${id} tbody tr`).forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(search)||(category&&row.dataset.category!==category));}
document.querySelector('#print-invoice')?.addEventListener('click',function(){window.open(this.dataset.pdfUrl,'_blank','noopener')});
document.querySelector('#share-invoice')?.addEventListener('click',async function(){try{const response=await fetch(`/invoices/${this.dataset.id}/pdf`);if(!response.ok)throw Error('Could not load PDF');const file=new File([await response.blob()],this.dataset.filename||'Customer.pdf',{type:'application/pdf'});if(navigator.canShare?.({files:[file]}))await navigator.share({files:[file],title:this.dataset.number});else{const link=document.createElement('a');link.href=URL.createObjectURL(file);link.download=file.name;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);alert('PDF downloaded. Attach it to your email or messaging app.')}}catch(e){if(e.name!=='AbortError')alert(e.message)}});
const dataElement=document.querySelector('#billing-data');
function convertedUnitRate(paise,factor='1'){
 const [whole,fraction='']=String(factor).split('.'),scale=fraction.length+2;
 const digits=(BigInt(paise)*BigInt(whole+fraction)).toString().padStart(scale+1,'0');
 return (digits.slice(0,-scale)+'.'+digits.slice(-scale)).replace(/0+$/,'').replace(/\.$/,'');
}
if(dataElement){
 const data=JSON.parse(dataElement.textContent),rows=document.querySelector('#item-rows'),form=document.querySelector('#billing-form');
 const common=document.querySelector('#common-discount'),round=document.querySelector('#round-total'),manualRound=document.querySelector('#manual-round-off'),walkIn=document.querySelector('#walk-in'),charges=document.querySelector('#charge-rows');
 let items=data.items.map(i=>({...i,original_unit_choice:i.unit_choice,quantity:i.quantity/1000,rate:i.unit_rate_decimal??i.rate/100,mrp:i.mrp/100,discount:i.discount/100}));
 const fmt=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(n/100);
 // Preview arithmetic; server Decimal calculations are authoritative.
 const paise=n=>Math.round((Number(n)||0)*100+1e-7);
 function input(value,field,type='number'){const node=document.createElement('input');node.type=type;node.value=value;node.dataset.field=field;node.setAttribute('aria-label',field==='rate'?'Amount / rate':field);if(type==='number'){node.min=field==='quantity'?'0.001':'0';node.step=field==='quantity'?'0.001':field==='rate'&&data.units_enabled?'0.000000001':'0.01'}node.required=true;return node}
 function render(){rows.replaceChildren();charges?.replaceChildren();items.forEach((item,index)=>{const row=document.createElement('tr');row.dataset.index=index;const name=document.createElement('td'),details=document.createElement('div');details.className='billing-item-details';const nameInput=input(item.name,'name','text');nameInput.placeholder=item.is_charge?'Service / transport charge':'Item name';details.append(nameInput);name.append(details);const hsn=input(item.hsn||'','hsn','text');hsn.required=false;hsn.placeholder='HSN / SAC';details.append(hsn);if(item.product_id){const p=data.products.find(p=>p.id===Number(item.product_id));const small=document.createElement('small');small.textContent=`Available: ${p?.quantity/1000||0} ${p?.data.unit||''}`;details.append(small)}if(data.units_enabled&&!item.is_charge)unitControls(item,details);row.append(name);(common?['quantity','rate','mrp']:['quantity','rate','mrp','discount']).forEach(field=>{const td=document.createElement('td');if(item.is_charge&&field!=='rate')td.textContent='—';else td.append(input(item[field],field));row.append(td)});const tax=document.createElement('td'),select=document.createElement('select');select.dataset.field='gst';select.setAttribute('aria-label','GST rate');data.business.gst_rates.split(',').forEach(rate=>{const o=new Option(rate+'%',rate);o.selected=Number(rate)===Number(item.gst);select.add(o)});tax.append(select);row.append(tax);const total=document.createElement('td');total.className='row-total';row.append(total);const remove=document.createElement('td'),button=document.createElement('button');button.type='button';button.className='text-button danger';button.textContent='×';button.title='Remove item';button.setAttribute('aria-label',item.is_charge?'Remove additional charge':'Remove item');button.addEventListener('click',()=>{items.splice(index,1);render()});remove.append(button);row.append(remove);if(item.is_charge&&charges){const table=document.createElement('table'),body=document.createElement('tbody');table.className='summary-charge';row.querySelectorAll('td').forEach(td=>{if(td.textContent==='—')td.remove()});row.querySelector('[data-field=rate]').placeholder='Amount';row.querySelector('[data-field=name]').setAttribute('aria-label','Charge name');body.append(row);table.append(body);charges.append(table)}else rows.append(row);const labels=['Item / HSN','Quantity','Rate ₹','MRP ₹',...(common?[]:['Discount ₹']),'GST %','Amount','Remove'];row.querySelectorAll('td').forEach((cell,n)=>cell.dataset.label=labels[n])});document.querySelector('#billing-empty').hidden=items.length>0;calculate()}
 function unitControls(item,container){
  const product=data.products.find(p=>p.id===Number(item.product_id));
  function select(label,field,choices){const wrapper=document.createElement('label');wrapper.textContent=label;if(field==='pricing_mode')wrapper.dataset.gstControl='';const node=document.createElement('select');node.setAttribute('aria-label',label);choices.forEach(([value,text])=>node.add(new Option(text,value,false,value===(item[field]||choices[0][0]))));node.addEventListener('change',()=>{item[field]=node.value;if(field!=='pricing_mode'&&product){const factor=item.unit_choice==='ALT'?(item.original_unit_choice==='ALT'?item.unit_factor:product.data.alternate_factor):'1',price=item.price_tier==='WHOLESALE'&&product.data.wholesale_price!=null?product.data.wholesale_price:product.selling_price;item.rate=convertedUnitRate(price,factor);item.unit_rate_decimal=item.rate;if(field==='unit_choice')item.mrp=paise(convertedUnitRate(product.mrp,factor))/100;render()}else calculate()});wrapper.append(node);container.append(wrapper)}
  if(product?.data.alternate_unit||item.unit_choice==='ALT')select('Unit','unit_choice',[['PRIMARY',product?.data.unit||'Primary'],['ALT',item.original_unit_choice==='ALT'?item.unit:product?.data.alternate_unit||'Alternate']]);
  if(product?.data.wholesale_price!=null)select('Price tier','price_tier',[['RETAIL','Retail'],['WHOLESALE','Wholesale']]);
  select('Tax pricing','pricing_mode',[['EXCLUSIVE','Tax exclusive'],['INCLUSIVE','Tax inclusive']]);
 }
 const referralPoints=document.querySelector('#referral-points'),referralAmount=document.querySelector('#referral-amount');
 let referralCustomer=document.querySelector('#customer').value;
 function calculate(){
  let subtotal=0,discount=0,cgst=0,sgst=0,igst=0,chargeAmount=0;
  const customer=data.customers.find(c=>c.id===Number(document.querySelector('#customer').value))||(walkIn?.checked?{data:{state:document.querySelector('#walk-in-state')?.value||data.business.state}}:null);
  if(referralPoints){
   const selected=document.querySelector('#customer').value;
   if(selected!==referralCustomer){referralPoints.value='0';referralAmount.value='0';referralCustomer=selected;}
   const available=customer?.referral_available??customer?.data?.referral_points??0;
   document.querySelector('#referral-balance').textContent='Referral points: '+available+' available';
   referralPoints.setCustomValidity(Number(referralPoints.value)>available?'Not enough referral points.':'');
   if(data.business.referral_mode!=='MANUAL'&&document.activeElement===referralPoints)referralAmount.value=(Number(referralPoints.value)*(data.business.referral_value||0)/100).toFixed(2);
   if(!Number(referralPoints.value))referralAmount.value='0';
  }
  const referral=paise(referralAmount?.value||0);
  const interstate=customer&&customer.data.state.trim().toLowerCase()!==data.business.state.trim().toLowerCase(),gst=document.querySelector('#invoice-type').value==='GST';
  document.querySelector(`.billing-table th:nth-child(${common?5:6})`).hidden=!gst;
  const gross=items.map(i=>Math.round((i.unit_rate_decimal!==undefined?Number(i.rate)*100:paise(i.rate))*Number(i.quantity)+1e-7));
  const bases=gross.map((amount,n)=>gst&&items[n].pricing_mode==='INCLUSIVE'?Math.round(amount*100/(100+Number(items[n].gst))+1e-7):amount);
  if(common){
   const eligible=bases.reduce((sum,base,n)=>sum+(items[n].is_charge?0:base),0),amount=paise(common.value)+referral;
   common.setCustomValidity(amount>eligible?'Combined discounts cannot exceed the item subtotal.':'');
   referralAmount?.setCustomValidity(referral>eligible?'Referral discount cannot exceed the item subtotal.':'');
   let cumulative=0,allocated=0;
   items.forEach((i,n)=>{cumulative+=i.is_charge?0:bases[n];const share=eligible?Math.round(amount*cumulative/eligible+1e-7):0;i.discount=(share-allocated)/100;allocated=share});
  }
  items.forEach((i,n)=>{
   const row=form.querySelector(`[data-index="${n}"]`);row.querySelector('[data-field="gst"]').closest('td').hidden=!gst;
   const base=bases[n],disc=paise(i.discount),taxable=base-disc,rate=gst?Number(i.gst):0;
   let integrated=interstate?Math.round(taxable*rate/100+1e-7):0,half=interstate?0:Math.round(taxable*rate/200+1e-7);
   if(gst&&i.pricing_mode==='INCLUSIVE'&&!disc){const tax=gross[n]-base;integrated=interstate?tax:0;half=interstate?0:Math.round(tax/2);i.preview_sgst=interstate?0:tax-half}else i.preview_sgst=half;
   subtotal+=base;discount+=disc;cgst+=half;sgst+=i.preview_sgst;igst+=integrated;if(i.is_charge)chargeAmount+=base;
   row.querySelector('.row-total').textContent=fmt(taxable+integrated+half+i.preview_sgst);
  });
  if(manualRound){manualRound.disabled=Boolean(round?.checked);if(round?.checked)manualRound.value='0';}
  const raw=subtotal-discount+cgst+sgst+igst,adjustment=round?.checked?Math.round(raw/100)*100-raw:paise(manualRound?.value||0),total=raw+adjustment;
  if(walkIn?.checked&&!form.elements.id.value){document.querySelector('#received').value=(total/100).toFixed(2);document.querySelector('#received').readOnly=true;}else if(!form.elements.id.value){document.querySelector('#received').readOnly=false;}
  const values=[['Subtotal',subtotal-chargeAmount],...(common?[['Additional charges',chargeAmount]]:[]),['Discount',Math.max(0,discount-referral)],['Referral discount',referral],[gst?'Taxable amount':'Total amount',subtotal-discount],...(gst?(interstate?[['IGST',igst]]:[['CGST',cgst],['SGST',sgst]]):[]),...(round?[['Round off',adjustment]]:[]),['Grand total',total]];
  const container=document.querySelector('#calculation');container.replaceChildren();
  values.filter(([label,value])=>!['Round off','Referral discount'].includes(label)||value!==0).forEach(([label,value])=>{const div=document.createElement('div');div.className='summary-line'+(label==='Grand total'?' grand':'');const a=document.createElement('span'),b=document.createElement('strong');a.textContent=label;b.textContent=fmt(value);div.append(a,b);container.append(div)});
  document.querySelector('#balance').textContent=fmt(total-paise(document.querySelector('#received').value));
  const mobileTotal=document.querySelector('#mobile-invoice-total');if(mobileTotal)mobileTotal.textContent=fmt(total);
  const count=document.querySelector('#billing-item-count');if(count)count.textContent=items.filter(item=>!item.is_charge).length;

 }
 form.addEventListener('input',e=>{const index=e.target.closest('[data-index]')?.dataset.index,field=e.target.dataset.field;if(index!==undefined&&field){items[index][field]=e.target.value;if(field==='rate'&&data.units_enabled)items[index].unit_rate_decimal=e.target.value;}if(field||e.target===common||e.target===round||e.target===manualRound||e.target===referralPoints||e.target===referralAmount)calculate()});
 document.addEventListener('billing-product-created',event=>{data.products.push(event.detail)});
 document.addEventListener('billing-customer-created',event=>{data.customers.push(event.detail);calculate()});
 document.querySelector('#walk-in-state')?.addEventListener('input',calculate);
 document.querySelector('#customer').addEventListener('change',calculate);document.querySelector('#invoice-type').addEventListener('change',calculate);document.querySelector('#received').addEventListener('input',calculate);
 document.querySelector('#add-product').addEventListener('click',()=>{const p=data.products.find(p=>p.id===Number(document.querySelector('#product-picker').value));if(!p)return;items.push({product_id:p.id,name:p.name,quantity:1,rate:p.selling_price/100,mrp:p.mrp/100,discount:0,gst:p.data.gst,hsn:p.data.hsn,unit:p.data.unit,...(data.units_enabled?{unit_choice:'PRIMARY',unit_rate_decimal:String(p.selling_price/100),pricing_mode:p.data.pricing_mode||'EXCLUSIVE'}:{})});render()});
 document.querySelector('#additional-charge')?.addEventListener('click',()=>{items.push({is_charge:true,product_id:null,name:'',quantity:1,rate:0,mrp:0,discount:0,gst:data.business.gst_rates.split(',')[0],hsn:'',unit:'CHARGE'});render();(charges?.lastChild||rows.lastChild).querySelector('input').focus()});
 document.querySelector('#manual-item').addEventListener('click',()=>{items.push({product_id:null,name:'',quantity:1,rate:0,mrp:0,discount:0,gst:data.business.gst_rates.split(',')[0],hsn:'',unit:'PCS'});render();rows.lastChild.querySelector('input').focus()});
 form.addEventListener('submit',e=>{if(!document.querySelector('#customer').value){e.preventDefault();alert('Search and select a customer first.');document.querySelector('#customer-search').focus();return}if(!items.length){e.preventDefault();alert('Add at least one invoice item.');return}document.querySelector('#items-json').value=JSON.stringify(items);document.querySelectorAll('button[type=submit][form="billing-form"],#billing-form button[type=submit]').forEach(button=>button.disabled=true)});render();
}

document.querySelectorAll('.commerce-page form[method="post"]').forEach(form=>form.addEventListener('submit',event=>queueMicrotask(()=>{if(!event.defaultPrevented&&form.checkValidity()){const button=form.querySelector('button.primary');if(button&&!button.name){button.disabled=true;button.textContent='Saving…'}}})));
