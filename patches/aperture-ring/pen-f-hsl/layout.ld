/* Section-1 lens hooks retain their original load dependency. ORF helpers
 * use the reviewed section-8 suffix, reached through a section-1 guard.
 * All other alpha-20261017 HSL placements remain unchanged.
 */
SECTIONS {
  .ring_disconnect 0x601caa50 : { *(.ring_disconnect) }
  .ring_poll 0x601cac00 : { *(.ring_poll) }
  .ring_parser 0x601cade0 : { *(.ring_parser) }
  .ring_ae 0x601cae24 : { *(.ring_ae) }
  .ring_dispatch 0x601caed0 : { *(.ring_dispatch) }
  .state 0x601caa40 : { *(.state) }
  .poll 0x60171c16 : { *(.poll) }
  .parser 0x60165276 : { *(.parser) }
  .ae 0x605ddb6c : { *(.ae) }
  .disconnect 0x60158fee : { *(.disconnect) }
  .dispatch 0x60175f48 : { *(.dispatch) }
  .native_orf_guard 0x601caaca : { *(.native_orf_guard) }
  .native_orf_hook 0x6053caff : { *(.native_orf_hook) }
  .native_orf_export 0x6115b060 : { *(.native_orf_export) }
  .cmio_table 0x6115b120 : { *(.cmio_table) }
  .cmio_table_tail 0x6115b180 : { *(.cmio_table_tail) }
  .cmio_stream 0x6115b1f0 : { *(.cmio_stream) }
  .text 0x6115b220 : { *(.text) }
  /DISCARD/ : { *(.comment) *(.note*) }
}
ASSERT(SIZEOF(.ring_disconnect) <= 0x20, "Reset exceeds reclaimed CMIO stream")
ASSERT(SIZEOF(.ring_poll) <= 0x69, "Poll exceeds reclaimed CMIO tail")
ASSERT(SIZEOF(.ring_parser) == 0x44, "Parser size changed")
ASSERT(SIZEOF(.ring_ae) <= 0x7b, "AE exceeds reclaimed ORF export")
ASSERT(SIZEOF(.ring_dispatch) <= 0x9b, "Dispatch exceeds reclaimed CMIO weights")
ASSERT(SIZEOF(.native_orf_guard) <= 0x5b, "Guard exceeds reclaimed CMIO table")
ASSERT(SIZEOF(.state) == 4, "Publication must remain one aligned word")
ASSERT(SIZEOF(.native_orf_export) <= 0xc0, "ORF export overlaps relocated table")
ASSERT(SIZEOF(.cmio_table) <= 0x60, "CMIO table overlaps tail")
ASSERT(SIZEOF(.cmio_table_tail) <= 0x70, "CMIO tail overlaps stream")
ASSERT(SIZEOF(.cmio_stream) <= 0x30, "CMIO stream overlaps weights")
ASSERT(ADDR(.text) + SIZEOF(.text) <= 0x6115b7c0, "ORF code exceeds reviewed section-8 interior")
ASSERT(SIZEOF(.poll) == 9 && SIZEOF(.parser) == 8 && SIZEOF(.ae) == 7, "Hook sizes changed")
ASSERT(SIZEOF(.disconnect) == 8 && SIZEOF(.dispatch) == 9, "Entry hook sizes changed")
ASSERT(SIZEOF(.native_orf_hook) == 7, "ORF call contract changed")
stock_info_get = 0x600750ee;
stock_discovery_resume = 0x60158ff6;
stock_dispatch_resume = 0x60175f51;
stock_dispatch_null = 0x60175fd5;
hl_owner_row = 0x6069b4cc;
captured_lightness_lut = 0x6069b36e;
native_cmio_copy = 0x604db0f1;
native_buffer_map = 0x60547aec;
native_buffer_unmap = 0x60547bef;
native_uncached = 0x6007dd80;
