SECTIONS {
 .wb_hook 0x602d19b6 : { *(.wb_hook) }
 .wb_extension 0x605af5cc : { *(.wb_extension) }
}
PM_ID = 111;
commit_resume = 0x602d19bb;
busy = 0xa0ca7ff8;
stock_get = 0x602d000d;
stock_ui_write = 0x60855cdc;
active_read = 0x602f50f8;
active_write = 0x602f5121;
