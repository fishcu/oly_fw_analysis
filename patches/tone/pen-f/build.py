#!/usr/bin/env python3
"""Build the bounded PEN-F five-point tone candidate without camera access."""
if not __debug__:
    raise RuntimeError('Firmware build validation requires assertions')

import argparse
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from oly_container import parse, reconstruct, replace_payload
import penf_tone_candidate as candidate
from penf_tone_graph_candidate import build_graph


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def changed_ranges(before, after):
    require(len(before) == len(after), 'Main image size changed')
    ranges = []
    start = None
    for index, (old, new) in enumerate(zip(before, after)):
        if old != new and start is None:
            start = index
        if old == new and start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(before)))
    rows = [dict(address=hex(candidate.BASE + start), bytes=end-start,
                 before_sha256=sha(before[start:end]), after_sha256=sha(after[start:end]))
            for start, end in ranges]
    validate_ranges(before, after, rows)
    return rows


def validate_ranges(before, after, rows):
    require(len(before) == len(after), 'Main image size changed')
    rebuilt = bytearray(before)
    previous_end = 0
    for row in rows:
        start = int(row['address'], 16) - candidate.BASE
        end = start + row['bytes']
        require(previous_end <= start < end <= len(before), 'Overlapping or invalid main patch ranges')
        require(sha(before[start:end]) == row['before_sha256'], 'Before hash mismatch')
        require(sha(after[start:end]) == row['after_sha256'], 'After hash mismatch')
        rebuilt[start:end] = after[start:end]
        previous_end = end
    require(rebuilt == after, 'Patch ranges do not account for every changed byte')


def pinned_hsl_builder():
    spec = importlib.util.spec_from_file_location('pinned_penf_hsl_build', ROOT / 'patches/hsl/pen-f/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(args):
    out = args.out.resolve()
    require(HERE != out and HERE not in out.parents, 'Keep output outside the patch source directory')
    spec = json.loads((ROOT / 'patches/hsl/pen-f/patch.json').read_text())
    stock = args.stock.read_bytes()
    require(sha(stock) == spec['stock_sha256'], 'Wrong stock firmware hash; requires full PEN-F 3101 container')
    blocks = parse(stock)
    require(len(blocks) == 4 and [b.kind for b in blocks[:2]] == [0x100, 0x101], 'Unexpected component order')
    require(not out.exists(), 'Output directory must be new')
    tools = {name: Path(getattr(args, name, None) or default).resolve()
             for name, default in candidate.TOOLS.items()}
    require(all(path.is_file() for path in tools.values()), 'Missing MN103 tool; provide --as, --ld, --objcopy, --objdump and --nm')
    out.mkdir(parents=True)
    with redirect_stdout(io.StringIO()):
        pinned_hsl_builder().build(SimpleNamespace(stock=args.stock, out=out/'hsl-reference',
            assembler=str(tools['assembler']), linker=str(tools['linker']), objcopy=str(tools['objcopy'])))
    baseline_path = out/'hsl-reference/install/DCOLYMP/E1229999.BIN'
    baseline_package = baseline_path.read_bytes()
    require(sha(baseline_package) == spec['package_sha256'], 'Pinned HSL package differs')
    baseline = parse(baseline_package)
    previous_tools = candidate.TOOLS
    try:
        candidate.TOOLS = tools
        graph = build_graph(out/'candidate', stock_main=blocks[0].payload)
    finally:
        candidate.TOOLS = previous_tools
    require(graph.base.reference == baseline[0].payload, 'Tone and container HSL baselines differ')
    spans = changed_ranges(baseline[0].payload, graph.image)
    package = reconstruct([replace_payload(baseline[0], graph.image), baseline[1]])
    verified = parse(package)
    require(len(verified) == 2, 'Unexpected candidate component count')
    require(verified[0].payload == graph.image, 'Main container round trip failed')
    require(verified[1].payload == baseline[1].payload and
            sha(verified[1].payload) == spec['osd_sha256'], 'Pinned HSL Value OSD was not preserved')
    require(all(a.header == b.header and a.trailer[:28] == b.trailer[:28]
                for a, b in zip(verified, blocks)), 'Container metadata changed')
    require(len(package) == len(baseline_package), 'Container size changed')
    require(reconstruct(verified) == package, 'Container byte round trip failed')
    install = out/'install/DCOLYMP/E1229999.BIN'
    install.parent.mkdir(parents=True)
    install.write_bytes(package)
    sources = [*HERE.glob('src/*.s'), HERE/'build.py',
               *(ROOT/'tools'/name for name in ('penf_tone_candidate.py',
                    'penf_tone_editor_candidate.py', 'penf_tone_graph_candidate.py'))]
    report = dict(status='offline candidate with bounded native verification; physical camera qualification pending',
        stock_sha256=sha(stock), pinned_hsl_package_sha256=sha(baseline_package),
        package_sha256=sha(package), package_bytes=len(package), main_sha256=sha(graph.image),
        osd_sha256=sha(verified[1].payload), hsl_value_osd_preserved=True,
        component_checksums_valid=True, container_metadata_unchanged=True,
        main_changed_bytes=sum(a != b for a, b in zip(baseline[0].payload, graph.image)),
        nonoverlapping_main_ranges=spans, camera_access=False,
        sources={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sources},
        tools={name:dict(sha256=sha(path.read_bytes()),
              version=subprocess.check_output([str(path),'--version'],text=True).splitlines()[0])
              for name,path in tools.items()},
        pinned_hsl_manifest='hsl-reference/build.json', placement_manifest='candidate/placement.json')
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    for flag,name in (('as','assembler'),('ld','linker'),('objcopy','objcopy'),('objdump','objdump'),('nm','nm')):
        parser.add_argument('--'+flag,dest=name,type=Path)
    return parser,parser.parse_args(argv)


def main():
    parser,args = arguments()
    try:
        report = build(args)
    except (ValueError,OSError,AssertionError,subprocess.CalledProcessError) as error:
        parser.exit(1,f'Build failed: {error}\n')
    print(json.dumps({k:report[k] for k in ('package_sha256','package_bytes','main_sha256',
        'hsl_value_osd_preserved','component_checksums_valid','container_metadata_unchanged')},indent=2))


if __name__ == '__main__':
    main()
