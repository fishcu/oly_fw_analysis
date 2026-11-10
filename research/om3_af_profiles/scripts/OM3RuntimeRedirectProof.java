// Prototype of the runtime table redirect (HARDWARE-STAGE0-RECORD.md, "Runtime redirect" / hook site 0x6017a5fc).
// Section 7 (compressed) stays stock: the four shooting-table handler fields are restored to their stock handlers after
// the inherited resident preparation (which writes them statically). A native installer, reached by a 5-byte jmp patched
// over the key-port callback prologue at 0x6017a5fc (section 1, uncompressed), installs the redirect in RAM:
//   save D0; if installed byte set -> resume; if section-7 loaded bit (0xa32de590 & 0x40) clear -> resume;
//   for each record: if field == stock handler, store wrapper; then require field == wrapper, else resume without
//   setting installed; set installed; resume: restore D0, replay movm [a2],(sp); add -0x8,sp; jmp 0x6017a601.
// Placement (v2): table-driven, validate-first installer in the free section-1 gap 0x6031ead0..0x6031eb80.
// Installer state (saved D0 word, installed byte) uses the free state bytes DATA+0x18/+0x1c through the uncached alias.
// FIXTURES (labelled): key-port reads 6007071e/60070793 report "no change" (the stock callback returns through its own
// early exit at 6017a61a); the section-7 loaded bit is set explicitly for the install case (the harness image contains
// section 7's bytes but does not run its loader). Controls: bit clear -> must defer; one field not stock -> must not set
// installed. Every edge then runs the hook (fast path) before being delivered to the stock engine.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3RuntimeRedirectProof extends OM3EngineRoutedConsumerProof {
 static final long HOOK=0x6017a5fcL,RESUME=0x6017a601L,LOADED=0xa32de590L;
 static final long SAVE_D0=0xa031e938L,INSTALLED=0xa031e93cL;
 long installer;int installerSize;boolean prepared;Long sentinel;final List<String> rlog=new ArrayList<>();
 void rl(String s){elog(s);rlog.add(s);}
 byte[] assemble(long at,long[][] recs)throws Exception{
  Asm a=new Asm();
  a.x(0xfc,0x81);a.w(SAVE_D0);                       // mov D0,(SAVE_D0)
  a.load8(INSTALLED);a.x(0xa0,0);a.ne("resume");      // installed? -> resume
  a.x(0xfc,0xa4);a.w(LOADED);a.x(0xfc,0xe0);a.w(0x40);a.x(0xa0,0);a.eq("resume"); // section 7 not loaded -> resume
  for(int i=0;i<recs.length;i++){long field=recs[i][0],stock=recs[i][1],wrap=recs[i][2];
   a.x(0xfc,0xa4);a.w(field);a.x(0xfc,0xc8);a.w(stock);a.ne("chk"+i); // field != stock -> just check
   a.imm(0,wrap);a.x(0xfc,0x81);a.w(field);                           // field = wrapper
   a.label("chk"+i);a.x(0xfc,0xa4);a.w(field);a.x(0xfc,0xc8);a.w(wrap);a.ne("resume");}
  a.x(0x80,0x01);a.store8(INSTALLED);                 // mov 1,D0; installed = 1
  a.label("resume");
  a.x(0xfc,0xa4);a.w(SAVE_D0);                        // restore D0
  a.x(0xcf,0x20);a.x(0xf8,0xfe,0xf8);                 // replay movm [a2],(sp); add -0x8,sp
  int p=a.b.size();a.x(0xdc);a.w(RESUME-(at+p));      // jmp 0x6017a601
  return a.finish();
 }
 // Refined installer (v2): validate all four, then write all four; table-driven; placed in the free section-1 gap
 // 0x6031ead0..0x6031eb80 (between the state data end DATA+0x1b0 and the wrappers). Encodings confirmed against stock
 // instructions: cff0/cef0 movm push/pop [d2,d3,a2,a3]; 7a mov (A2),D2; f1eb mov D2,A3; 73 mov (A3),D0;
 // f80a04/f80a08 mov (4/8,A2),D2; a8 cmp D2,D0; 6b mov D2,(A3); 220c add 0xc,A2; 2bff add -1,D3; 8f04 mov 4,D3;
 // c8/c9 beq/bne rel8 (relative to the branch's own address).
 static final long GAP=0x6031ead0L,GAP_END=0x6031eb80L;
 byte[] assembleV2(long at,long table)throws Exception{
  java.io.ByteArrayOutputStream b=new java.io.ByteArrayOutputStream();Map<String,Integer> lab=new HashMap<>();List<Object[]> fx=new ArrayList<>();
  java.util.function.Consumer<int[]> x=v->{for(int i:v)b.write(i&255);};
  java.util.function.LongConsumer w=v->{for(int i=0;i<4;i++)b.write((int)(v>>>(8*i))&255);};
  java.util.function.BiConsumer<Integer,String> br=(op,l)->{fx.add(new Object[]{b.size(),l});b.write(op);b.write(0);};
  x.accept(new int[]{0xcf,0xf0});                                  // movm [d2,d3,a2,a3],(sp)
  x.accept(new int[]{0xfc,0x81});w.accept(SAVE_D0);                // mov D0,(SAVE_D0)
  x.accept(new int[]{0xfc,0xa8});w.accept(INSTALLED);x.accept(new int[]{0xa0,0});br.accept(0xc9,"done"); // installed -> done
  x.accept(new int[]{0xfc,0xa4});w.accept(LOADED);x.accept(new int[]{0xfc,0xe0});w.accept(0x40);x.accept(new int[]{0xa0,0});br.accept(0xc8,"done"); // section 7 not loaded -> done
  x.accept(new int[]{0xfc,0xde});w.accept(table);x.accept(new int[]{0x8f,0x04});   // A2=table, D3=4
  lab.put("v",b.size());
  x.accept(new int[]{0x7a,0xf1,0xeb,0x73});                        // D2=field; A3=D2; D0=(A3)
  x.accept(new int[]{0xf8,0x0a,0x04,0xa8});br.accept(0xc8,"ok");   // == stock -> ok
  x.accept(new int[]{0xf8,0x0a,0x08,0xa8});br.accept(0xc9,"done"); // != wrapper -> done (write nothing)
  lab.put("ok",b.size());
  x.accept(new int[]{0x22,0x0c,0x2b,0xff});br.accept(0xc9,"v");    // next entry
  x.accept(new int[]{0xfc,0xde});w.accept(table);x.accept(new int[]{0x8f,0x04});
  lab.put("wr",b.size());
  x.accept(new int[]{0x7a,0xf1,0xeb,0xf8,0x0a,0x08,0x6b});         // (field) = wrapper
  x.accept(new int[]{0x22,0x0c,0x2b,0xff});br.accept(0xc9,"wr");
  x.accept(new int[]{0x80,0x01,0xfc,0x82});w.accept(INSTALLED);    // installed = 1
  lab.put("done",b.size());
  x.accept(new int[]{0xfc,0xa4});w.accept(SAVE_D0);                // restore D0
  x.accept(new int[]{0xce,0xf0});                                  // movm (sp),[d2,d3,a2,a3]
  x.accept(new int[]{0xcf,0x20,0xf8,0xfe,0xf8});                   // replay prologue
  int p=b.size();b.write(0xdc);w.accept(RESUME-(at+p));            // jmp 0x6017a601
  byte[] a=b.toByteArray();
  for(Object[] f:fx){int pos=(int)f[0];int d=lab.get((String)f[1])-pos;check(d>=-128&&d<=127,"rel8 range");a[pos+1]=(byte)d;}
  return a;
 }
 String disasm(long start,int len)throws Exception{
  ghidra.app.util.PseudoDisassembler dis=new ghidra.app.util.PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  StringBuilder sb=new StringBuilder();
  for(long pc=start;pc<start+len;){byte[] b=e.readMemory(toAddr(pc),16);var ins=dis.disassemble(toAddr(pc),b);
   if(ins==null){sb.append(String.format("%08x ??\n",pc));pc++;continue;}sb.append(String.format("%08x %s\n",pc,ins));pc+=ins.getLength();}
  return sb.toString();
 }
 long field(long[] r){return r[0]+12;}
 void runHook(String label)throws Exception{
  var caller=saveRegisters();long oldTop=stackTop;stackTop=0x700e6000L;
  try{sentinel=0x5a5a0000L|(edge&0xffff);e.writeRegister("D0",sentinel);runNative(HOOK,0,0);}
  finally{stackTop=oldTop;restoreRegisters(caller);}
  StringBuilder s=new StringBuilder();for(long[] r:RECORDS)s.append(String.format("%08x ",u32(field(r))));
  rl(String.format("HOOK-RUN %s installed=%d fields=%s",label,u8(INSTALLED),s));
 }
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc==RESUME&&sentinel!=null){check(reg("D0")==sentinel,String.format("Installer must preserve D0 (got %08x, want %08x)",reg("D0"),sentinel));sentinel=null;}
  return super.instruction(ins);
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x6007071eL||t==0x60070793L){e.writeRegister("D0",0);trace.add("FIXTURE:key-port read "+Long.toHexString(t)+" = no change");return true;}
  return super.external(t);
 }
 @Override void redirect()throws Exception {
  if(prepared)return;prepared=true;redirected=true;
  long[][] recs=new long[4][];
  for(int i=0;i<4;i++){long[] r=RECORDS[i];long wrapper=translated(CODE+0x900+128*r[3]);wrapperByEvent.put(r[1],wrapper);
   check(u32(r[0])==r[1],"Stock table record event "+Long.toHexString(r[0]));
   e.writeMemoryValue(toAddr(field(r)),4,r[2]);   // section 7 as shipped: stock handler
   recs[i]=new long[]{field(r),r[2],wrapper};
   rl(String.format("SECTION7-STOCK record=%08x field=%08x restored to stock %08x (wrapper %08x to be installed at run time)",r[0],field(r),r[2],wrapper));}
  e.writeMemoryValue(toAddr(SAVE_D0),4,0);e.writeMemoryValue(toAddr(INSTALLED),1,0);
  // runtime-redirect2: the gap is already used by OM3BootMutexProof's boot-time initializer (0x6031ead0..0x6031eb4a,
  // run through the section-4 constructor group) and only 52 bytes remain. Placement is a layout decision recorded in
  // HARDWARE-STAGE0-RECORD.md; this run validates the v2 logic from emulator scratch memory and measures its size.
  byte[] gap=e.readMemory(toAddr(GAP),(int)(GAP_END-GAP));int firstFree=0;for(int i=gap.length-1;i>=0;i--)if((gap[i]&255)!=0xff){firstFree=i+1;break;}
  rl(String.format("GAP-CHECK %08x..%08x in use up to %08x (%d B free)",GAP,GAP_END,GAP+firstFree,gap.length-firstFree));
  installer=CODE+0x3e00;byte[] probe=assembleV2(installer,0);long table=(installer+probe.length+3)&~3L;
  byte[] code=assembleV2(installer,table);check(code.length==probe.length,"Stable installer size");
  java.nio.ByteBuffer tb=java.nio.ByteBuffer.allocate(48).order(java.nio.ByteOrder.LITTLE_ENDIAN);for(long[] r:recs){tb.putInt((int)r[0]);tb.putInt((int)r[1]);tb.putInt((int)r[2]);}
  
  installerSize=code.length;e.writeMemory(toAddr(installer),code);e.writeMemory(toAddr(table),tb.array());
  rl(String.format("PLACEMENT (emulator scratch) code %08x..%08x (%d B) + table %08x..%08x (48 B): total %d B",installer,installer+code.length,code.length,table,table+48,table+48-installer));
  check(u8(HOOK)==0xcf&&u8(HOOK+1)==0x20&&u8(HOOK+2)==0xf8&&u8(HOOK+3)==0xfe&&u8(HOOK+4)==0xf8,"Stock hook prologue cf20 f8fef8");
  Asm j=new Asm();j.x(0xdc);j.w(installer-HOOK);e.writeMemory(toAddr(HOOK),j.finish());decodeCache.clear();
  rl(String.format("INSTALLER size=%d bytes at %08x; hook %08x patched to jmp",installerSize,installer,HOOK));
  Files.writeString(Paths.get(getScriptArgs()[0]).resolve("installer-disasm.txt"),"hook:\n"+disasm(HOOK,5)+"installer:\n"+disasm(installer,installerSize));
  // Control 1: section 7 not loaded -> defer.
  long bits=u32(LOADED);e.writeMemoryValue(toAddr(LOADED),4,bits&~0x40L);runHook("control-section7-not-loaded");
  for(long[] r:RECORDS)check(u32(field(r))==r[2],"Installer must defer while section 7 is not loaded");check(u8(INSTALLED)==0,"Not installed while deferred");
  // Control 2: one field not stock -> must not set installed.
  e.writeMemoryValue(toAddr(LOADED),4,bits|0x40L);rl("FIXTURE:section-7 loaded bit set (image bytes present; loader not run by harness)");
  e.writeMemoryValue(toAddr(field(RECORDS[2])),4,0x12345678L);runHook("control-one-field-not-stock");
  check(u8(INSTALLED)==0,"Installer must not mark installed when a field is not stock/wrapper");check(u32(field(RECORDS[2]))==0x12345678L,"Installer must not overwrite a non-stock field");
  for(int i:new int[]{0,1,3})check(u32(field(RECORDS[i]))==RECORDS[i][2],"Validate-first: no field may be written when any field is foreign (field "+i+")");
  // Restore and install.
  e.writeMemoryValue(toAddr(field(RECORDS[2])),4,RECORDS[2][2]);runHook("install");
  check(u8(INSTALLED)==1,"Installer must mark installed");
  for(int i=0;i<4;i++)check(u32(field(RECORDS[i]))==recs[i][2],"Installed wrapper field "+i);
  rl("RUNTIME-REDIRECT installed: all four fields hold the wrappers; section 7 image bytes unchanged");
 }
 @Override void beforeNativeButton(long event)throws Exception {
  super.beforeNativeButton(event);
  runHook(String.format("fast-path before edge %d event %08x",edge,event));
  check(u8(INSTALLED)==1,"Redirect must stay installed");
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{Files.write(Paths.get(getScriptArgs()[0]).resolve("runtime-redirect-log.txt"),rlog);}
 }
}
