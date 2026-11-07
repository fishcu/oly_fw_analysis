# MN10300 aliased register-add carry defect — fix and verification

Offline tooling fix. **No firmware image was changed; readiness is still NO-GO.**

## What was wrong

Four register-register constructors in the Ghidra MN10300 SLEIGH language
(`mn103_base.sinc`) wrote the destination register and then passed the **source
register symbol** to the `addFlags`/`subFlags` macros, which re-read it to compute
carry (`CF`) and overflow (`VF`). For a same-register instruction such as
`add D0,D0`, the source had already been overwritten by the result, so `CF`/`VF`
were computed from the wrong operand. The arithmetic result, `ZF` and `NF` were
always correct.

Effect: the `u32 -> double` converter `0x6004c266` normalizes with
`add D0,D0; rol D1`. A cleared carry on a bit-31-set value made `rol D1` drop the
top bit, so the loop never reached its stop condition — a confirmed candidate for
the 2,000,000-instruction cap-stop seen in capture-reset connection processing.

## The fix

Snapshot the source into a local before writing the destination
(`local s:4 = <src>; dst = o + s; …Flags(o, s, dst)`), matching the already-correct
AM33 forms at `mn103_gen.sinc:198-202`. See `mn103_base.sinc.diff`. All three
variant `.sla` files were recompiled. Originals are in `backup-language/`.

## Files

- `mn103_base.sinc.diff` — the four-constructor change.
- `backup-language/` — original `mn103_base.sinc` and the three original `.sla`.
- `before/carry-test-result.txt`, `after/carry-test-result.txt` — identical test,
  run against the unfixed and fixed compiled language.
- `evidence-manifest.json` — full description plus SHA-256 of every input/output.
- `../../../scripts/OM3CarryDefectTest.java` — the test (emulates the real
  `0x6004c28c`/`0x6004c28d` instructions through `EmulatorHelper`).

## Reproduce

Hashes:

```bash
python analysis/review/carry-fix/verify_evidence.py
```

Re-run the before/after test (needs the OM3_main_full project; JAVA_HOME set to
the portable JDK). To reproduce "before", restore `backup-language/` first and
recompile; the installed language currently holds the fix.
