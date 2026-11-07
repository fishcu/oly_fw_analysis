"""Repeatable offline OM-3 1.1 observations. Never accesses a camera."""
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
DECODED = ROOT / 'analysis' / 'decoded'
OUT = ROOT / 'analysis' / 'observations'
OUT.mkdir(exist_ok=True)
manifest = json.loads((DECODED / 'manifest.json').read_text())
inventory = json.loads((ROOT / 'reference/provenance/firmware-inventory.json').read_text())
reference = next(x for x in inventory if x['model'] == 'OM-3')
assert manifest['source_sha256'] == reference['sha256']
assert manifest['roundtrip_identical']
for block, expected in zip(manifest['blocks'], reference['components'], strict=True):
    assert block['decoded_sha256'] == expected['decoded_sha256']
    assert block['checksum_valid']

main = (DECODED / manifest['blocks'][0]['decoded_file']).read_bytes()
resource = (DECODED / manifest['blocks'][2]['decoded_file']).read_bytes()
xml_start = main.index(b'<?xml version="1.0"?><oishare>')
xml_end = main.index(b'</oishare>', xml_start) + len(b'</oishare>')
xml_bytes = main[xml_start:xml_end]
xml_root = ET.fromstring(xml_bytes)
(OUT/'oishare-description.xml').write_bytes(xml_bytes)
commands = [node.attrib['name'] for node in xml_root.findall('cgi')]
(OUT/'advertised-commands.json').write_text(json.dumps(dict(
    scope='Embedded description only; advertised names do not prove implementation or reachability',
    main_decoded_offset=hex(xml_start), version=xml_root.findtext('version'),
    supports=[node.attrib['func'] for node in xml_root.findall('support')],
    commands=commands), indent=2)+'\n')
base = 0x60021020  # Mapping from pinned upstream research, not header address.
table = main[0x606ba608-base:0x606ba608-base+3028]
assert hashlib.sha256(table).hexdigest() == 'a33d64bdb78ac41ba24ccbff820380f563211a095ac08a12a7c37a51b5c00531'
names_start = 0x28803f0
def name_at(key):
    return resource[names_start+52*key:names_start+52*(key+1)].split(b'\0')[0].decode('ascii')
assert name_at(0) == 'MODE_DRIVE' and name_at(111) == 'MODE_COLORTONE'
assert main[0x60405804-base:0x60405804-base+6] == b'\xfc\xdc'+struct.pack('<I', 0x605f6d90)
profiles = []
expected_sat = [[0]*12, [1,1,0,0,0,0,1,1,0,0,1,1], [4,4,4,4,4,3,4,4,4,4,4,4], [-4,0,0,0,-1,-1,-1,0,0,0,0,-4]]
expected_tone = [[0,0,0], [3,0,-3], [4,0,-4], [-3,0,3]]
for i, first in enumerate([928,940,952,964]):
    ids = list(range(first,first+12))
    labels = [name_at(k) for k in ids]
    assert labels == [f'MODE_COLOR_CREATOR_2_VIVID_SET{i+1}_{j+1}' for j in range(12)]
    read = lambda key, n: list(struct.unpack_from('<'+'i'*n, main, 0x605f6d90-base+key*4))
    sat, tone = read(first,12), read(976+i*3,3)
    assert sat == expected_sat[i] and tone == expected_tone[i]
    profiles.append(dict(profile=i+1, setting_ids=ids, setting_names=labels,
                         saturation=sat, tone_high_mid_low=tone))

categories = {
    'remote_and_transfer': r'\.cgi|<oishare|<caminfo|<command|<version',
    'color': r'COLOR_CREATOR|MONOCHROME|HUE|SATURATION|GRADATION',
    'system': r'Linux version|BusyBox|FreeRTOS|ITRON|ThreadX|VxWorks|assert|\.c:\d+',
    'update': r'firmware|firmup|bootloader|checksum',
}
counts = collections.Counter()
samples = {k: [] for k in categories}
patterns = {k: re.compile(v,re.I) for k,v in categories.items()}
with (DECODED/'strings.jsonl').open() as source, (OUT/'string_leads.jsonl').open('w') as dest:
    for line in source:
        record = json.loads(line)
        counts[str(record['block'])] += 1
        matched = [k for k,p in patterns.items() if p.search(record['text'])]
        if matched:
            dest.write(json.dumps(dict(record, categories=matched))+'\n')
            for k in matched:
                if len(samples[k]) < 25:
                    samples[k].append(record)
summary = dict(scope='Static bytes and strings only; no code execution, device access, or feature validation',
               source_sha256=manifest['source_sha256'], all_six_component_hashes_match_inventory=True,
               color_table_hash_matches=True, defaults_accessor_bytes_match=True,
               mapping_source='reference/tools/compare_color_generations.py at upstream commit 539fcf1fa9eda5fdef8ede4deeab94a4691d94c3',
               profiles=profiles, ascii_string_counts_by_block=dict(counts), samples=samples)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k != 'samples'}, indent=2))
