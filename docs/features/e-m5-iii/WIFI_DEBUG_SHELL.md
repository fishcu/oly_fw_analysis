# Wi-Fi debug shell on the E-M5 III 1700: connecting and the `take` trace

The card-file Wi-Fi debug shell described for the PEN-F also works on an E-M5 III
running build 1700 (landmarks `60615f6d`, `6005bafb`, `6122e9f6`; identities in
[E-M5 III address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md)). This page
adds what a **physical camera test** on one E-M5 III showed about connecting, and
the `take` commands that turn the shell into a live trace of the shooting
sequencer.

Evidence: static disassembly unless marked as a **physical camera test**.

## Connecting

- With the card file in place, a laptop joins the camera's open network by
  DHCP: camera (router) `192.168.0.10`, laptop `192.168.0.3`, mask /24.
  **Physical camera test.**
- The shell is on TCP port 23 and needs **CR or CRLF** line endings: with LF
  alone (plain `nc`) commands print nothing. `nc -c 192.168.0.10 23` works.
  **Physical camera test.**
- The prompt `USR>` appears only after the first Enter. `help` lists the 58
  user commands of the table at `601fbe38`; `help <command>` only reprints the
  list. **Physical camera test.**
- One connection per power-on: after the first session is closed, a new
  connection gets no answer until the camera is power-cycled. Scripts should be
  the first and only connection. **Physical camera test.**
- The body shutter works normally while the network and a session are up.
  **Physical camera test.**

## `take`: shooting-sequencer trace

`take` (handler `602a158b`) with no argument prints its own help: `func ...`,
`dbgmode`, `dbginfo`, `exec COM`, `ev_qname NAME`; it also accepts
`cont_dbgmode`, `ps` and `pe`.

| Command | Effect |
| --- | --- |
| `take dbgmode` | prints the current value of the trace word `62107754` (RAM) |
| `take dbgmode 1` | turns the sequencer trace on: for every event the state name plus `.exec(n)`, `.ipost(n)` or `.post(n)`, and `old -> new` on each state change. The four readers in the state dispatcher (`602a0ff9`, `602a1125`, `602a1256`, `602a13ba`) only print. The value is stored unmasked (`602a1898`) and the readers test bit 0 only. |
| `take dbginfo` | print-only status (`602a169b`): sequencer state (`62107744`), event mask (`62107750`), the pending command, a `history` line of recent events and burst fields (continue_mode, uhs_cont_speed, capture_count, stop#req, uhs_cam_packet_queue) |

**Physical camera test:** with `take dbgmode 1` the trace streams to the port-23
session as it happens. A normal single shot reads:

```
Idle -> RdyStart -> RdyFcsRdy1-3 -> RdyTrig2Wait -> RdyFcsTake -> Standby -> StlRdy1 -> StlRdy2
-> StlTakeCave -> StlEnd1 -> StlEnd2 -> RdyTrig2Wait -> RdyAbort -> RdyEnd -> Idle
```

Because the lines leave the camera as they are printed, the trace survives a
reset or a battery pull, which a log in RAM or on the card does not. This is how
the hangs and resets in the [Live ND](LIVE_ND.md) port were found.

## Commands not to run

- `take exec`, `take ps`, `take pe`, `take func exec`: they post commands to the
  sequencer.
- `dbg test`, `dbg dmyp`, `dbg dmyw`, `dbg nmip`, `dbg nmiw` (`dbg` handler
  `61401a03`): they raise dummy warnings and NMIs on purpose.
- A line that is only `:` switches the session to the system-shell dispatcher
  (toggle byte `a25b8800`), which has memory reads (`mdump4/2/1`, `mem_get4/2/1`)
  but also `mem_put*`, `nmiset`, `arm load*` and `shelloff`. Not tried; whether
  its output reaches the Wi-Fi session is unknown.

## Verification and limits of the evidence

- The connection results and the single-shot trace come from one E-M5 III on
  build 1700 with the stock firmware and the card file only.
- Whether removing the card file and power-cycling fully undoes the network was
  not checked.
