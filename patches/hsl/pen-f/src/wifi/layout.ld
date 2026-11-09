/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: Apache-2.0
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
SECTIONS {
.wifi_ingress_hook 0x60aa26f0 : { *(.wifi_ingress_hook) }
.wifi_receiver_hook 0x607ab916 : { *(.wifi_receiver_hook) }
.wifi_reader_hook 0x60aa23c7 : { *(.wifi_reader_hook) }
.wifi_body 0x601cab25 : { *(.wifi_body) }
.wifi_validate 0x601caa70 : { *(.wifi_validate) }
.wifi_read_head 0x601cae9f : { *(.wifi_read_head) }
.wifi_read_tail 0x601caf6b : { *(.wifi_read_tail) }
.wifi_allowed 0x60fdc704 : { *(.wifi_allowed) }
.wifi_bridge 0x60a4ffa8 : { *(.wifi_bridge) }
}
stock_get = 0x602f024a;
stock_raw_set = 0x602f029d;
stock_app_event = 0x60aa4e7b;
stock_receive = 0x607abd07;
stock_receiver_return = 0x607ab91b;
stock_public_set = 0x602b9f33;
stock_active_get = 0x602f06e7;
hl_active_set = 0x60427cb4;
hl_decode_cell = 0x60427c70;
hl_publish = 0x60427d60;
hl_refresh_profile = 0x60427e09;
