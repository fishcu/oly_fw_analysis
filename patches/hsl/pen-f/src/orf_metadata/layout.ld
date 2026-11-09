/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
SECTIONS {
.native_orf_hook 0x6053caff : { *(.native_orf_hook) }
.native_orf_export 0x601cade0 : { *(.native_orf_export) }
.cmio_table 0x601caaca : { *(.cmio_table) }
.cmio_stream 0x601caa50 : { *(.cmio_stream) }
.text 0x601caed0 : { *(.text) }
.cmio_table_tail 0x601cac00 : { *(.cmio_table_tail) }
}
hl_owner_row = 0x6069b4cc;
captured_lightness_lut = 0x6069b36e;
native_cmio_copy = 0x604db0f1;
native_buffer_map = 0x60547aec;
native_buffer_unmap = 0x60547bef;
native_uncached = 0x6007dd80;
