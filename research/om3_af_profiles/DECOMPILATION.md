# OM-3 1.1 decompilation outputs

These are Ghidra reconstructions, not original or buildable source. A completed
decompiler result can still contain errors, unresolved instructions, inaccurate
types, or incorrect function boundaries. See each functions.tsv and bookmarks.tsv.

Recovered function candidates: 187,717; C output produced: 187,179; failures: 538.

Linux ELF exports completed: 241/241.

## Primary exports

- [analysis/decompiled-kernel/all-functions.c](analysis/decompiled-kernel/all-functions.c): 23,077 C results, 0 failures; 2,843 completed results with warning markers/diagnostics.
- [analysis/decompiled-main/all-functions.c](analysis/decompiled-main/all-functions.c): 98,356 C results, 529 failures; 18,316 completed results with warning markers/diagnostics.
- [analysis/decompiled-scpu/all-functions.c](analysis/decompiled-scpu/all-functions.c): 1,384 C results, 0 failures; 76 completed results with warning markers/diagnostics.

## Navigation

- Each export directory contains all-functions.c, all-functions.asm, calls.tsv,
  functions.tsv, bookmarks.tsv, summary.json and one C file per function address.
- Linux binaries have individual folders under analysis/decompiled-linux.
- analysis/embedded/rootfs contains extracted regular filesystem files.
- analysis/embedded/rootfs-inventory.json preserves original paths, modes and ELF hashes.
- Eighteen case-distinct files are stored under rootfs-case-sensitive because
  Windows cannot store their original paths side by side. The inventory maps
  original paths to authoritative storage paths. Corrected ELF exports carry
  path-hash prefixes; nine earlier ambiguous exports are excluded from this index.
- analysis/decompilation-index.json is the validated machine-readable index.

## Limits

- Function discovery is heuristic, especially in mixed MN103 code/data.
- The MN103 module leaves some user-defined instructions as opaque operations.
- The module's GCC calling convention is not established for proprietary camera code.
- Kernel symbols were recovered from kallsyms; its ELF is reconstructed.
- After repeated 10-second timeouts, a two-second no-output watchdog was applied
  only while traversing the problematic main-code region 0x60ec0000..0x60f00000.
  It made 5 native-decompiler interruption attempts; these failures remain in the index.
  The Ghidra JVM was preserved. Events are in analysis/decompiler-watchdog.jsonl.
  Native-process-death cases were retried with fresh decompilers and the original
  10-second limit; see decompiled-main/interrupted-retries.tsv. Remaining failures
  are not evidence that those functions can never be decompiled.
- Resource containers 0101, 010e and 0102 remain decoded data, not arbitrarily
  interpreted as executable code. Non-ELF peripheral blobs in the Linux filesystem
  also remain extracted inputs pending architecture identification.
- The camera was not accessed or modified.

## Reopen or reproduce

Run Open-Ghidra.ps1 with -Project main, scpu, linux, linux-corrections, kernel or validation.
The default is the full main-application project. Close a project before
running headless analysis on the same project.
Run Run-Decompilation.ps1 -Component main (or scpu/linux/kernel) to reanalyze
and export an existing project. Use linux-corrections for the case-distinct subset.
Initial imports use these settings:
- main: decoded 0100, BinaryLoader at 0x60021020, mn10300:LE:32:mn10300,
  OM3Prepare.java before analysis, OM3Export.java after analysis.
- scpu: decoded 0107, BinaryLoader at 0x08000000, ARM:LE:32:Cortex,
  OM3PrepareArm.java before analysis, OM3Export.java after analysis.
- linux: analysis/embedded/elf-inputs recursively, automatic ELF loader,
  OM3Export.java with export directory and batch arguments.
- kernel: analysis/embedded/linux-kernel-symbolized.elf, automatic ELF loader,
  OM3Export.java after analysis.
Scripts extract_embedded.py, extract_rootfs.py and recover_kernel.py reproduce
the embedded-image preparation. summarize_decompilation.py validates exports.
