"""Record class-aware backend observations and validate bounded ROM decodes."""
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / 'analysis/decoded/00_0100_50000020.decoded.bin'
BASE = 0x60021020


def save(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def validate_windows(directory=None):
    directory = directory or ROOT / 'analysis/review/backend-start'
    payload = PAYLOAD.read_bytes()
    records = []
    for row in (directory / 'windows.tsv').read_text(encoding='utf-8-sig').splitlines():
        start, end, label = row.split('\t')
        start, end = int(start, 16), int(end, 16)
        expected, instructions = start, 0
        for line in (directory / f'{label}.asm').read_text(encoding='utf-8').splitlines():
            if line.startswith(';'):
                continue
            address, raw, *_ = line.split('\t')
            address, data = int(address, 16), bytes.fromhex(raw)
            if address != expected or not data:
                raise ValueError(f'Noncontiguous decode in {label}: {line}')
            if payload[address-BASE:address-BASE+len(data)] != data:
                raise ValueError(f'ROM byte mismatch in {label}: {line}')
            expected += len(data)
            instructions += 1
        if not end <= expected < end + 16:
            raise ValueError(f'Window extent mismatch: {label}')
        records.append({'directory': directory.relative_to(ROOT).as_posix(), 'label': label, 'start': f'{start:08x}',
                        'requested_end_exclusive': f'{end:08x}',
                        'decoded_end_exclusive': f'{expected:08x}',
                        'instructions': instructions})
    return records


def record(run, probe):
    observation_file = next((run / name for name in ('backend-start-observations.txt', 'queue10-exchange-trace.txt', 'task10-trace.txt', 'status-property-results.txt', 'missing-device-trace.txt', 'property-failure-trace.txt', 'registered-device-trace.txt', 'heap-reuse-trace.txt', 'af-worker-startup-trace.txt') if (run / name).exists()), None)
    if observation_file is None:
        raise ValueError('No completed observation trace found')
    lines = observation_file.read_text(encoding='utf-8').splitlines()
    scope_file = next((run / name for name in ('backend-start-outcome.txt', 'queue10-exchange-outcome.txt', 'task10-outcome.txt', 'status-property-results.txt', 'missing-device-outcome.txt', 'property-failure-outcome.txt', 'registered-device-outcome.txt', 'heap-reuse-outcome.txt', 'af-worker-startup-outcome.txt') if (run / name).exists()), None)
    if scope_file is None:
        raise ValueError('No probe outcome found')
    snapshots = []
    for line in lines:
        if not line.startswith('SNAPSHOT obj=') or ' data=' not in line:
            continue
        data = bytes.fromhex(line.split(' data=', 1)[1])
        address = int(line.split('obj=', 1)[1][:8], 16)
        word = lambda off: struct.unpack_from('<I', data, off)[0]
        result = {'object': f'{address:08x}', 'vtable': f'{word(0):08x}'}
        if word(0) == 0x60f10f50:
            result.update(layout='capture public backend', coarse_state=word(0xfc),
                          active_state=word(0x100), start_observer_count=word(0xa8),
                          current_event=f'{word(0x68):08x}')
        elif word(0) in (0x60ebc334, 0x60ebda38):
            result.update(layout='simple child component', lifecycle=word(0xb0),
                          active_state=word(0xb4), parent=f'{word(0xa8):08x}')
        else:
            result.update(layout='unclassified; do not infer lifecycle offsets')
        snapshots.append(result)
    window_dirs = [ROOT / 'analysis/review/backend-start']
    for name in ('mode-sequence', 'mode-key-init', 'constructor-group', 'queue10', 'startup-singleton', 'device-dispatch', 'property-init', 'device-registry', 'static-os'):
        if (ROOT / 'analysis/review' / name / 'windows.tsv').exists():
            window_dirs.append(ROOT / 'analysis/review' / name)
    task_trace = run / 'capture-connection-trace.txt'
    task_lines = task_trace.read_text(encoding='utf-8').splitlines() if task_trace.exists() else lines
    button_file = run / 'mode-sequence-button-results.txt'
    observations = {
        'scope': scope_file.read_text(encoding='utf-8').strip(),
        'native_queue10_exchange': [s for s in task_lines if s.startswith(('TASK10:', 'REPLAY-INPUT:', 'NATIVE-EXCHANGE-RESULT:'))],
        'constructor_group_proof': (run / 'constructor-group-proof.txt').read_text(encoding='utf-8') if (run / 'constructor-group-proof.txt').exists() else None,
        'original_trace_label_correction': 'life/state/parent labels in generic state() are valid only for the simple-component layout; use the class-aware snapshots below for the public backend.',
        'line_counts': dict(Counter(s.split(' ', 1)[0] for s in lines)),
        'snapshots': snapshots,
        'backend_events': [s for s in lines if s.startswith('BACKEND-EVENT')],
        'backend_state_path': [s for s in lines if s.startswith('BACKEND-STATE')],
        'public_start_observer_activity': [s for s in lines if s.startswith('OBSERVER ') and 'obj=62b71814 ' in s],
        'mode_input_trace': [s for s in lines if s.startswith(('STOCK-CONNECTION', 'MODE-SEQUENCE'))],
        'protocol_initialization': [s for s in lines if s.startswith(('PROTOCOL-INIT', 'SUBTYPE-ROUTING', 'SUBTYPE-CLASS-RESULT', 'CONSTRUCTOR-GROUP'))],
        'router_snapshot': [s for s in lines if s.startswith('SNAPSHOT key269')],
        'button_results': button_file.read_text(encoding='utf-8').splitlines() if button_file.exists() else [],
        'bounded_decodes': [row for directory in window_dirs for row in validate_windows(directory)],
        'limitations': ['Conditional reset/OS/device fixtures; not normal boot.',
                        'See button_results for guarded original-button attempts using inherited context/resident fixtures.' if button_file.exists() else 'No original buttons run by this connection observation probe.',
                        'No camera, AF acquisition or installable firmware safety proof.'],
    }
    save(run / 'backend-class-aware-summary.json', observations)
    # Preserve the actual inheritance chain, including the input fixture, instead
    # of assuming current files will remain unchanged after the next experiment.
    sources, name = [], probe
    while name.startswith('OM3'):
        path = ROOT / 'scripts' / f'{name}.java'
        sources.append(path)
        match = re.search(r'public class\s+\w+\s+extends\s+(\w+)', path.read_text(encoding='utf-8'))
        if match is None:
            break
        name = match.group(1)
    if probe in ('OM3Queue10StatusIndependentProof', 'OM3Queue10MissingDeviceProof', 'OM3PropertyFailurePathProof', 'OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        sources.append(ROOT / 'scripts/OM3StatusPropertyProbe.java')
    if probe in ('OM3Queue10MissingDeviceProof', 'OM3PropertyFailurePathProof', 'OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        sources.append(ROOT / 'scripts/OM3MissingDeviceCallbackProbe.java')
    if probe in ('OM3PropertyFailurePathProof', 'OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        sources.append(ROOT / 'scripts/OM3PropertyFailurePathProbe.java')
    if probe in ('OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        sources.append(ROOT / 'scripts/OM3ReusingHeapProbe.java')
    if probe == 'OM3CompleteStaticOSConsumerProof':
        sources.append(ROOT / 'scripts/OM3AFWorkerStartupProbe.java')
    source_dir = run / 'source-snapshot'
    source_dir.mkdir(exist_ok=True)
    for source in sources + [Path(__file__)]:
        target = source_dir / source.name
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError(f'Refusing to overwrite archived source {target}')
        target.write_bytes(source.read_bytes())
    files = [p for p in run.rglob('*') if p.is_file() and p.name != 'class-aware-evidence-manifest.json']
    files += [PAYLOAD]
    if probe in ('OM3Queue10StatusIndependentProof', 'OM3Queue10MissingDeviceProof', 'OM3PropertyFailurePathProof', 'OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        dependency = ROOT / 'analysis/button-af/readiness/status-property1'
        files += [p for p in dependency.rglob('*') if p.is_file()]
    if probe in ('OM3Queue10MissingDeviceProof', 'OM3PropertyFailurePathProof', 'OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        files += [p for p in (ROOT / 'analysis/button-af/readiness/missing-device3').rglob('*') if p.is_file()]
    if probe in ('OM3PropertyFailurePathProof', 'OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        files += [p for p in (ROOT / 'analysis/button-af/readiness/property-failure4').rglob('*') if p.is_file()]
    if probe in ('OM3ReusingHeapProof', 'OM3OriginalButtonMatrixProof', 'OM3OriginalButtonConsumerProof', 'OM3CompleteStaticOSConsumerProof'):
        files += [p for p in (ROOT / 'analysis/button-af/readiness/heap-reuse2').rglob('*') if p.is_file()]
    if probe == 'OM3CompleteStaticOSConsumerProof':
        files += [p for p in (ROOT / 'analysis/button-af/readiness/af-worker-startup1').rglob('*') if p.is_file()]
    for windows in window_dirs:
        files += [windows / 'windows.tsv'] + list(windows.glob('*.asm')) + list(windows.glob('*.json'))
    lang = ROOT / 'tooling/ghidra_12.2_PUBLIC/Ghidra/Extensions/MN10300/data/languages'
    files += [lang / 'mn103_base.sinc', lang / 'mn103_mn10300.sla']
    # Freeze mutable static analyses and prerequisite runs inside this run.
    # Payload stays content-checked at its immutable catalog path.
    frozen = []
    for source in files:
        if source.is_relative_to(run) or source == PAYLOAD:
            frozen.append(source)
            continue
        target = run / 'evidence-snapshot' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError(f'Refusing to overwrite archived evidence {target}')
        target.write_bytes(source.read_bytes())
        frozen.append(target)
    files = frozen
    save(run / 'class-aware-evidence-manifest.json', {
        'probe': probe, 'scope': observations['scope'],
        'sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})
    print(json.dumps({k: v for k, v in observations.items() if k != 'bounded_decodes'}, indent=2))
    print(f'Validated {len(observations["bounded_decodes"])} bounded windows against decoded stock bytes.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--probe', required=True)
    args = parser.parse_args()
    record(args.run.resolve(), args.probe)
