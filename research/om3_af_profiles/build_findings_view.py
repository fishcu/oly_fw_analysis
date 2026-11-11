import json
from pathlib import Path

root = Path(__file__).parent
rows = [
('Recipe library / backup inspector','Host tool','Strong starting point','Advertised chunked settings backup and restore, names and state requests.','Backup format, checksums and camera-specific fields remain unmapped; selective COLOR import is unproven.','Build an offline inspector before editing or restoring.','analysis/observations/oishare-description.xml'),
('Desktop Wi-Fi remote','Host tool','Strong starting point','CGI frontend bridges shared memory and ISC; advertised live view, still/movie capture and exposure controls.','Pairing, state restrictions, allowed ranges and stream transport need measurements.','Specify the session state machine and parse normal responses.','analysis/decompiled-linux/var__www__fcgi-bin__isc_cgi/functions/0001119c.c'),
('Capture workflow sequencer','Host tool','Plausible extension','Remote capture and exposure commands plus near/far focus movements are advertised.','Focus movement repeatability and combinations of controls are untested. Built-in interval and bracketing already exist.','Map command timing and capture-state responses on stock firmware.','analysis/observations/oishare-description.xml'),
('Twelve-sector hue and lightness','Firmware research','Most promising patch direction','Twelve 24-byte records, per-sector gains and additional forwarded coefficients in the OM-3 color path.','Pixel meanings, safe ranges, opaque operations, persistence and preview/capture activation need verification.','Fix ABI and trace a single coefficient through initialization and output.','analysis/review/color-byte-evidence.json'),
('More internal recipe slots','Firmware research','Unproven implementation','Four existing COLOR banks and a large shared settings vocabulary.','Slot counts may affect allocation, serialization, menus and validation. External library is easier.','Map the profile serialization and every bank-count consumer.','analysis/review/setting-name-candidates.json'),
('Quick switching / button actions','Firmware research','Plausible extension','Existing settings and profile dispatch infrastructure provides search targets.','No complete button dispatcher or verified new assignable action path has been mapped.','Trace one existing assignable action end to end.','analysis/decompiled-main/functions/604037f9.c'),
('USB still tethering','Firmware research','Credible prior-work lead','Community OM-3 patch reports USB live view; exact-image USB mode work remains.','Not reproduced locally. Boot, recovery, USB handshake and application restrictions unresolved.','Independently trace the stock USB dispatch and compare guarded patch sites.','reference/docs/features/HISTORICAL_HACKS.md'),
('Logs and reconnect diagnostics','Host tool','Strong starting point','Camera log commands, ISC services and survival-inquiry heartbeat.','Additional telemetry, units and public reachability need proof.','Decode supported logs and distinguish camera errors from transport failures.','analysis/decompiled-linux/usr__bin__sccore/functions/00010d88.c'),
('Expanded webcam controls / resolution','Speculative extension','Pipeline investigation needed','Stock manual specifies 720p at 30p/25p and computer-control restrictions.','UVC descriptors, encoder path, bandwidth and state support are not mapped. Card recording modes do not prove USB capability.','Locate descriptors and trace a stock webcam-mode transition.','reference/OM3-official-manual.pdf'),
('Focus-stack controls / compatibility','Speculative extension','Pipeline investigation needed','Existing focus stacking and settings-label leads.','No verified OM-3 compatibility branch or full merge contract. Lens protocol and image quality matter.','Trace one supported stock stack from settings to capture.','analysis/review/setting-name-candidates.json'),
('High-resolution merge variants','Speculative extension','Algorithm identity unconfirmed','Boot-launched hhhr contains matrix and double-precision numerical operations plus IPC.','Name alone does not establish handheld-high-resolution processing or available headroom.','Map IPC callers and identify numerical input/output structures.','analysis/decompiled-linux/usr__bin__hhhr/functions/00010988.c'),
('Arbitrary 3D LUT / RAW video / new AI','Speculative extension','No demonstrated path','No complete implementation path established in this review.','Twelve-sector color is not arbitrary 3D LUT support. Sensor, ISP, memory and model requirements remain unknown.','Identify concrete hardware and pipeline support before proposing a feature.','FIRMWARE-ANALYSIS.md'),
]
features = [dict(zip(['name','category','assessment','evidence','limits','next','source'], r)) for r in rows]
(root/'analysis/review/feature-assessment.json').write_text(json.dumps({'firmware':'OM-3 1.1','scope':'Static evidence; no camera or modified-image tests','features':features},indent=2),encoding='utf-8')
template = '''import { useHostTheme, useState, useCanvasAction, Stack, H1, H2, Text, Divider } from "cursor/canvas";
const features = __DATA__;
const base = "C:/Dev/OM3-research/";
export default function OM3Findings() {
  const theme = useHostTheme();
  const act = useCanvasAction();
  const [filter, setFilter] = useState("All");
  const [selected, setSelected] = useState(features[0].name);
  const visible = features.filter(f => filter === "All" || f.category === filter);
  const item = visible.find(f => f.name === selected) || visible[0];
  const button = { padding: "8px 12px", border: `1px solid ${theme.stroke.primary}`, borderRadius: 4, color: theme.text.primary, background: theme.bg.editor, cursor: "pointer" };
  return <Stack gap={22} style={{ padding: 24, maxWidth: 1180, color: theme.text.primary, background: theme.bg.editor, lineHeight: 1.55 }}>
    <div><Text>OM SYSTEM OM-3 · FIRMWARE 1.1 · STATIC REVIEW · 31 OCTOBER 2026</Text><H1>What the firmware makes plausible</H1>
    <p style={{fontSize:18,maxWidth:880}}>The strongest leads are richer twelve-sector color controls, desktop remote workflows and a recipe library. The output is research evidence, not a tested replacement firmware.</p>
    <button style={button} onClick={() => act({type:"openFile",path:base+"FIRMWARE-ANALYSIS.md"})}>Open detailed report</button></div>
    <section style={{background:theme.fill.tertiary,padding:18}}><H2>Read the decompilation counts carefully</H2>
      <div style={{display:"flex",gap:32,flexWrap:"wrap"}}>{[["244","exported programs"],["187,179","C outputs"],["538","failed candidates"],["42,322","C outputs with diagnostics"]].map(([n,label])=><div key={label}><strong style={{fontSize:22}}>{n}</strong><div>{label}</div></div>)}</div>
      <p>All authoritative exports were scanned; selected paths were manually traced. Much of the main application has uncertain calling conventions, function boundaries and instruction semantics. Successful C generation does not mean verified behavior.</p>
      <button style={button} onClick={()=>act({type:"openFile",path:base+"analysis/review/corpus-review.json"})}>Inspect scope and quality evidence</button>
    </section>
    <section><H2>Architecture recovered from startup and call paths</H2>
      <ol><li><strong>Network frontend:</strong> lighttpd routes requests into CGI and file handlers.</li><li><strong>Shared-memory / ISC bridge:</strong> Linux packages requests and waits for application replies.</li><li><strong>Camera application:</strong> MN10300-family firmware owns substantial settings and image-pipeline control.</li><li><strong>Other environments:</strong> AArch64 Linux kernel, ARM userspace and Cortex-M battery/power-related firmware.</li></ol>
      <p style={{color:theme.text.secondary}}>This is a software boundary map. It does not establish separate physical chips or prove that every advertised request works in every camera state.</p>
    </section><Divider/>
    <section><H2>Explore feature opportunities</H2><p>Select a category and an idea to see its evidence, limitations and first useful experiment.</p>
      <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:18}}>{["All","Host tool","Firmware research","Speculative extension"].map(v=><button key={v} style={{...button,background:filter===v?theme.fill.tertiary:theme.bg.editor,fontWeight:filter===v?700:400}} aria-pressed={filter===v} onClick={()=>setFilter(v)}>{v}</button>)}</div>
      <div style={{display:"grid",gridTemplateColumns:"minmax(210px, 1fr) minmax(280px, 2fr)",gap:24}}>
        <nav style={{display:"flex",flexDirection:"column",gap:7}}>{visible.map(f=><button key={f.name} style={{...button,textAlign:"left",background:item.name===f.name?theme.fill.tertiary:theme.bg.editor,fontWeight:item.name===f.name?700:400}} aria-pressed={item.name===f.name} onClick={()=>setSelected(f.name)}>{f.name}</button>)}</nav>
        <article><Text>{item.category} · {item.assessment}</Text><H2>{item.name}</H2><p><strong>Evidence:</strong> {item.evidence}</p><p><strong>What remains uncertain:</strong> {item.limits}</p><p><strong>First useful step:</strong> {item.next}</p><button style={button} onClick={()=>act({type:"openFile",path:base+item.source})}>Open supporting artifact</button></article>
      </div>
    </section><Divider/>
    <section><H2>Recommended order</H2><p>Repair the focused main-code analysis → document settings and protocol structures → build offline recipe/backup tools → establish stock-camera baselines → investigate one color coefficient → consider USB and deeper processing changes.</p>
    <p style={{color:theme.text.secondary}}>Container decode/re-encode is verified. Modified-image boot acceptance, recovery, runtime feature behavior and hardware headroom are not. No camera was accessed or flashed during this review.</p></section>
  </Stack>;
}
'''
(root/'analysis/review/OM3-firmware-findings.canvas.tsx.source').write_text(template.replace('__DATA__',json.dumps(features)),encoding='utf-8')
print('Created structured assessments and standalone view source for 12 feature directions.')
