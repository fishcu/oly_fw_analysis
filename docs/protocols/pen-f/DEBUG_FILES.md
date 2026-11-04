# Other debug files and execution points

The [stock SD debug switch](WIFI_DEBUG.md) leads to several other useful PEN-F
3101 mechanisms. Their scope differs: a file can supply settings, record events,
or serve a factory test without being an automatic startup trigger.

## Parameter import completion

After importing `PARAMDT/CP??????.CSV`, routine `6007363b` terminates the records,
installs the RAM override through `600745a1`, then submits callback `6007439b`
through `6008593a`. The queue has 32 slots of 12 bytes at `a1c3ac54`, holding a
function, argument and CPU selection. Submission signals event flag `0x24`,
bit 1; consumer `600855a8` forwards work through `600700a8`.

This identifies an after-import execution point for a possible extension.
It is later than usable card/filesystem services, and its deferred context
must be understood before adding file I/O. It does not identify pre-main
recovery or prove a general stock plugin loader.

The original callback handles three conditions:

| Parameter | Observed action |
| --- | --- |
| `F971 != 0` | Start debug Wi-Fi and its shell. |
| `F981` | Select disabled, bounded or circular RAM diagnostic capture. |
| `7B64` bit 31 | Refresh cached parameter pointers used by strobe/flash control. |

The third condition calls `602db9f0 → 602db754`, which resolves 106 IDs through
`600750c4` and stores pointers in 8-byte entries at `615fd4f8`. Normal strobe
initialization also calls this loop. Native tests confirm the conditional loop
using synthetic IDs and modeled pointer resolution. This is a parameter-cache
refresh, not programming flash storage. It also shows why a generic parameter
override need not update consumers that already cached the old pointer.

## Key-event recording and replay

The stock `sdk macro` command family supports `rec`, `play` and `stop`, with an
optional file number 0–999. It constructs `MACROnnn.DAT` from a FAT-style
`MACRO000DAT` template. This can potentially support repeatable UI tests.

| PEN-F 3101 address | Role |
| --- | --- |
| `606b507f`, `6097fb0c` | SDK shell handler and macro command-table entry. |
| `606f49fc` | Parse the macro subcommand and optional decimal file number. |
| `606fa80b`, `606fa882` | Start and stop recording; stop schedules file output. |
| `606fa8f8`, `606faa25` | Read and write the numbered file. |
| `606fa777`, `606fa9af` | Start playback and deliver timed events. |

The recorder uses an 8000-byte array of time/event word pairs, selecting events
in the `0x02xxxxxx` family. Playback posts through `606bb95c` and loops back to
the first pair. These are traced instructions, not a hardware-qualified test
workflow. File validation, full event effects and clean stopping remain to be
checked. The reviewed entry is a shell command; merely placing the file on SD
does not establish automatic execution. Event replay is also distinct from
loading native executable code.

## Other file leads

| Name | Finding |
| --- | --- |
| `PCA/PCAWIFI.CSV` | Service routine `60b84679` checks the directory, reads up to 1024 bytes, parses a leading decimal number and passes it into Wi-Fi test setup. No ordinary-startup connection established. |
| `MN7GAMMA.CSV`…`PL7GAMMA.CSV`, `MN7_CTMP.CSV`…`PL7_CTMP.CSV`, `CDIFKNEE.CSV`, `ROTPRMTR.CSV` | Display-tuning strings exist, but exact pointer/alias scans found no filename references. The reachable display gamma command manipulates tables/registers. No active CSV startup reader or JPEG tone-curve control is established. |
| `DCOLYMP/F???????.BIN`, `L???????.BIN` | Strobe and lens firmware-update inputs through the existing updater loader. |
| `file memload NAME ADR [LEN]` | Shell help advertises a file-to-address transfer. Safe allocation, execution and code-relocation behavior are not established. |

Nearby numeric parameter IDs are not necessarily debug gates. For example,
`F9B1/F9C2/F9D2` hold registered lens data: ten names and associated numeric arrays.
No additional automatic native-code loader was identified in the reviewed card
scan, import-completion callback or command/file paths.
