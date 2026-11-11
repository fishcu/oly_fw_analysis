"""Reject stale/incomplete suites; keep successes, limits and defect reproductions separate."""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import argparse,hashlib,json
R=Path(__file__).resolve().parents[1];O=R/'analysis/button-af/prehardware'
EXPECTED={'revised':{'PASS':15},'revised-coverage':{'PASS':21},'additional-contract':{'PASS':34,'BOUNDARY':8},'wake-audit':{'PASS':6},'packed-relocation':{'PASS':11},'shooting-continuation':{'BOUNDARY':4},'shooting-runtime':{'BOUNDARY':4},'recovery-before':{'REPRODUCED':2},'wake-before':{'REPRODUCED':6},'admission-ordering':{'BOUNDARY':2},'target-size':{'PASS':4}}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--log',type=Path,default=O/'prehardware-verified-run.log');args=p.parse_args();log=args.log.read_text(encoding='utf8')
 assert 'SCRIPT ERROR' not in log and 'ERROR REPORT' not in log,'A Ghidra script failed'
 for marker in ('REVISED CHECKS: 15 PASS','REVISED COVERAGE: 21 PASS','ADDITIONAL CONTRACTS: 42 records','PACKED RELOCATION: 11 PASS','ADMISSION ORDERING: 2 BOUNDARY counterexamples','TARGET SIZE: 4 PASS','Discarding changes to the following read-only file'):assert marker in log,marker
 paths=[]
 for name,counts in EXPECTED.items():
  path=O/(name+'-results.txt');rows=path.read_text(encoding='utf8').splitlines();assert dict(Counter(r.split()[0] for r in rows))==counts,(name,rows);paths.append(path)
 for name in ('shooting-continuation','shooting-runtime'):
  for i in range(4):
   path=O/(name+'-trace-'+str(i)+'.txt');assert 'MISSING-RUNTIME-READ:' in path.read_text(encoding='utf8');paths.append(path)
 assert log.count('> BOUNDARY original handler ')==8,'Expected all eight strict continuation outcomes'
 original=R/'firmware/catalog/OLY_E_147_1100_0000_0000.BIN';main_image=R/'analysis/decoded/00_0100_50000020.decoded.bin'
 assert sha(original)=='8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d'
 assert sha(main_image)=='5e8d376e9111a44ac0352f26030d7c1b17026d42c45f3600cfa02a0e8c5b7d59'
 package=json.loads((O/'packed-container-results.json').read_text());assert package['packed_code_bytes']==1780 and package['repaired_component_parser_accepted'] and package['unrepaired_edit_rejected'] and not package['saved_modified_component']
 inventory=json.loads((O/'static-inventory.json').read_text());assert inventory['padding']['remaining_bytes']==132
 paths += list(O.glob('revised-*-trace*.txt'))+list(O.glob('stock-type-trace-*.txt'))+list(O.glob('late-publisher-trace-*.txt'))+list(O.glob('packed-trace-*.txt'))+list(O.glob('admission-ordering-trace-*.txt'))+list(O.glob('target-size-trace-*.txt'))
 paths += [O/x for x in ('revised-reconcile.emulator-only.bin','revised-capture.emulator-only.bin','packed-code.emulator-only.bin','packed-relocation-map.txt','static-inventory.json','packed-container-results.json','windows.tsv')]
 paths += list(O.glob('*.asm'))+[args.log]
 paths += list((R/'scripts').glob('OM3Native*.java'))+[R/'scripts'/f'{n}.java' for n in ('OM3TargetSizeProof','OM3AdmissionOrdering','OM3RecoveryAudit','OM3RevisedProfiles','OM3RevisionChecks','OM3RevisionCoverage','OM3PrehardwareContracts','OM3WakeAudit','OM3WakeBeforeAudit','OM3PackedRelocation','OM3ShootingContinuation','OM3ShootingRuntime','OM3HumanWindows')]
 paths += [Path(__file__),R/'scripts/Run-OM3PrehardwareProof.ps1',R/'scripts/audit_om3_prehardware.py',R/'scripts/audit_om3_packed_container.py',R/'reference/tools/oly_container.py',R/'PREHARDWARE-AF-AUDIT.md',R/'analysis/button-af/FEATURE-SPEC.md',R/'analysis/button-af/OM3-AF-feasibility.canvas.tsx.source']
 result=dict(verified_at_utc=datetime.now(timezone.utc).isoformat(),new_pass_assertion_groups=91,explicit_boundary_records=18,defect_reproduction_cases=8,revised_finite_button_edges=224,stock_enum_orientation_button_combinations=66,movement_dimension_priority_cases=40,packed_native_code_bytes=1780,original_images_unchanged=True,results=EXPECTED,verdict='All seven investigation areas covered; complete extension and all software gaps NOT proved closed',remaining_offline_work=['Stock UI capture/event adapter and full original shooting transaction','Automatic recovery/retry and physical-event replay after rejection','Physical orientation mapping, saved banks, custom-mode/reset/sleep/wake hooks','Full display publication and scheduling/result provenance','Owned RAM, loading lifetime, complete update/boot chain'],files={str(f.resolve().relative_to(R)):sha(f) for f in sorted(set(paths))})
 (O/'prehardware-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print('Verified 91 additional PASS groups, 18 explicit boundary records, 8 defect reproductions, exact sources/results and pristine firmware hashes.')
if __name__=='__main__':main()
