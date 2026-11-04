/* Live ND helpers on HSL alpha-20261017. HSL fills the section-5 padding,
   so the helpers go into loaded section tails it leaves erased, with
   margins to HSL code:
     section 4 tail: 60a4fe6c..60a4feb0 (HSL hsl_ui starts at 60a4feb0)
                     60a4ffb3..60a50000 (after HSL wifi_bridge)
     section 3 tail: 6069b26c..6069b2b0 (HSL extension starts at 6069b2b0)
     section 5:      60fdc7a1..60fdc7c0 (last qualified bytes after HSL) */
flag_op = 0x60828c0b;
take_count = 0x6082bbd3;
request_mes_combine = 0x60849e19;
setting_get = 0x602f024a;

SECTIONS {
  .take_done_tail    0x60a4fe70 : { *(.take_done_tail) }
  .release_kind      0x60a4ffb4 : { *(.release_kind) }
  .bayer_handles     0x60a4ffcc : { *(.bayer_handles) }
  .scale_entry_cap   0x6069b270 : { *(.scale_entry_cap) }
  .review_entry_cap  0x6069b288 : { *(.review_entry_cap) }
  .exif_frame_count  0x60fdc7a4 : { *(.exif_frame_count) }
}
