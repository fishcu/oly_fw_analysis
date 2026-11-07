import json
from pathlib import Path
root=Path(__file__).parent;out=root/'analysis/human-detection'
stages=[
 {'name':'Mode and learned data','status':'Static mapping recovered','finding':'Human is enum 6, selects resource index 5 and the sixth stored learned-data bank. The bank is 9,383,936 bytes.','detail':'Mode → index conversion → resource 0x800f → directory 10 → bank at logical 0x4c33f800. The accelerator data layout remains opaque; no compatible train/export pipeline exists yet.','source':'verified-evidence.json'},
 {'name':'Sensor to YC input','status':'Upstream gap','finding':'The trace starts at an image-submission routine. The full sensor readout and ISP preprocessing path is not reconstructed.','detail':'The public submission interface and queued worker are traced. We cannot yet establish exactly where image detail is discarded or whether higher-resolution crops are available to this engine.','source':'image-submit-upstream.asm'},
 {'name':'Input dimensions and execution','status':'Interface recovered; inference opaque','finding':'The aspect helper checks 640-wide input with heights 480, 360 or 340. DML execution is table-configured and completion-driven.','detail':'These are software-interface dimensions, not proven neural tensor sizes. Additional internal resizing and feature maps remain unknown. The worker uses CPU-labelled request and completion events.','source':'assembly/640-get_index_yc_aspect.asm'},
 {'name':'Raw result decoding and filters','status':'Selected paths traced','finding':'Fixed-size records contain masked geometry and a score-like field. Class/part remapping and separate region filters precede stabilization.','detail':'The result reader checks local group and entry bounds. A coordinate-bounds filter compacts accepted candidates; no single minimum-person-size switch was established. Score units are not verified probabilities.','source':'assembly/638-get_dml_result.asm'},
 {'name':'Temporal stabilization','status':'Concrete policy parameters found','finding':'Candidate matching, establishment and deletion use counters. Score and geometry influence the selected counter thresholds.','detail':'Registration choices include 6 and 10; loss choices include 2, 3, 4, 6 and 8. Geometry-derived comparisons use 500 and 37,200. UDF arithmetic and runtime cadence still need validation; these are not measured pixel cutoffs or milliseconds.','source':'assembly/664-regist_judge_update.asm'},
 {'name':'Human face/body/eye combination','status':'Dedicated branch traced','finding':'Mode 6 takes a specialized combination path: face registration, continuity matching, part association, body registration and eye selection.','detail':'Normal/vertical eye geometry and previous choice have separate routines. Several combined-list loops use eight slots; that is a local bound, not proof of a universal eight-person detection limit.','source':'assembly/708-face_combination.asm'},
 {'name':'Fallback and target selection','status':'Recovered with analysis repair','finding':'Secondary-part geometry can be promoted when a primary part is unavailable. Candidate eligibility and subject choice are separate from inference.','detail':'A false CALL_RETURN annotation hid this code in the original C export. It was repaired in a read-only analysis run. Exact part semantics still need mapping; adding generic body fallback may duplicate existing behavior.','source':'result-read-repaired.c'},
 {'name':'AF handoff and lens drive','status':'Application handoff traced; motor loop gap','finding':'The selected coordinates and state reach the focus subsystem. The complete phase-detection and lens-control algorithm is outside the recovered trace.','detail':'Coordinate export at 0x60864c75 is called from focus-side routine 0x609dbeb9. No focus-performance or detection-quality improvement has been tested on hardware.','source':'focus-handoff.asm'},
]
(out/'pipeline-assessment.json').write_text(json.dumps({'scope':'Static OM-3 1.1 trace; no camera tests','stages':stages},indent=2))
template='''import { useHostTheme, useState, useCanvasAction, Stack, H1, H2, Text, Divider } from "cursor/canvas";
const stages = __DATA__;
const base = "C:/Dev/OM3-research/";
export default function OM3HumanDetection() {
 const theme=useHostTheme(); const act=useCanvasAction();
 const [index,setIndex]=useState(0); const [percent,setPercent]=useState(1);
 const item=stages[index];
 const button={border:`1px solid ${theme.stroke.primary}`,borderRadius:4,padding:"8px 12px",background:theme.bg.editor,color:theme.text.primary,cursor:"pointer"};
 return <Stack gap={22} style={{padding:24,maxWidth:1120,lineHeight:1.6,color:theme.text.primary,background:theme.bg.editor}}>
  <div><Text>OM-3 1.1 · HUMAN DETECTION · STATIC TRACE · 31 OCTOBER 2026</Text><H1>Where a small person can disappear</H1>
   <p style={{fontSize:18,maxWidth:900}}>Human mode selects distinct learned data, processes a reduced-resolution image interface, stabilizes candidates, combines face/body/eye parts, then selects an autofocus target.</p>
   <button style={button} onClick={()=>act({type:"openFile",path:base+"HUMAN-DETECTION-ANALYSIS.md"})}>Open full analysis</button>
  </div>
  <section style={{background:theme.fill.tertiary,padding:18}}><H2>What was established</H2>
   <p><strong>Human-selected data bank extracted:</strong> 9,383,936 bytes. <strong>Interface geometry:</strong> 640 wide, with three checked heights. <strong>Policy code:</strong> score/geometry-dependent establishment and loss counters. <strong>Fallback:</strong> secondary-part promotion already exists.</p>
   <p>17 static checks pass. No inference was executed, no camera was connected and no modified firmware was installed. The neural graph, full ISP path and final lens-control loop remain unresolved.</p>
  </section>
  <section><H2>Follow the pipeline</H2><p>Choose a stage to inspect its evidence and the boundary of what we know.</p>
   <div style={{display:"grid",gridTemplateColumns:"minmax(210px,1fr) minmax(280px,2fr)",gap:24}}>
    <nav style={{display:"flex",flexDirection:"column",gap:8}}>{stages.map((s,i)=><button key={s.name} style={{...button,textAlign:"left",background:index===i?theme.fill.tertiary:theme.bg.editor,fontWeight:index===i?700:400}} aria-pressed={index===i} onClick={()=>setIndex(i)}>{i+1}. {s.name}</button>)}</nav>
    <article><Text>{item.status}</Text><H2>{item.name}</H2><p><strong>{item.finding}</strong></p><p>{item.detail}</p><button style={button} onClick={()=>act({type:"openFile",path:base+"analysis/human-detection/"+item.source})}>Open evidence</button></article>
   </div>
  </section><Divider/>
  <section><H2>Why reduced-resolution input matters</H2><p>This illustrates geometry at the recovered 640-wide interface. It is not a measured detection threshold or a statement of the network's internal tensor size.</p>
   <label>Face width as a share of submitted image width: <strong>{percent.toFixed(1)}%</strong><input aria-label="Face width percentage" type="range" min="0.2" max="10" step="0.1" value={percent} onChange={e=>setPercent(Number(e.target.value))} style={{display:"block",width:"100%",maxWidth:600,marginTop:12}}/></label>
   <p style={{fontSize:20}}>{(640*percent/100).toFixed(1)} pixels across at 640-wide input</p>
   <p style={{color:theme.text.secondary}}>A higher-detail crop could help only if the pipeline can supply it before detail is lost and the engine can process it. Enlarging an already reduced image does not restore missing detail.</p>
  </section>
  <section><H2>Which change would address which failure?</H2><dl style={{display:"grid",gridTemplateColumns:"minmax(170px,1fr) 2fr",gap:"12px 24px"}}>
   <dt><strong>No raw candidate</strong></dt><dd style={{margin:0}}>Investigate preprocessing, available crop detail and the learned detector. Downstream persistence cannot create detections.</dd>
   <dt><strong>Candidate disappears</strong></dt><dd style={{margin:0}}>Inspect bounds/class filtering, matching, registration and loss counters. More persistence can also preserve false targets.</dd>
   <dt><strong>Person exists but AF chooses elsewhere</strong></dt><dd style={{margin:0}}>Inspect target eligibility, priority, switching and selected-part fallback. Recognition and target selection are different stages.</dd>
  </dl></section>
  <p style={{color:theme.text.secondary}}>Recommended next evidence: synchronized raw, filtered, established, combined and selected results while subject size changes. Internal telemetry access and timing still need work.</p>
 </Stack>;
}
'''
(out/'OM3-human-detection.canvas.tsx.source').write_text(template.replace('__DATA__',json.dumps(stages)),encoding='utf-8')
print('Created pipeline assessment and interactive view source.')
