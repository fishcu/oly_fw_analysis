SECTIONS {
 .wb_hook 0x602d19b6 : { *(.wb_hook) }
 .wb_extension 0x605af5cc : { *(.wb_extension) }
 .wb_profile 0x613f2e00 : { *(.wb_profile) }
}
PM_ID = 111;
loaded_bits = 0xa26e2698;
commit_resume = 0x602d19bb;
busy = 0xa0ca7ff8;
stock_get = 0x602d000d;
stock_ui_write = 0x60855cdc;
active_read = 0x602f50f8;
active_write = 0x602f5121;
pm_refresh = 0x602e082f;
ctx_get = 0x602d2fc2;
