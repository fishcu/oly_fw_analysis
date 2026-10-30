SECTIONS
{
  .text 0x601caa50 : { *(.text) }
  .dispatch 0x60175f48 : { *(.dispatch) }
  .state 0x601cafb0 : { *(.state) }
  .poll 0x60171c16 : { *(.poll) }
  .parser 0x60165276 : { *(.parser) }
  .ae 0x605ddb6c : { *(.ae) }
  .disconnect 0x60158fee : { *(.disconnect) }
  /DISCARD/ : { *(.comment) *(.note*) }
}
ASSERT(SIZEOF(.text) <= 0x560, "Code exceeds reviewed section-1 interior")
ASSERT(SIZEOF(.state) == 4, "Publication must remain one aligned word")
ASSERT(SIZEOF(.poll) == 9, "Polling overlay length differs")
ASSERT(SIZEOF(.parser) == 8, "Parser overlay length differs")
ASSERT(SIZEOF(.ae) == 7, "AE CALL overlay length differs")
ASSERT(SIZEOF(.disconnect) == 8, "Disconnect overlay length differs")
stock_info_get = 0x600750ee;
stock_discovery_resume = 0x60158ff6;

ASSERT(SIZEOF(.dispatch) == 9, "Dispatch overlay length differs")
stock_dispatch_resume = 0x60175f51;
stock_dispatch_null = 0x60175fd5;
