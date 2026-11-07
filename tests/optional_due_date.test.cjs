const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {runInNewContext}=require('node:vm');

test('customer and invoice-date changes preserve an optional due date',()=>{
 const events={};
 const customer={value:'1',addEventListener(_,fn){events.customer=fn}};
 const day={value:'2026-10-02',addEventListener(_,fn){events.day=fn}};
 const due={value:''},info={replaceChildren(){},append(){}};
 const data={customers:[{id:1,data:{state:'Tamil Nadu',credit_days:30},previous_balance:0}]};
 const elements={'#billing-data':{textContent:JSON.stringify(data)},'#billing-form':{},'#customer':customer,'#invoice-date':day,'#due-date':due,'#customer-info':info};
 const document={querySelector(selector){return elements[selector]||null},createElement(){return {style:{}}},addEventListener(){}};
 runInNewContext(readFileSync('static/billing-options.js','utf8'),{document});
 assert.equal(due.value,'');assert.equal(due.min,'2026-10-02');
 events.customer();assert.equal(due.value,'');
 day.value='2026-11-01';events.day();assert.equal(due.value,'');assert.equal(due.min,'2026-11-01');
 due.value='2026-12-01';events.customer();assert.equal(due.value,'2026-12-01');
 due.value='';events.day();assert.equal(due.value,'');
});
