/* AF limiter helper: section 5, after the Live ND maker-note helper and
   before the end of the qualified bytes at 60fdc800. */
setting_get = 0x602f024a;

SECTIONS {
  .af_limit 0x60fdc7c0 : { *(.af_limit) }
}
