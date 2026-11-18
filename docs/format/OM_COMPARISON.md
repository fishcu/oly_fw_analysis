# OM firmware container comparison

The following exact input files were parsed, their additive component checksums checked, and their decoded components re-encoded to reproduce the original containers byte for byte. This establishes the parser's round trip for these files, not camera update acceptance, cryptographic authentication, compatibility or recovery.

| Model / displayed firmware / build | Update SHA-256 | OE components |
| --- | --- | ---: |
| PEN-F 3.1 / 3101 | `77398610b379f80238117f31a6d5bbf65d608b49ec563666c64d84367e969f2c` | 4 |
| OM-3 1.1 / 1100 | `8c133084414533159f587bf46bfb4152714c4074312a47c8d8503e33d605696d` | 6 |
| OM-5 1.2 / 1200 | `a0c91f3ac7caaf0925b2af609e711183cf3b5982b3333224bcef26c0c5943d11` | 5 |
| OM-5 Mark II 1.1 / 1100 | `9de5d77e1d290fa2ed4ebc7d75cee0ed490befbc89566722467d1d421d66d637` | 5 |

The first three hashes matched independently published emulator inventory values. The Mark II input matched a fresh official download stream; no independently published digest was located. The two OM-5 containers use model bytes `1440` and `1480`, with five component kinds in the same order; every corresponding decoded component has a different SHA-256. This observation does not establish which components can be exchanged.

See [container format](CONTAINERS.md) for the parser and checksum method, [OM-3 update client](../boot/om-3/RECOVERY.md), and [OM-5 menu compatibility](../features/om-5/MENU_COMPATIBILITY.md). Container addresses, decoded offsets and runtime addresses are separate concepts. No physical update, authentication or recovery test is implied by these results.
