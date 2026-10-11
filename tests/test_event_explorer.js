// Offline interaction and statistical checks; no dependencies or browser required.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const template=fs.readFileSync('scripts/event_explorer.html','utf8');
const script=template.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
class Element{
 constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.style={};this.value='';this.checked=false;this.selected=false;this.textContent='';}
 appendChild(e){this.children.push(e);if(this.tagName==='select'&&!this.value)this.value=e.value;return e;}
 replaceChildren(){this.children=[];this.value='';}
 get options(){return this.children;}
 get selectedOptions(){return this.children.filter(e=>e.selected);}
 addEventListener(k,f){this.listeners[k]=f;}
 querySelectorAll(tag){return this.children.flatMap(e=>[...(e.tagName===tag?[e]:[]),...e.querySelectorAll(tag)]);}
 getBoundingClientRect(){return{left:0,top:0,width:this.width,height:this.height};}
 getContext(){return new Proxy({},{get(_,key){if(['font','fillStyle','strokeStyle'].includes(key))return '';return(...values)=>{for(const v of values)if(typeof v==='number')assert.ok(Number.isFinite(v),'Non-finite canvas coordinate');};},set(){return true;}});}
}
const elements={};for(const id of [...template.matchAll(/id="([^"]+)"/g)].map(m=>m[1]))elements[id]=new Element(['frame','event','direction','thresholds','cross-threshold','alignment','horizon','lag'].includes(id)?'select':'div');
Object.assign(elements.frame,{value:'daily'});elements.direction.value='both';elements.alignment.value='calendar';elements.horizon.value='24';elements.distance.value='5';elements.lag.value='0';
const start=1791432000;
function points(offset=0,sign=1){return Array.from({length:30},(_,i)=>[start+(i+1)*300+offset,.2+sign*(i%5)*.02,82000,2,i<24?0:1,300]);}
function market(id,threshold,direction,selection='keep',offset=0){return{id,title:id,threshold,direction,frame:'daily',start:start+offset,end:start+86400+offset,window_basis:'calendar',review_boundary:false,hit:start+7500+offset,venue_yes:true,selection,points:points(offset,id==='B'?-1:1)};}
let data={schema_version:1,events:[{id:'1151848',title:'Day one',omitted:[],markets:[market('A',84000,'up'),market('B',85000,'up'),market('C',80000,'down'),market('tail',90000,'up','drop')]},{id:'next',title:'Day two',omitted:[],markets:[market('D',84000,'up','keep',86400)]}],inputs:{},script_hash:'fixture',template_hash:'fixture'};
if(process.argv[2]){const report=fs.readFileSync(process.argv[2],'utf8');data=JSON.parse(report.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1]);}
elements.data.textContent=JSON.stringify(data);
const context=vm.createContext({document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag)},window:{innerWidth:1400,innerHeight:900},console});
vm.runInContext(script,context);
const run=code=>vm.runInContext(code,context);
if(process.argv[2]){
 for(const frame of ['daily','weekly','monthly','all']){
  elements.frame.value=frame;run('refreshUniverse()');
  for(const hits of [false,true])for(const tails of [false,true]){
   elements.hits.checked=hits;elements.tails.checked=tails;
   elements.alignment.value='remaining';run('renderAll()');
   elements.alignment.value='calendar';run('renderAll()');
  }
 }
 elements.frame.value='daily';run('refreshUniverse()');
 for(const event of data.events.filter(e=>e.markets.some(m=>m.frame==='daily'))){elements.event.value=event.id;run('refreshTime()');elements.time.value=elements.time.min;run('renderTime()');elements.time.value=elements.time.max;run('renderTime()');}
 console.log('Full-dataset controls passed for daily/weekly/monthly/all frames, hit/tail toggles, both alignments and 32 daily-event slider endpoints.');process.exit(0);
}
assert.match(elements.summary.textContent,/4 markets/);
assert.equal(run('sample(allMarkets[0],allMarkets[0].points[0][0]-1)'),null,'No future bucket');
assert.equal(run('sample(allMarkets[0],allMarkets[0].points.at(-1)[0])'),null,'After-hit toggle excludes');
elements.hits.checked=true;run('renderAll()');assert.notEqual(run('sample(allMarkets[0],allMarkets[0].points.at(-1)[0])'),null);
elements.tails.checked=true;run('renderAll()');assert.match(elements.summary.textContent,/5 markets/);
elements.direction.value='up';run('renderAll()');assert.equal(elements['event-panels'].children.filter(e=>e.tagName==='h3').length,1);
elements.direction.value='both';elements.alignment.value='remaining';run('renderAll()');
assert.ok(elements['cross-panels'].querySelectorAll('canvas').length>0);
const before=run('regions.size');for(let i=0;i<10;i++){elements.time.value=start+(i+1)*300;run('renderTime()');}assert.equal(run('regions.size'),before,'No retained canvases on scrubbing');
const pointCanvas=elements['event-panels'].querySelectorAll('canvas')[0],region=run('regions.get(document.getElementById("event-panels").querySelectorAll("canvas")[0]).find(r=>r.time!==undefined)');
pointCanvas.listeners.click({clientX:region.x+.1,clientY:region.y+.1});assert.equal(Number(elements.time.value),region.time);
assert.equal(run('correlation(new Map([[1,1],[2,2]]),new Map([[1,1],[2,2]]),0).value'),null,'Minimum overlap gate');
assert.equal(run('correlation(new Map(Array.from({length:12},(_,i)=>[i,1])),new Map(Array.from({length:12},(_,i)=>[i,i])),0).value'),null,'Constant changes');
assert.ok(Math.abs(run('correlation(new Map(Array.from({length:12},(_,i)=>[i,i])),new Map(Array.from({length:12},(_,i)=>[i+300,-i])),300).value')+1)<1e-10,'Exact lag direction');
assert.equal(run('changes({...allMarkets[0],points:[allMarkets[0].points[0],allMarkets[0].points[2]]},true).size'),0,'No bridging missing buckets');
assert.equal(run('aggregate([{id:"x",event:"e",end:3600,points:[[300,.4,100,1,2,300]]}],24,5,false).used'),0,'Unknown paths excluded');
const a=run('aggregate([{id:"x",event:"e",end:3600,points:[[300,.4,100,1,0,300],[600,.6,100,1,0,300]]}],24,5,false)');assert.equal(a.used,2);assert.equal(a.bins.values().next().value.sum/2,.5);
elements.from.value='2030-01-01';elements.to.value='2030-01-02';run('refreshUniverse()');assert.equal(elements['event-panels'].querySelectorAll('canvas').length,0,'Empty range');
console.log('Event explorer controls, exact-time sampling, hit/tail filters, click/slider, lag/gaps, pooled counts and empty range passed.');
