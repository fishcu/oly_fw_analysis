# Flash readers and diagnostic dumps

The stock PEN-F diagnostic dump command is not a strictly read-only operation.
Its lower reader can replace degraded flash blocks, and the command bypasses
the lock used by ordinary flash reads. Access through the
[Wi-Fi debug shell](../../protocols/pen-f/WIFI_DEBUG.md) does not make it safe.
Addresses below refer to **PEN-F 3.1 build 3101**.

## Reader paths

| Entry | Behavior |
| --- | --- |
| `600725a4` | `flash` shell handler; dump branch at `60072bbf`. |
| `600219b5` | Mapped page reader; can trigger flash maintenance. |
| `6002189d` | Follow the logical-to-physical block map. |
| `600217a6` | Replace a block and update persistent mapping copies. |
| `60021c4f` | Physical page reader without the replacement branch. |
| `600224c2` | Ordinary read wrapper with flash serialization. |
| `600226d0`, `600226f9` | Acquire/release the flash semaphore. |

The mapped reader handles 2048-byte pages and 64-page blocks. It samples the
low nibble of controller register `98d01194`, then calls the replacement routine
when that value exceeds 13. Native fixtures verify the branch at 14 and 15.
The field resembles an error/correction measure, but its exact hardware meaning
is not established.

Replacement changes the RAM map, copies a 128 KiB block to scratch `61f22c00`,
erases/programs a replacement, marks the old block and rewrites mapping tables.
A native fixture for block zero reaches erase of replacement `47c00000` after
a modeled block copy. Execution stops before erase; subsequent writes are
statically traced. This may be normal flash maintenance, but it violates a
requirement to dump without persistent writes.

## Buffer and locking problems

The dump command allocates a `4040`-byte slot, reads 2048 main bytes, prints them,
reads spare information and releases the slot. Its allocator uses separate CPU
groups. Exhaustion tests expose these results:

| CPU-index fixture | Exhausted allocation |
| --- | --- |
| 0 | Null, passed to the reader without a check. |
| 1 | Slot 63, outside CPU1's group. |
| 2 | Slot 95, outside CPU2's group. |

CPU1/2 add the group offset to `-1` before checking for failure. In the all-full
fixture the returned slot is already owned. These cases do not establish that
U_SHELL normally executes on every CPU. Passing null to the lower reader logs
an alignment error but still produces DMA-address operand `ffffffff`; no actual
DMA or resulting hardware behavior was tested.

When runtime word `8ff00078` is 7, ordinary reads use semaphore 94 (`5e`). The
dump reaches the lower reader without that lock. Allocator exclusion protects
only allocation; it does not serialize NAND accesses against other tasks.

Error handling also matters. A completion error can be logged and followed by
a success return. A failed NAND-status check retries the same page without a
visible retry limit. The ordinary read wrapper discards the lower return value,
so adding that wrapper alone does not solve the problem.

The physical reader avoids block replacement but retains validation, locking,
error and buffer responsibilities. It is a candidate for a dedicated bounded
reader, not a qualified command ready to run. Logical and physical exports must
be distinguished, especially when blocks have been remapped.

## Wi-Fi dump output

The listener's 16 KiB allocation is split into RX/TX halves. TX uses an **8 KiB**
ring, pointer `a1c8ae30`, producer index `a1c8ae34`. Byte writer `6006d1ba` forwards
through `600429d1`; task `60aaa554` drains the ring to socket send `60a82cb0`.
This is separate from F981's RAM log and the other 16 KiB diagnostic capture.

The producer has no full-ring check. A full wrap before TX runs looks empty;
failed socket sends are not retried by the TX task. A 128-row page dump fits
without concurrent logs, but batching commands can still lose output.
Serial and network formatting can produce CRCRLF line endings.

A dependable export needs per-page address, length, status and checksum,
one outstanding request, and host-side completeness checks. Repeated matching
captures help detect transport loss; they do not by themselves prove correct
hardware reads or a safe read path.

## Reproduction and evidence

[penf_boot_dump_probe.py](../../../tools/penf_boot_dump_probe.py) runs 25 native
cases covering allocation, command dispatch, maintenance selection, locking,
error returns and output delivery:

```sh
python3 tools/penf_boot_dump_probe.py --out generated/boot-dump-qualification.json
```

It requires the pinned stock main and MN103 engine described in
[reproduction](../../../REPRODUCING.md). Controller completion, NAND status,
semaphores, allocation exclusion and socket sends are modeled. Unknown accesses
stop execution. Tests perform no DMA, actual flash read/write, networking or
physical-camera operation. The report includes input, probe and engine hashes.

This PEN-F audit builds on enduity's
[stock debug-shell discovery](https://www.mu-43.com/threads/modified-firmware-looking-for-users.99804/post-1888641)
and [cmdada's E-M10 work](../e-m10/RECOVERY.md). The command limitations above are
independent PEN-F findings, not claims made by those contributors.
