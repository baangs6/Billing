document.querySelectorAll('.referrer-picker').forEach(picker=>{
 const search=picker.querySelector('input'),select=picker.querySelector('select');
 search.addEventListener('input',()=>{const query=search.value.trim().toLowerCase();for(const option of select.options)option.hidden=Boolean(option.value&&!option.textContent.toLowerCase().includes(query));});
 document.addEventListener('billing-customer-created',event=>{const c=event.detail;select.add(new Option(c.name+' · '+(c.data.phone||'')+' · #'+c.id,c.id));});
});
