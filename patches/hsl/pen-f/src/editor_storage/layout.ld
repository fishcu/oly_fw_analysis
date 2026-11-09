/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
SECTIONS {
.hsl_set_hook 0x6073659d : { *(.hsl_set_hook) }
.hsl_get_pointer 0x609a4668 : { *(.hsl_get_pointer) }
.hsl_default_pointer 0x609a46ec : { *(.hsl_default_pointer) }
.hsl_axis 0x6069b7b8 : { *(.hsl_axis) }
.hsl_ui 0x60a4feb0 : { *(.hsl_ui) }
.hsl_wheel 0x6081b83a : { *(.hsl_wheel) }
.hsl_dispatch_hook 0x60bcba63 : { *(.hsl_dispatch_hook) }
.hsl_cycle 0x60fdc2e0 : { *(.hsl_cycle) }
.hsl_paint_pointer 0x60e04828 : { *(.hsl_paint_pointer) }
.hsl_initial_update 0x60c17373 : { *(.hsl_initial_update) }
.hsl_changed_update 0x60c17415 : { *(.hsl_changed_update) }
.persist_boot_hook 0x602b9f10 : { *(.persist_boot_hook) }
.persist_commit_hook 0x602f0c52 : { *(.persist_commit_hook) }
.persist_refresh_hook 0x602c50be : { *(.persist_refresh_hook) }
.capture_acquire 0x60253c7f : { *(.capture_acquire) }
.compact_acquire 0x605576ec : { *(.compact_acquire) }
.capture_to_job 0x605205f9 : { *(.capture_to_job) }
.compact_to_job 0x6055a28a : { *(.compact_to_job) }
.recording_to_job 0x605323f8 : { *(.recording_to_job) }
.transport 0x6069b38c : { *(.transport) }
.transport_rows 0x6069b590 : { *(.transport_rows) }
.hsl_wheel1_hook 0x6081b984 : { *(.hsl_wheel1_hook) }
.hsl_wheel3_hook 0x6081b8df : { *(.hsl_wheel3_hook) }
.hsl_persistence 0x60427c70 : { *(.hsl_cells) *(.hsl_persist) *(.persist_source) }
}
axis_uncached = 0xa069b7b8;
stock_color2_refresh = 0x602c1080;
stock_manager_finish = 0x6075fc45;
stock_manager = 0x6075fbed;
stock_get = 0x607359ef;
stock_default = 0x60735a4c;
stock_raw_get = 0x602b9f84;
wheel_resume = 0x6081bb7f;
stock_fsm_descriptor = 0x60bcbbc7;
stock_dispatch_resume = 0x60bcba68;
stock_viewer = 0x60c84901;
stock_draw_request = 0x60d147e8;
stock_entry_resume = 0x60cb02d8;
stock_paint = 0x60bbe8bb;
stock_update = 0x60c1768d;
stock_visible = 0x60cfcb51;
stock_invalidate = 0x60bc07e5;
stock_font = 0x60bca38f;
stock_text = 0x60bc1fbf;
stock_font_release = 0x60bcad32;
stock_initial_resume = 0x60c17378;
stock_changed_resume = 0x60c1741a;
stock_rectangle = 0x60bc69b8;
stock_pen = 0x60bca2b4;
stock_brush = 0x60bca074;
stock_bitmap = 0x60bc49b6;
stock_active_get = 0x602f06e7;
stock_active_set = 0x602f0710;
stock_boot_reset = 0x602ba62e;
stock_boot_resume = 0x602b9f15;
stock_refresh_resume = 0x602c50c3;
stock_bank_save = 0x602f067a;
hl_rows_uncached = 0xa069b590;
hl_compact_rows = 0xa069b770;
stock_color1_refresh = 0x602c1067;
stock_color3_refresh = 0x602c1099;
capture_acquire_resume = 0x60253c85;
compact_acquire_resume = 0x605576f2;
capture_job_resume = 0x605205ff;
compact_job_resume = 0x6055a291;
compact_setter = 0x6056d418;
recording_job_resume = 0x605323fe;
source_uncached = hl_profile_source + 0x40000000;
hl_source_uncached = source_uncached;
stock_backup_descriptor = 0x602c243c;
