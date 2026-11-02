SECTIONS {
 .wb_hook 0x603f1ea1 : { *(.wb_hook) }
 .wb_loader 0x6031ef14 : { *(.wb_loader) }
 .wb_extension 0x60a8f100 : { *(.wb_extension) }
}
section_load = 0x60045ed5;
commit_resume = 0x603f1ea6;
busy = 0xa031efd8;
stock_get = 0x603f039d;
stock_ui_write = 0x60aea1de;
active_read = 0x604197e2;
active_write = 0x6041980b;
