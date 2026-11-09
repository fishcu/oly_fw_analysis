/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
SECTIONS {
.raw_acquire_hook 0x60af2f56 : { *(.raw_acquire_hook) }
.raw_acquire 0x60fdc750 : { *(.raw_acquire) }
}
hl_source_to_owner = 0x6069b44c;
hl_owner_row = 0x6069b4cc;
raw_acquire_resume = 0x60af2f5c;
