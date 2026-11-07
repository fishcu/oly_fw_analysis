"""Validate completed export inventories and write a durable decompilation index."""
import csv,json,collections
from pathlib import Path
root=Path(__file__).resolve().parent
analysis=root/'analysis'
expected=json.loads((analysis/'embedded/elf-input-manifest.json').read_text())
expected_names={x.get('export_name',x['staged_name']) for x in expected}|{'embedded-vdso-aarch64.elf'}
superseded=[]
programs=[]
for p in sorted(analysis.glob('decompiled-*/**/summary.json')):
    if 'decompiled-linux' in str(p) and p.parent.name not in expected_names:
        superseded.append(str(p.parent.relative_to(root)))
        continue
    summary=json.loads(p.read_text())
    index=p.parent/'functions.tsv'
    with index.open(encoding='utf-8') as f:rows=list(csv.DictReader(f,delimiter='\t'))
    assert len(rows)==summary['functions'],str(index)
    assert sum(r['decompiled']=='true' for r in rows)==summary['decompiled']
    assert len(list((p.parent/'functions').glob('*.c')))==len(rows)
    assert not summary['cancelled']
    bookmark_counts=collections.Counter()
    with (p.parent/'bookmarks.tsv').open(encoding='utf-8') as f:
        for row in csv.DictReader(f,delimiter='\t'):bookmark_counts[row['type']]+=1
    summary['bookmarks_by_type']=dict(bookmark_counts)
    summary['export_directory']=str(p.parent.relative_to(root))
    summary['inventory_validated']=True
    programs.append(summary)
linux=[p for p in programs if 'decompiled-linux' in p['export_directory']]
done={Path(p['export_directory']).name for p in linux}
missing=[x['staged_name'] for x in expected if x.get('export_name',x['staged_name']) not in done]
if 'embedded-vdso-aarch64.elf' not in done:missing.append('embedded-vdso-aarch64.elf')
result=dict(programs=programs,total_functions=sum(p['functions'] for p in programs),
    total_decompiled=sum(p['decompiled'] for p in programs),
    total_failed=sum(p['failed'] for p in programs),
    expected_linux_elfs=len(expected)+1,completed_linux_elfs=len(linux),missing_linux_elfs=missing)
result['superseded_case_collision_exports']=superseded
watchdog=analysis/'decompiler-watchdog.jsonl'
result['watchdog_interruption_attempts']=len(watchdog.read_text().splitlines()) if watchdog.exists() else 0
result['completed_results_with_warnings_or_diagnostics']=sum(p['functions_with_warnings_or_diagnostics'] for p in programs)
(analysis/'decompilation-index.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# OM-3 1.1 decompilation outputs','',
    'These are Ghidra reconstructions, not original or buildable source. A completed',
    'decompiler result can still contain errors, unresolved instructions, inaccurate',
    'types, or incorrect function boundaries. See each functions.tsv and bookmarks.tsv.','',
    f"Recovered function candidates: {result['total_functions']:,}; C output produced: {result['total_decompiled']:,}; failures: {result['total_failed']:,}.",'',
    f"Linux ELF exports completed: {len(linux)}/{len(expected)+1}.",'',
    '## Primary exports','']
for p in programs:
    if 'decompiled-linux' in p['export_directory']:continue
    directory=p['export_directory'].replace('\\','/')
    lines.extend([f"- [{directory}/all-functions.c]({directory}/all-functions.c): {p['decompiled']:,} C results, {p['failed']:,} failures; {p['functions_with_warnings_or_diagnostics']:,} completed results with warning markers/diagnostics."])
lines.extend(['','## Navigation','',
    '- Each export directory contains all-functions.c, all-functions.asm, calls.tsv,',
    '  functions.tsv, bookmarks.tsv, summary.json and one C file per function address.',
    '- Linux binaries have individual folders under analysis/decompiled-linux.',
    '- analysis/embedded/rootfs contains extracted regular filesystem files.',
    '- analysis/embedded/rootfs-inventory.json preserves original paths, modes and ELF hashes.',
    '- Eighteen case-distinct files are stored under rootfs-case-sensitive because',
    '  Windows cannot store their original paths side by side. The inventory maps',
    '  original paths to authoritative storage paths. Corrected ELF exports carry',
    '  path-hash prefixes; nine earlier ambiguous exports are excluded from this index.',
    '- analysis/decompilation-index.json is the validated machine-readable index.','',
    '## Limits','',
    '- Function discovery is heuristic, especially in mixed MN103 code/data.',
    '- The MN103 module leaves some user-defined instructions as opaque operations.',
    '- The module\'s GCC calling convention is not established for proprietary camera code.',
    '- Kernel symbols were recovered from kallsyms; its ELF is reconstructed.',
    '- After repeated 10-second timeouts, a two-second no-output watchdog was applied',
    '  only while traversing the problematic main-code region 0x60ec0000..0x60f00000.',
    f"  It made {result['watchdog_interruption_attempts']} native-decompiler interruption attempts; these failures remain in the index.",
    '  The Ghidra JVM was preserved. Events are in analysis/decompiler-watchdog.jsonl.',
    '  Native-process-death cases were retried with fresh decompilers and the original',
    '  10-second limit; see decompiled-main/interrupted-retries.tsv. Remaining failures',
    '  are not evidence that those functions can never be decompiled.',
    '- Resource containers 0101, 010e and 0102 remain decoded data, not arbitrarily',
    '  interpreted as executable code. Non-ELF peripheral blobs in the Linux filesystem',
    '  also remain extracted inputs pending architecture identification.',
    '- The camera was not accessed or modified.','',
    '## Reopen or reproduce','',
    'Run Open-Ghidra.ps1 with -Project main, scpu, linux, linux-corrections, kernel or validation.',
    'The default is the full main-application project. Close a project before',
    'running headless analysis on the same project.',
    'Run Run-Decompilation.ps1 -Component main (or scpu/linux/kernel) to reanalyze',
    'and export an existing project. Use linux-corrections for the case-distinct subset.',
    'Initial imports use these settings:',
    '- main: decoded 0100, BinaryLoader at 0x60021020, mn10300:LE:32:mn10300,',
    '  OM3Prepare.java before analysis, OM3Export.java after analysis.',
    '- scpu: decoded 0107, BinaryLoader at 0x08000000, ARM:LE:32:Cortex,',
    '  OM3PrepareArm.java before analysis, OM3Export.java after analysis.',
    '- linux: analysis/embedded/elf-inputs recursively, automatic ELF loader,',
    '  OM3Export.java with export directory and batch arguments.',
    '- kernel: analysis/embedded/linux-kernel-symbolized.elf, automatic ELF loader,',
    '  OM3Export.java after analysis.',
    'Scripts extract_embedded.py, extract_rootfs.py and recover_kernel.py reproduce',
    'the embedded-image preparation. summarize_decompilation.py validates exports.',''])
(root/'DECOMPILATION.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('programs','missing_linux_elfs','superseded_case_collision_exports')},indent=2))
