const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {runInNewContext}=require('node:vm');
const source=readFileSync('static/mobile-navigation.js','utf8');

test('menu collapses on phones, Escape returns focus, desktop restores navigation',()=>{
 const events={},toggleEvents={},media={matches:true,addEventListener(_,fn){this.change=fn}},sidebar={hidden:false};
 const toggle={setAttribute(key,value){this[key]=value},addEventListener(key,fn){toggleEvents[key]=fn},focus(){this.focused=true}};
 const navigation={querySelector(tag){return tag==='button'?toggle:sidebar},addEventListener(key,fn){events[key]=fn}};
 runInNewContext(source,{document:{querySelector(){return navigation},querySelectorAll(){return []}},window:{matchMedia(){return media},addEventListener(){}}});
 assert.equal(sidebar.hidden,true);assert.equal(toggle['aria-expanded'],'false');
 toggleEvents.click();assert.equal(sidebar.hidden,false);
 events.keydown({key:'Escape'});assert.equal(sidebar.hidden,true);assert.equal(toggle.focused,true);
 media.matches=false;media.change();assert.equal(sidebar.hidden,false);assert.equal(toggle['aria-expanded'],'true');
});

test('wide tables get keyboard access and hints; resizing clears obsolete hints',()=>{
 const attributes={},table={scrollWidth:800,clientWidth:320,dataset:{},setAttribute(k,v){attributes[k]=v},removeAttribute(k){delete attributes[k]}};
 let resize;
 runInNewContext(source,{document:{querySelector(){return null},querySelectorAll(){return [table]}},window:{addEventListener(_,fn){resize=fn}}});
 assert.equal(table.dataset.scrollable,'true');assert.equal(table.tabIndex,0);assert.equal(attributes.role,'region');assert.match(attributes['aria-label'],/arrow keys/);
 table.clientWidth=900;resize();
 assert.equal(table.dataset.scrollable,'false');assert.equal(table.tabIndex,-1);assert.equal(attributes.role,undefined);
});
