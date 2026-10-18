(() => {
 const rows=document.querySelector('#custom-header-rows'),add=document.querySelector('#add-custom-header');if(!rows)return;
 add.disabled=rows.children.length>=10;
 function remove(event){const button=event.target.closest('.remove-header');if(button){button.closest('.custom-header-row').remove();add.disabled=false;document.querySelector('#header-limit').textContent='';add.focus();}}
 rows.addEventListener('click',remove);
 add.addEventListener('click',()=>{
  if(rows.children.length>=10)return;
  const row=document.createElement('div');row.className='custom-header-row';
  for(const [name,label,max] of [['header_name','Header',50],['header_value','Value',300]]){const field=document.createElement('label'),input=document.createElement('input');field.textContent=label;input.name=name;input.maxLength=max;input.required=true;field.append(input);row.append(field);}
  const remove=document.createElement('button');remove.type='button';remove.className='secondary remove-header';remove.textContent='Remove';remove.setAttribute('aria-label','Remove custom header');row.append(remove);rows.append(row);row.querySelector('input').focus();
  add.disabled=rows.children.length>=10;if(add.disabled)document.querySelector('#header-limit').textContent='Maximum 10 custom headers.';
 });
 const gst=document.querySelector('[name=gst_registration]'),gstin=document.querySelector('[name=gstin]');
 function registration(){gstin.closest('label').hidden=gst.value==='UNREGISTERED';gstin.required=gst.value==='REGISTERED';}
 gst.addEventListener('change',registration);registration();
})();
