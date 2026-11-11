# E-M5 III image stabiliser (IBIS)

The in-body image stabiliser moves the sensor to cancel camera shake. On the
E-M5 III the control loop does not run on the main CPU: a separate IS sub-CPU
runs it, and the main program sends it numbered commands over a serial link.
This page lists that link, the command set, the IS settings, and how the OM-5's
movie "IS Level" setting compares. Build identities are in
[address spaces](../../format/e-m5-iii/ADDRESS_SPACES.md).

Evidence: static disassembly unless stated. Nothing on this page has been tested
on a camera.

Terms used here:

- **Sub-CPU:** a separate microcontroller next to the main processor.
- **Sync IS:** body and lens stabilisers sharing the correction.
- **VCM:** voice-coil motor, the actuators that move the sensor.

## How it is driven

- The servo (gyros, accelerometer, hall sensors, VCMs) runs on the IS sub-CPU.
  The main CPU talks to it over a synchronous serial link (`bc_sio`: channel,
  master/slave, clock edge, up to 8 MHz) with reset, CS, RDY and RQ lines. The
  sub-CPU has its own boot (SYS) and application (USR) firmware.
- The host side is the "bc" module ("Blurring Correction"), `60103f21..6011f82f`.
  Requests go through submit `60116bc5` (a0 = 104-byte packet, command id at +12).
- Actuators are Y, X1 and X2 (X1/X2 differential gives roll). Calibration lives
  in the STAB_FLASH parameters (`PRM_BC_HALL_*`, `PRM_BC_GYRO_TEMPOFS_TABLE_*`,
  `PRM_BC_GYRO_SLOPE_MATRIX`).
- The sub-CPU firmware is most likely the LUKE component (kind `0x10e`). The
  updater writes it with the same routine as the "BURE" (shake) firmware
  (`60c3b7ad`), and its strings include `luke_main\cpu0\ms\` and
  `luke_main\cpu1\cmd\task_drive.c`. Its instruction set is not identified. OM-5's
  LUKE differs in 42% of its bytes. This is inferred, not proven.

## Command set

There are 57 commands, decoded from the `bc com` parser (`6010ee39`) and jump
table `601b5d58`. Selected ones:

| Id | Purpose |
| --- | --- |
| 8 | set mode |
| 9 | centering |
| 10 | stop |
| 11 | drive to a target (pos_x, pos_y, pos_roll) |
| 12 | tripod High Res drive |
| 13 | start IS (det_mode, corr_mode, opt_param, image_mag, ratio_yaw, ratio_pitch, tv) |
| 15 | switch IS |
| 16 | handheld High Res drive |
| 24-27 | IS parameters |
| 31 | constant-speed drive (axis, speed) |
| 35 | rotation drive |
| 37-40 | parameter set / get |

- Stock code has no sender for 11, 31 and 35; only the `bc com` debug command
  sends them. Tripod High Res uses 12 and handheld uses 16.
- Sync IS split: command 13 carries the lens share (128 = 100%) from `620a8ffa`
  (yaw) and `620a8ffb` (pitch), computed by `6010658b`. With a non-cooperating
  lens, body = 128 and lens = 0.
- Ids match the OM-5 up to 18. Above that, OM-5 id = E-M5 III id minus 1. OM-5
  drops commands 22 (ICT log) and 23 (level gauge state) and adds body/lens ratio
  and per-axis limit parameters, so its LUKE is not a drop-in replacement.
- The user shell's `bc` command (handler `6010d41b`) offers `version`, `dbginfo`,
  `getprm`, `tsdata`, `com`, `exec`, `boot`, `rst`, `bps` and `tmo`.

## IS settings and "IS Level"

- E-M5 III has S-IS AUTO/1/2/3/Off, M-IS1/2/Off, IS focal length, panning modes,
  sequential-shooting IS speed/stability, Lens I.S. Priority and Half Way Rls
  With IS. It lacks the movie "IS Level" (`MODE_MOVIE_ANTI_SHAKE_STRENGTH`) that
  OM-5, E-M1 III and OM-5 II have.
- On OM-5, IS Level is setting 1477 / property 6569, read only by the IS host. Its
  value (-1, 0, +1) picks one of three parameter sets in `6011aac6` with gain 0.6
  for ±1.
- The sets are property defaults (properties 1394/1410/1602/1618/6130/6146). E-M5
  III has 18 values (sets A and B); OM-5 has 27 (A, B and C, where C is 9 × 128).
- E-M5 III has the matching level function `6010bc83`, including the +1 branch
  (× 0.6), but its three callers (`6010af2a`, `6011ca8a`, `6011d445`) always pass
  level 0. Argument struct: +2 table pair, +3 table, +4 still (0) or movie variant
  (1, 2), +10 level, outputs at +12/+14. Level +1 matches OM-5's +1 only when
  +2 ≠ 0 and +4 = 1; for +4 = 2 the gain is 0. E-M5 III's -1 follows the normal
  formula rather than OM-5's set C. Property 6569 is unused on E-M5 III.

## Verification and limits

- The command table comes from the parser and jump table in the pinned 1700
  main, and the labels are the firmware's own strings. The level-function
  behaviour is read from disassembly.
- No IS command has been sent and no level change has been tested on a camera.
