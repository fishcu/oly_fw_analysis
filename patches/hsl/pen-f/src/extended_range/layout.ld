/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
SECTIONS {
.range_wheel_encode 0x602fc3a7 : { *(.range_wheel_encode) }
.range_value_label 0x60c84c75 : { *(.range_value_label) }
.range_backup_enum_export 0x602c25a9 : { *(.range_backup_enum_export) }
.range_backup_enum_import 0x602c25fd : { *(.range_backup_enum_import) }
}
range_wheel_store = 0x602fc472;
stock_wheel_invalid = 0x602fc476;
stock_backup_descriptor = 0x602c243c;
range_backup_enum = 0x60427de7;
