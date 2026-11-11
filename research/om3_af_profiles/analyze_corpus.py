"""Corpus-wide triage. Text matches are research leads, not feature validation."""
import collections,csv,json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis/review'
OUT.mkdir(exist_ok=True)
index=json.loads((ROOT/'analysis/decompilation-index.json').read_text(encoding='utf-8'))
topics={
 'color':r'color.?creator|color.?profile|saturat|monochrom|white.?balance|gradation',
 'capture':r'pro.?capture|bracket|focus.?stack|interval|bulb|high.?res|pixel.?shift|HDR',
 'video':r'framerate|frame.?rate|movie|h264|h265|HEVC|bitrate|codec',
 'focus_lens':r'autofocus|focus|lens|tracking|subject.?detect',
 'remote':r'\.cgi|myset|remocon|liveview|wifi|bluetooth|ISC_send|ISC_receive',
 'power':r'battery|thermal|temperatur|overheat|watchdog|power.?supply',
 'storage':r'SD.?card|sdmmc|file.?system|FAT32|exfat|DCIM|\.ORF',
 'update':r'firmware|firmup|bootloader|checksum|signature|rollback',
 'ui':r'button|dial|touch.?screen|key.?assign|OSD|menu',
 'diagnostics':r'dbgterm|assert|cameralog|panic|syslog|diagnostic',
}
patterns={k:re.compile(v,re.I) for k,v in topics.items()}
quality={k:re.compile(v) for k,v in {
 'opaque_user_defined':r'\buser_defined(?:_imm)?\s*\(',
 'unrecovered_register_inputs':r'\b(?:in_[AD][0-9]|unaff_[A-Za-z0-9_]+)\b',
 'bad_spacebase':r'BADSPACEBASE|unaff_SP',
 'warning_markers':r'WARNING',
}.items()}
programs=[]
topic_counts=collections.Counter()
topic_leads={k:[] for k in topics}
with (OUT/'function-topic-leads.jsonl').open('w',encoding='utf-8') as leads:
 for program in index['programs']:
    folder=ROOT/program['export_directory']
    text=(folder/'all-functions.c').read_text(encoding='utf-8')
    with (folder/'functions.tsv').open(encoding='utf-8') as f:rows=list(csv.DictReader(f,delimiter='\t'))
    q=collections.Counter();t=collections.Counter();small=0;named=0
    markers=list(re.finditer(r'^/\* Address ([0-9a-f]+);',text,re.M))
    assert len(markers)==len(rows)
    for i,(marker,row) in enumerate(zip(markers,rows)):
        body=text[marker.start():markers[i+1].start() if i+1<len(markers) else len(text)]
        assert marker[1]==row['address']
        if int(row['body_bytes'])<=16:small+=1
        if not re.match(r'^(?:FUN_|thunk_FUN_|switchD_)',row['name']):named+=1
        for k,p in quality.items():
            if p.search(body):q[k]+=1
        matches=[k for k,p in patterns.items() if p.search(body)]
        if not matches:continue
        for k in matches:t[k]+=1;topic_counts[k]+=1
        record=dict(program=program['export_directory'],address=row['address'],name=row['name'],
                    topics=matches,body_bytes=int(row['body_bytes']),completed=row['decompiled']=='true',
                    warnings=int(row['warning_markers']),file=str((folder/row['file']).relative_to(ROOT)))
        leads.write(json.dumps(record)+'\n')
        camera_specific='decompiled-main' in str(folder) or 'decompiled-scpu' in str(folder) or any(
            x in folder.name for x in ['isc','wifi','sccore','blebridge','hhhr','dbgterm'])
        if camera_specific:
            literals=re.findall(r'"([^"\n]{5,200})"',body)
            for k in matches:
                evidence=[s for s in literals if patterns[k].search(s)]
                if evidence and len(topic_leads[k])<35:topic_leads[k].append(dict(record,literals=evidence[:5]))
    programs.append(dict(directory=program['export_directory'],functions=len(rows),
        completed=program['decompiled'],failed=program['failed'],functions_le_16_bytes=small,
        names_not_matching_generic_prefix=named,quality_flags=dict(q),topic_matches=dict(t),c_bytes=len(text.encode())))

# Full ASCII string corpus also covers resources not represented in generated C.
string_topics=collections.Counter();string_leads={k:[] for k in topics}
with (ROOT/'analysis/decoded/strings.jsonl').open(encoding='utf-8') as f:
 for line in f:
    row=json.loads(line)
    for k,p in patterns.items():
        if p.search(row['text']):
            string_topics[k]+=1
            if len(string_leads[k])<35:string_leads[k].append(row)
result=dict(scope='All 244 authoritative exported programs scanned; bounded manual traces needed for behavior',
    programs=programs,functions=sum(p['functions'] for p in programs),topic_function_matches=dict(topic_counts),
    string_topic_matches=dict(string_topics),topic_leads=topic_leads,string_leads=string_leads)
(OUT/'corpus-review.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(programs=len(programs),functions=result['functions'],
    main=next(p for p in programs if p['directory'].endswith('decompiled-main')),
    topic_function_matches=dict(topic_counts)),indent=2))
