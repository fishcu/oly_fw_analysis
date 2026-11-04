# E-M10 I boot and recovery

This reference concerns **E-M10 Mark I 1.4 (E113/1400)**. cmdada reports dumping
its early boot code and recovering a nonbooting modified main using OK+power
and a good SD update. The original dumps are not in the published repository,
so the boot-code interpretation remains attributed rather than independently
disassembled here.

Sources: [main report](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1886273),
[later updater finding](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1886391),
and [system notes](https://github.com/cmdada/em10-fw/blob/6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1/notes/system.md).
Publication dates, source identities and verification limits are in
[community reports](../../../provenance/community-reports.json).

## Reported boot chain

| Stage | Location | Role |
| --- | --- | --- |
| Mask ROM | CPU view `40000000`; 2 KiB mirror period | Reads straps and starts NAND or raw SD bootstrap |
| First stage | Logical flash `40000000`, length `7800` | Loaded at `47001000`; loads its remainder and configures clocks |
| Second stage | Logical flash `40020000`, length `31800` | Own filesystem/flash services and `[firmup]` card updater |
| Main | Update component at `40300000`; runtime entry `7D991020` | Normal camera firmware and section loading |

CPU address space and logical flash-service addresses are distinct. Reading
`40000000` directly and asking the flash service for that address can return
different objects. The ROM's strap-selected SD bootstrap is also separate from
the OK-button `DCOLYMP` updater; its card format and board-level accessibility
have not been established as a recovery method.

Independent decoding confirms that the stock update contains three components
at `40300000`, `41500000` and `42D00000`, with valid checksums. It contains no
component targeting the reported first/second-stage area. That describes this
package; it does not prove the updater refuses other destinations.

## Recovery is not write protection

cmdada's later post reports a **simulated** SD update overwriting the first
stage: a component targeting `40000000` reaches destination `80000000`, selects
write mode `0109`, passes the software guard and reports success. The public
snapshot predates that post and lacks its preboot simulator, input fixture and
trace. This result has not been independently replayed.

The earlier claim that ordinary flashing cannot touch the boot chain must
therefore be read narrowly: known main-only packages leave those areas out.
Do not infer that arbitrary valid-checksum containers are harmless or that an
immutable ROM guarantees recovery from damaged NAND boot stages.

PEN-F's separately analyzed backend also uses `0109` for a boot-related write
override. This is a useful correspondence, not proof of identical SD acceptance
or reset behavior. [PEN-F's recovery limits](../pen-f/RECOVERY.md) still apply.

## Obtaining the missing code

cmdada's [SYSDUMP source](https://github.com/cmdada/em10-fw/blob/6adb3bef36239859ae3fcd94b0dbb7db6de6ffa1/plugins/sysdump/sysdump.c)
uses native flash READ at `7D992410` to export `40000000..40300000` in 64 KiB
chunks. A separate operation reads the CPU ROM mapping. The source reproduces
the firmware's call frame and distinguishes failed reads in its output.

An independent probe assembles the source's 46-byte wrapper and runs it with
the stock READ routine. Nine cases verify arguments, address translation,
returns and saved registers, with sector I/O and synchronization modeled:

- Logical flash below `40300000` selects volume 0. At `40300000`, volume 1
  starts at sector zero. Sector size is 512 bytes.
- Read length rounds up to whole sectors. SYSDUMP's aligned 64 KiB chunks fit
  its buffer; a buffer sized for an arbitrary byte count may not.
- A modeled lower-level result of `-5` returns as `FFFB`, with the unlock
  call still reached. The source treats any nonzero result as a failed chunk,
  fills that chunk with `EE` and records the failure count. A written file can
  therefore contain failed reads; inspect its accompanying log.

To repeat the bounded check with an MN103 assembler, linker and native runner:

```sh
python3 tools/em10_dump_probe.py \
  --stock-main /path/to/em10-1400-main.bin \
  --upstream /path/to/em10-fw \
  --assembler /path/to/mn10300-elf-as \
  --linker /path/to/mn10300-elf-ld \
  --out generated/em10-read.json
```

The tool pins the decoded payload and SYSDUMP source hashes. It does not build
the complete plugin, perform file I/O on a camera or recover real boot bytes.

This provides a concrete method for studying boot code outside update files.
A port needs the target model's read service, calling convention, owned buffer
and file-operation context. The broad flash export includes per-camera
calibration, serials and settings: boot-code slices and their hashes are the
appropriate artifacts for sharing.

The public E-M10 emulator starts at main, with a supplied loader hand-off and
modeled flash reads. Its successful GUI startup does not independently test
the ROM, OK-button recovery selection or the reported destructive update.
