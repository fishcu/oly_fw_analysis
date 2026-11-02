SECTIONS {
 .delete_pointer 0x615d0b64 : { *(.delete_pointer) }
 .label_hook 0x611d1401 : { *(.label_hook) }
 .container_pointer 0x615370e8 : { *(.container_pointer) }
 .reset_hook 0x61225de4 : { *(.reset_hook) }
 .read_hook 0x60bb52f8 : { *(.read_hook) }
 .write_hook 0x60bb534c : { *(.write_hook) }
 .display_hook 0x60b1d363 : { *(.display_hook) }
 .builder_hook 0x60518615 : { *(.builder_hook) }
 .parent_hook 0x61228102 : { *(.parent_hook) }
 .paint_pointer 0x61452290 : { *(.paint_pointer) }
 .extension 0x6031e920 : { *(.extension) }
 .state 0x6031efa0 : { *(.state) }
}
axis = 0xa031efa0;
screen_forward = 0x6125becc;
stock_delete_action = 0x6125c7a7;
stock_container = 0x611c28e0;
stock_settings = 0x60b8696a;
label_resume = 0x611d1416;
reset_resume = 0x61225dea;
parent_resume = 0x61228107;
read_resume = 0x60bb52ff;
write_resume = 0x60bb5353;
display_resume = 0x60b1d401;
builder_resume = 0x6051861a;
stock_get = 0x603f039d;
stock_ui_write = 0x60aea1de;
active_read = 0x604197e2;
active_write = 0x6041980b;
color_builder = 0x60518381;
stock_paint = 0x610d8b6c;
stock_font = 0x610f459d;
stock_text = 0x610e7818;
stock_font_release = 0x610f50d1;
