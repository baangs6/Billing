(() => {
 const source=document.querySelector('#billing-data');if(!source)return;
 const data=JSON.parse(source.textContent),products=data.products;
 const categories=[...new Set([...(data.categories||[]).map(c=>c.name||'Uncategorized'),...products.map(p=>p.data.category||'Uncategorized')].filter(Boolean))];
 const categorySearch=document.querySelector('#category-search'),productSearch=document.querySelector('#product-search');
 const categoryResults=document.querySelector('#category-results'),productResults=document.querySelector('#product-results');
 const selected=document.querySelector('#product-picker'),addButton=document.querySelector('#add-product');
 const popup=document.querySelector('#product-popup'),quick=document.querySelector('#quick-product-form');
 let category='';
 function clearProduct(){selected.value='';productSearch.value='';addButton.disabled=true;productResults.hidden=true;}
 function chooseCategory(value){category=value;categorySearch.value=value;categoryResults.hidden=true;clearProduct();productSearch.disabled=false;productSearch.placeholder='Search products in '+value+'…';productSearch.focus();}
 function chooseProduct(product){selected.value=product.id;productSearch.value=product.name;productResults.hidden=true;addButton.disabled=false;}
 function open(newCategory=false){
  quick.reset();quick.elements.category.value=newCategory?categorySearch.value.trim():category;
  quick.elements.name.value=newCategory?'':productSearch.value.trim();
  document.querySelector('#quick-product-error').hidden=true;categoryResults.hidden=true;productResults.hidden=true;
  popup.showModal();quick.elements.name.focus();
 }
 function button(label,handler,detail=''){const node=document.createElement('button');node.type='button';node.className='catalogue-result';const title=document.createElement('strong');title.textContent=label;node.append(title);if(detail){const small=document.createElement('small');small.textContent=detail;node.append(small)}node.addEventListener('click',handler);return node;}
 function showCategories(){
  const query=categorySearch.value.trim().toLowerCase();categoryResults.replaceChildren();
  const matches=categories.filter(c=>c.toLowerCase().includes(query)).sort().slice(0,25);
  matches.forEach(c=>categoryResults.append(button(c,()=>chooseCategory(c))));
  if(!matches.length){const message=document.createElement('p');message.textContent='No matching category found.';categoryResults.append(message)}
  if(popup){categoryResults.append(button('＋ Add '+(query?'“'+categorySearch.value.trim()+'” category & product':'category & product'),()=>open(true)))}
  categoryResults.hidden=false;
 }
 function showProducts(){
  if(!category)return;
  const query=productSearch.value.trim().toLowerCase();productResults.replaceChildren();
  const matches=products.filter(p=>p.active&&(p.data.category||'Uncategorized')===category&&[p.name,p.sku].join(' ').toLowerCase().includes(query)).slice(0,25);
  matches.forEach(p=>productResults.append(button(p.name,()=>chooseProduct(p),p.sku+' · '+new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(p.selling_price/100)+' · '+p.quantity/1000+' '+p.data.unit+' available')));
  if(!matches.length){const message=document.createElement('p');message.textContent='No matching products in '+category+'.';productResults.append(message)}
  if(popup){productResults.append(button('＋ Add '+(query?'“'+productSearch.value.trim()+'”':'new product')+' in '+category,()=>open()))}
  productResults.hidden=false;
 }
 categorySearch.addEventListener('focus',showCategories);
 categorySearch.addEventListener('input',()=>{category='';clearProduct();productSearch.disabled=true;productSearch.placeholder='Choose a category first…';showCategories()});
 productSearch.addEventListener('focus',showProducts);
 productSearch.addEventListener('input',()=>{selected.value='';addButton.disabled=true;showProducts()});
 for(const [search,results] of [[categorySearch,categoryResults],[productSearch,productResults]]){
  search.addEventListener('keydown',event=>{if(event.key==='Escape')results.hidden=true;if(event.key==='ArrowDown'){event.preventDefault();results.querySelector('button')?.focus()}if(event.key==='Enter'){event.preventDefault();results.querySelector('button')?.click()}});
 }
 document.addEventListener('click',event=>{if(!event.target.closest('.catalogue-lookup')){categoryResults.hidden=true;productResults.hidden=true}});
 document.querySelector('#close-product-popup')?.addEventListener('click',()=>popup.close());
 quick?.addEventListener('submit',async event=>{
  event.preventDefault();const save=quick.querySelector('[type=submit]'),error=document.querySelector('#quick-product-error'),status=document.querySelector('#quick-product-status');
  save.disabled=true;error.hidden=true;status.textContent=' Saving…';
  try{
   const response=await fetch('/billing/product',{method:'POST',body:new FormData(quick),headers:{Accept:'application/json'}});
   if(response.redirected)throw Error('Your session or subscription changed. Sign in again in another tab, then retry.');
   if(!(response.headers.get('content-type')||'').includes('application/json'))throw Error(response.status===403?'Your role does not allow adding products.':'Unable to save product. Refresh your session or try again.');
   const result=await response.json();if(!response.ok)throw Error(result.error||'Unable to save product.');
   products.push(result.product);if(!categories.includes(result.product.data.category))categories.push(result.product.data.category);
   document.dispatchEvent(new CustomEvent('billing-product-created',{detail:result.product}));
   popup.close();chooseCategory(result.product.data.category);chooseProduct(result.product);productResults.hidden=true;addButton.focus();
  }catch(reason){error.textContent=reason.message;error.hidden=false}
  finally{save.disabled=false;status.textContent=''}
 });
})();
