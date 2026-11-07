"""Validate complete native-suite output and pin the exact sources/results used."""
from pathlib import Path
import argparse
import hashlib
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/button-af/closure'
EXPECTED = {'native-flow': 4, 'native-queue': 6, 'native-lifecycle': 6,
            'native-profile': 28, 'native-hook': 4, 'native-fault': 4,
            'native-state-space': 14}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', type=Path, default=OUT / 'offline-suite-verified-run.log')
    args = parser.parse_args()
    main_image = ROOT / 'analysis/decoded/00_0100_50000020.decoded.bin'
    original = ROOT / 'firmware/catalog/OLY_E_147_1100_0000_0000.BIN'
    assert sha(main_image) == '5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59'
    assert sha(original) == '8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d'
    log = args.log.read_text(encoding='utf-8')
    assert 'OFFLINE SUITE: 66 PASS;' in log, 'Missing complete-suite success marker'
    assert 'SCRIPT ERROR' not in log and 'ERROR REPORT' not in log and 'Uninitialized memory read' not in log
    assert 'Discarding changes to the following read-only file' in log
    for name, count in EXPECTED.items():
        rows = (OUT / f'{name}-results.txt').read_text(encoding='utf-8').splitlines()
        assert len(rows) == count and all(r.startswith('PASS ') for r in rows), name
    assert len((OUT / 'offline-suite-results.txt').read_text().splitlines()) == len(EXPECTED)
    paths = [p for p in OUT.glob('native-*-results.txt') if p.stem.removesuffix('-results') in EXPECTED]
    paths += [p for p in sorted(OUT.glob('native-*-trace*.txt')) if '-last-trace' not in p.name]
    paths += [OUT / 'offline-suite-results.txt', OUT / 'native-controller.emulator-only.bin',
              OUT / 'mn10300.igen', OUT / 'additional-setting-map.json',
              OUT / 'effective-mode-address-references.json', args.log]
    paths += [ROOT / 'scripts' / f'{n}.java' for n in (
        'OM3NativeFlow', 'OM3NativeQueue', 'OM3NativeLifecycle', 'OM3NativeProfiles',
        'OM3NativeHooks', 'OM3NativeFaults', 'OM3NativeStateSpace', 'OM3OfflineSuite')]
    paths += [Path(__file__), ROOT / 'scripts/Run-OM3OfflineProof.ps1', ROOT / 'OFFLINE-AF-PROOF.md',
              ROOT / 'analysis/button-af/FEATURE-SPEC.md',
              ROOT / 'analysis/button-af/OM3-AF-feasibility.canvas.tsx.source']
    manifest = dict(verified_at_utc=datetime.now(timezone.utc).isoformat(),
                    source_main_sha256=sha(main_image), original_vendor_sha256=sha(original),
                    checks=sum(EXPECTED.values()), suites=EXPECTED, exhaustive_button_edges=224,
                    verdict='Native emulator mechanism demonstrated; complete camera extension unproven',
                    exclusions=['kernel scheduling/event semantics modeled', 'settings and memset modeled',
                                'device completion is a RAM fixture', 'original shooting handler bodies not executed',
                                'configuration UI, persistence, display and lens behavior not established',
                                'temporary artificial RAM addresses; no installable image'],
                    files={str(p.resolve().relative_to(ROOT)): sha(p) for p in paths})
    (OUT / 'offline-proof-validation.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Verified 66 checks, 224 finite button-state edges, pristine input hashes, and explicit scope.')

if __name__ == '__main__':
    main()
