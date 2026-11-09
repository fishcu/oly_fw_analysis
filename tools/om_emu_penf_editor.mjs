// Copyright 2026 fishku (original contributions)
// SPDX-License-Identifier: Apache-2.0
// Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
// PEN-F editor probe for flatpanda/om-emu d24ff9dd20b98304541494d0199a5e6415eebdba.
// Exposes two existing UI_IN keys. The firmware handles their press/release;
// no direct GUI event, firmware change, device connection or download is made.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import {pathToFileURL} from 'node:url';

const args=process.argv.slice(2);
if(!args.length || args.includes('--help')) {
  console.log('node tools/om_emu_penf_editor.mjs OM_EMU_CHECKOUT --out NEW_DIR [--patch OVERLAY.json]');
  process.exit(args.includes('--help')?0:2);
}
const checkout=path.resolve(args.shift());
const options={};
while(args.length){
  const name=args.shift();
  if(!['--out','--patch'].includes(name)||!args.length||options[name])throw Error('Invalid or repeated option: '+name);
  options[name]=path.resolve(args.shift());
}
if(!options['--out'])throw Error('--out is required');
const out=options['--out'];
fs.mkdirSync(out); // Refuse an existing evidence directory.
process.env.OM_EMU_MODEL='E122';
const get=file=>import(pathToFileURL(path.join(checkout,'emu',file)));
const E=await get('checks/lib/env.mjs');
const {Player}=await get('src/lab/player.mjs');
const {PLAYER_PARSER}=await get('scenarios/session_replay.mjs');
const {CONTROLS,BY_ID,uiin_layout}=await get('src/lab/play.mjs');
const {pngRaw}=await get('host/server.mjs');
const fw=options['--patch']?E.patchedFirmware(E.readPatchFiles([options['--patch']])):null;
const rom=fw?.rom??E.loadImage(); // Upstream checks exact E122 input hashes.
const additions=[];
uiin_layout(rom).groups.forEach((group,g)=>group.entries.forEach(([byte,bit,code,type,polarity])=>{
  if(![0x122b,0x122c].includes(code))return;
  if(g!==1||byte!==1||bit!==(code===0x122b?2:3)||type!==2||polarity!==0)
    throw Error('Unexpected PEN-F input layout');
  if(CONTROLS.some(c=>c.uiin?.[3]===code))throw Error('Input already exposed: review this adapter against the new upstream revision');
  const c={id:`penf_${code.toString(16)}`,name:code===0x122b?'Picture-function left':'Picture-function right',
    kind:'key',uiin:[g,byte,bit,code,type,polarity],gui:[null,null,null]};
  CONTROLS.push(c);BY_ID.set(c.id,c);additions.push(c);
}));
if(additions.length!==2)throw Error('Expected both PEN-F picture-function keys');
const env={rom,resBlock:fw?.resBlock??E.loadBlock(),createHash:E.createHash,
  deflate:(b,l)=>new Uint8Array(zlib.deflateSync(b,{level:l})),
  inflate:b=>new Uint8Array(zlib.inflateSync(b)),wallClock:()=>performance.now()/1000};
const player=new Player({...PLAYER_PARSER,no_browser:true,idle:'off',a15:'on',out,
  no_wait_on_error:true,device:'tft'},env);
const report={model:'E122',additions,patch:fw?.summary??null,steps:[],frames:[],
  scope:'Synthetic cold session and input producer; native UI_IN/application/GUI. No reset boot, physical hardware, persistence or ISP-image validation.'};
function capture(name){
  const s=player.session;const [w,h,raw]=s.frame('boundary',true);
  fs.writeFileSync(path.join(out,name+'.png'),pngRaw(w,h,raw));
  const state=s.lab.state();const r={name,width:w,height:h,state:'0x'+state.toString(16),state_name:s.lab.state_names.get(state)};
  report.frames.push(r);console.log(name,r.state,r.state_name);
}
function key(id){for(const action of ['down','up'])report.steps.push(player.session.key(id,action));}
try{
  player.open_session();key('s1');capture('shooting');
  key('penf_122b');capture('color-editor');
  report.steps.push(player.session.dial_input('main',1));capture('main-plus');
  report.steps.push(player.session.dial_input('sub',1));capture('sub-plus');
  if(fw){for(let i=1;i<=3;i++){key('delete');capture('delete-'+i);}}
  key('penf_122c');capture('picture-function-right');
}catch(error){report.failure=error.stack;process.exitCode=1;console.error(error.stack);}
finally{fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2)+'\n');}
