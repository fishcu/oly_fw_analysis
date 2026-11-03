/* OM-5 Mark II 1.1 (E148 build 1100) runtime addresses. */
SECTIONS {
 .delete_pointer 0x61234464 : { *(.delete_pointer) }
 .label_hook 0x60e4ade9 : { *(.label_hook) }
 .container_pointer 0x611a0c54 : { *(.container_pointer) }
 .reset_hook 0x60e9e0f4 : { *(.reset_hook) }
 .read_hook 0x6091c66d : { *(.read_hook) }
 .write_hook 0x6091c6bd : { *(.write_hook) }
 .display_hook 0x60a33eac : { *(.display_hook) }
 .builder_hook 0x603e7eb0 : { *(.builder_hook) }
 .parent_hook 0x60ea0180 : { *(.parent_hook) }
 .paint_pointer 0x610c1540 : { *(.paint_pointer) }
 .pages_hook 0x60dad5f5 : { *(.pages_hook) }
 .ext2 0x605af4b0 : { *(.ext2) }
 .ext6 0x60ca7b00 : { *(.ext6) }
 .ext7 0x612a4b98 : { *(.ext7) }
 .state 0x60ca7fc0 : { *(.state) }
 .refresh_hook 0x602e0826 : { *(.refresh_hook) }
 .creset_hook 0x602db531 : { *(.creset_hook) }
 .refresh_cases 0x604997f0 : { *(.refresh_cases) }
 .refresh_guard 0x605af560 : { *(.refresh_guard) }
 .pm_s1 0x602e0f82 : { *(.pm_s1) }
 .pm_s2 0x602e1119 : { *(.pm_s2) }
 .pm_s4 0x602e0fe8 : { *(.pm_s4) }
 .pm_s5 0x602e11fc : { *(.pm_s5) }
 .ext8 0x613f2b80 : { *(.ext8) }
 .ext5 0x60845a00 : { *(.ext5) }
}
axis = 0xa0ca7fc0;
screen_forward = 0x60ed5c18;
stock_delete_action = 0x60ed6476;
stock_container = 0x60e3ca0a;
label_resume = 0x60e4adf3;
label_format = 0x611b5af0;
reset_resume = 0x60e9e0fa;
parent_resume = 0x60ea0185;
read_resume = 0x6091c674;
write_resume = 0x6091c6c4;
stock_display_next = 0x6092bbfc;
display_resume = 0x60a33eb3;
builder_resume = 0x603e7eb5;
stock_get = 0x602d000d;
stock_ui_write = 0x60855cdc;
active_read = 0x602f50f8;
active_write = 0x602f5121;
color_builder = 0x603e7c3f;
stock_paint = 0x60d47237;
stock_font = 0x60d51f07;
stock_text = 0x60d4b7bc;
stock_font_release = 0x60d529eb;
direct_layout = 0x60f05251;
direct_ret = 0x60dad5fc;
child_get = 0x60dad302;
set_visible = 0x60f04d10;
refresh_get = 0x602d2fc2;
refresh_set = 0x602d2fdb;
raw_get = 0x602f4c5b;
refresh_default = 0x602e06ca;
creset_resume = 0x602db536;
loaded_bits = 0xa26e2698;
prop_byte = 0x602bbed5;
wc_set = 0x602f5173;
wc_get = 0x602f514d;
/* creset scratch in section 6's free tail (stock ff, unreferenced; uncached alias like axis) */
creset_kind = 0xa0ca7e70;
creset_ptr = 0xa0ca7e74;
creset_ret = 0xa0ca7e78;
creset_buf = 0xa0ca7e80;
