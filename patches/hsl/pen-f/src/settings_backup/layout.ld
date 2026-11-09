/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
SECTIONS {
.backup_export_hook 0x602c1829 : { *(.backup_export_hook) }
.backup_header_hook 0x602c1e8f : { *(.backup_header_hook) }
.backup_line_hook 0x602c1ed2 : { *(.backup_line_hook) }
.backup_footer_hook 0x602c1f73 : { *(.backup_footer_hook) }
.backup_import 0x601cac70 : { *(.backup_import) }
.backup_lifecycle 0x60427e48 : { *(.backup_lifecycle) }
.backup_export 0x60427ed0 : { *(.backup_export) }
}
hl_decode_cell = 0x60427c70;
native_600751c5 = 0x600751c5;
native_602c176b = 0x602c176b;
native_602c182f = 0x602c182f;
native_602c183f = 0x602c183f;
native_602c1e95 = 0x602c1e95;
native_602c1ed8 = 0x602c1ed8;
native_602c1f2e = 0x602c1f2e;
native_602c1f79 = 0x602c1f79;
native_602c1f83 = 0x602c1f83;
native_602c2651 = 0x602c2651;
native_602c2734 = 0x602c2734;
native_602f06b6 = 0x602f06b6;
native_602f06e7 = 0x602f06e7;
native_602f0710 = 0x602f0710;
