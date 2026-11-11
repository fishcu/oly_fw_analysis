// Finding 5 fix: the key-port hook 0x6017a5fc runs in INTERRUPT context (IRQ 0x140 handler 0x600709dc on core 0;
// hook-core1 observations), where the mutex-create service 0x60030659 returns E_CTX (-25: nest byte check at
// 0x60030665..0x60030691). The consolidated v3 installer would therefore always fail on the camera.
// Redesign (v4), emulator only, no image written:
//  - ENSURE (task context, fixed at the start of the freed section-1 gap 0x6031ead0): called by every wrapper after its
//    S+6 check (call [d2,d3,a2,a3],0x14). S+17==1 -> D0=1. Otherwise create the mutex with the same packet as before:
//    success -> S+20=id, S+17=1, D0=1; failure -> S+6=0, S+20=0, S+17=2, D0=0. The wrapper takes its stock path
//    (original handler, no profile change) when D0 != 1. Wrappers all run in the GUI task (task 165, core 0), so
//    ENSURE is not re-entered. No retry after a failure (S+6=0 until reboot).
//  - Installer v4 (interrupt context, after ENSURE): no OS call. installed==1 -> done; section 7 not loaded -> done;
//    validate all four fields, write all four, installed=1; preserves D0/A0 (saved to ST+0x18/+0x78) as before.
//  - Wrapper change: `movbu (S+17),D0; cmp 1; jne reject` becomes `call ENSURE; cmp 1,D0; jne stock` (+1 byte).
// Harness model (labelled): runHook runs with an interrupt-context flag; the 0x60030659 model returns E_CTX while it
// is set (the native check is the service's first test). The matrix's wrapper calls run in task context.
// Controls: c0 reproduces Finding 5 with the v3 installer (E_CTX, feature disabled, no redirect); then v4: c1 section 7
// not loaded; c2 foreign field; install (no OS call, no mutex yet); c3 first wrapper call with create failure (stock
// handler runs, feature off, no mutex); state reset; then the 28-edge matrix, whose first wrapper call creates the
// mutex in task context. The live access audit (OM3LiveAccessAudit) runs on the installed v4 layout.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3TaskContextMutexProof extends OM3LiveAccessAudit {
 static final long ENSURE=GAP;
 boolean inInterrupt=false;int ectx=0,taskCreates=0,ensureLen=0,v4Len=0;
 // ---- wrapper: as OM3SerializedProfiles.wrapper, with the S+17 test replaced by a call to ENSURE
 @Override byte[] wrapper(long address,long event,long original)throws Exception {
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0);volatileStore(a);
  a.load8(S+6);a.x(0xa0,1);a.ne("stock");callAt(a,address,ENSURE,0xf0,0x14);a.x(0xa0,1);a.ne("stock");
  load32(a,S+20);callAt(a,address,0x60032312L,0xf0,0x14);a.x(0xa0,0);a.ne("reject");a.imm(2,16);
  a.label("retry");a.imm(0,event);callAt(a,address,RECONCILE,0,0);a.load8(S+5);a.x(0xa0,0);a.eq("original");a.x(0xa0,4);a.ne("unlockReject");
  a.x(0x2a,0xff,0xaa,0);a.eq("exhausted");a.imm(0,1);callAt(a,address,0x60031581L,0xb0,0x10);a.jump("retry");
  a.label("exhausted");a.imm(0,8);a.store8(S+5);a.label("unlockReject");load32(a,S+20);callAt(a,address,0x6003791bL,0xf0,0x18);a.jump("returnInputs");
  a.label("original");inputs(a);callAt(a,address,original,0,0);volatileStore(a);load32(a,S+20);callAt(a,address,0x6003791bL,0xf0,0x18);a.jump("returnInputs");
  a.label("stock");inputs(a);callAt(a,address,original,0,0);volatileStore(a);a.jump("returnInputs");
  a.label("reject");a.imm(0,9);a.store8(S+5);a.label("returnInputs");volatileRestore(a);a.x(0xf8,0xfe,0x20,0xce,0xf0,0xdf,0,0);return a.finish();
 }
 // ---- small assembler with rel8 branches (same scheme as assembleV3)
 static class B {
  final java.io.ByteArrayOutputStream b=new java.io.ByteArrayOutputStream();final Map<String,Integer> lab=new HashMap<>();final List<Object[]> fx=new ArrayList<>();final long at;
  B(long at){this.at=at;}
  void x(int... v){for(int i:v)b.write(i&255);}void w(long v){for(int i=0;i<4;i++)b.write((int)(v>>>(8*i))&255);}
  void br(int op,String l){fx.add(new Object[]{b.size(),l});b.write(op);b.write(0);}
  void call(long target,int mask,int frame){int p=b.size();b.write(0xdd);w(target-(at+p));x(mask,frame);}
  void jmp(long target){int p=b.size();b.write(0xdc);w(target-(at+p));}
  void label(String l){lab.put(l,b.size());}
  byte[] finish()throws Exception{byte[] a=b.toByteArray();for(Object[] f:fx){int pos=(int)f[0];int d=lab.get((String)f[1])-pos;if(d<-128||d>127)throw new Exception("rel8 range "+f[1]+" d="+d);a[pos+1]=(byte)d;}return a;}
 }
 byte[] assembleEnsure(long at)throws Exception{
  B a=new B(at);
  a.x(0xfc,0xdf);a.w(ST);                                  // A3 = state base (uncached)
  a.x(0xf8,0x43,0x11,0xa0,0x01);a.br(0xc8,"ready");        // S+17 == 1 -> ready (D0 is 1)
  a.x(0xf8,0xfe,0xf0,0x80,0x02,0x42,0x04,0x00,0x42,0x08,0x3c,0x50); // packet (+4)=2, (+8)=0; A0=sp+4 (boot initializer bytes)
  a.call(MUTEX_CREATE,0xa0,0x10);                          // call 0x60030659,[d2,a2],0x10
  a.x(0xf8,0xfe,0x10);                                     // add 0x10,sp
  a.x(0xa0,0x00);a.br(0xc3,"fail");                        // id <= 0 -> fail
  a.x(0xf8,0x13,0x14,0x80,0x01,0xf8,0x53,0x11);            // S+20 = id; D0 = 1; S+17 = 1
  a.label("ready");a.x(0xdf,0xf0,0x14);                    // ret [d2,d3,a2,a3],0x14 (D0 = 1)
  a.label("fail");a.x(0x00,0xf8,0x53,0x06,0xf8,0x13,0x14,0x80,0x02,0xf8,0x53,0x11); // S+6=0, S+20=0, S+17=2
  a.x(0x00,0xdf,0xf0,0x14);                                // D0 = 0; ret
  return a.finish();
 }
 byte[] assembleV4(long at,long table)throws Exception{
  B a=new B(at);
  a.x(0xcf,0xf0);                                          // movm [d2,d3,a2,a3],(sp)
  a.x(0xfc,0xdf);a.w(ST);                                  // A3 = state base
  a.x(0xf8,0x13,0x18,0xf8,0x33,0x78);                      // save D0 (+0x18), A0 (+0x78)
  a.x(0xf8,0x43,0x1c,0xa0,0x01);a.br(0xc8,"done");         // installed == 1 -> done
  a.x(0xfc,0xa4);a.w(LOADED);a.x(0xfc,0xe0);a.w(0x40);a.br(0xc8,"done"); // section 7 not loaded -> done
  a.x(0xfc,0xde);a.w(table);a.x(0x8f,0x04);                // A2 = table, D3 = 4
  a.label("v");a.x(0x7a,0xf1,0xe8,0x70,0xf8,0x0a,0x04,0xa8);a.br(0xc8,"ok"); // A0 = field; D0 = (A0); == stock -> ok
  a.x(0xf8,0x0a,0x08,0xa8);a.br(0xc9,"done");              // != wrapper -> done (write nothing)
  a.label("ok");a.x(0x22,0x0c,0x2b,0xff);a.br(0xc9,"v");
  a.x(0x22,0xd0,0x8f,0x04);                                // A2 -= 48; D3 = 4
  a.label("wr");a.x(0x7a,0xf1,0xe8,0xf8,0x0a,0x08,0x68,0x22,0x0c,0x2b,0xff);a.br(0xc9,"wr"); // (field) = wrapper
  a.x(0x80,0x01,0xf8,0x53,0x1c);                           // installed = 1
  a.label("done");a.x(0xf8,0x03,0x18,0xf8,0x23,0x78);      // restore D0, A0
  a.x(0xce,0xf0,0xcf,0x20,0xf8,0xfe,0xf8);                 // pop; replay movm [a2],(sp); add -0x8,sp
  a.jmp(RESUME);
  return a.finish();
 }
 // ---- context model
 @Override void runHook(String label)throws Exception{boolean prior=inInterrupt;inInterrupt=true;try{super.runHook(label);}finally{inInterrupt=prior;}}
 @Override boolean external(long t)throws Exception {
  if(t==MUTEX_CREATE&&inInterrupt){ectx++;e.writeRegister("D0",0xffffffe7L);trace.add("MODEL:E_CTX mutex create from interrupt context (native check 0x60030665..0x60030691)");rl("E_CTX mutex create refused in interrupt context");return true;}
  if(t==MUTEX_CREATE&&!rejectCreate&&e.getExecutionAddress().getOffset()>=ENSURE&&e.getExecutionAddress().getOffset()<ENSURE+ensureLen){taskCreates++;rl("TASK-CONTEXT feature mutex create at "+e.getExecutionAddress());}
  return super.external(t);
 }
 long readReturn(){try{return u32(reg("SP"));}catch(Exception ex){return -1;}}
 void resetState(String why)throws Exception{
  e.writeMemoryValue(toAddr(ST+6),1,1);e.writeMemoryValue(toAddr(ST+17),1,0);e.writeMemoryValue(toAddr(ST+20),4,0);
  rl("FIXTURE:state reset after control ("+why+"): S+6=1, S+17=0, S+20=0");
 }
 @Override void redirect()throws Exception {
  if(prepared)return;prepared=true;redirected=true;
  long[][] recs=new long[4][];
  for(int i=0;i<4;i++){long[] r=RECORDS[i];long wrapper=translated(CODE+0x900+128*r[3]);wrapperByEvent.put(r[1],wrapper);
   check(u32(r[0])==r[1],"Stock table record event");e.writeMemoryValue(toAddr(field(r)),4,r[2]);recs[i]=new long[]{field(r),r[2],wrapper};}
  rl("SECTION7-STOCK all four handler fields hold their stock handlers");
  stateLine("after-boot");check(u8(ST+17)==0&&u32(ST+20)==0,"No mutex may exist after boot");
  byte[] ff=new byte[(int)(GAP_END-GAP)];Arrays.fill(ff,(byte)0xff);
  check(Arrays.equals(e.readMemory(toAddr(GAP),ff.length),ff),"Freed section-1 gap must be FF");
  byte[] ff48=new byte[48];Arrays.fill(ff48,(byte)0xff);check(Arrays.equals(e.readMemory(toAddr(TABLE2),48),ff48),"Section-2 table area must be FF");
  java.nio.ByteBuffer tb=java.nio.ByteBuffer.allocate(48).order(java.nio.ByteOrder.LITTLE_ENDIAN);for(long[] r:recs){tb.putInt((int)r[0]);tb.putInt((int)r[1]);tb.putInt((int)r[2]);}
  e.writeMemory(toAddr(TABLE2),tb.array());
  check(u8(HOOK)==0xcf&&u8(HOOK+1)==0x20&&u8(HOOK+2)==0xf8&&u8(HOOK+3)==0xfe&&u8(HOOK+4)==0xf8,"Stock hook prologue");
  long bits=u32(LOADED);e.writeMemoryValue(toAddr(LOADED),4,bits|0x40L);rl("FIXTURE:section-7 loaded bit set (image bytes present; loader not run by harness)");
  // c0: Finding 5 reproduced with the v3 installer run in interrupt context.
  {byte[] v3=assembleV3(GAP,TABLE2);e.writeMemory(toAddr(GAP),v3);Asm j=new Asm();j.x(0xdc);j.w(GAP-HOOK);e.writeMemory(toAddr(HOOK),j.finish());decodeCache.clear();
   int before=ectx;runHook("c0-v3-installer-interrupt-context");stateLine("c0");
   check(ectx==before+1&&u8(ST+17)==2&&u8(ST+6)==0&&u32(ST+20)==0&&u8(INSTALLED)!=1,"Finding 5: v3 create refused (E_CTX), feature disabled, nothing installed");
   for(long[] r:RECORDS)check(u32(field(r))==r[2],"c0 fields stock");
   rl("C0 FINDING-5 REPRODUCED: v3 installer in interrupt context -> E_CTX, S+6=0, S+17=2, no redirect");
   e.writeMemory(toAddr(GAP),ff);resetState("c0");}
  // v4 placement: ENSURE then installer.
  byte[] ens=assembleEnsure(ENSURE);ensureLen=ens.length;installer=ENSURE+ensureLen;byte[] v4=assembleV4(installer,TABLE2);v4Len=v4.length;installerSize=v4Len;
  check(installer+v4Len<=GAP_END,String.format("ENSURE+v4 must fit the freed gap: %d + %d > %d",ensureLen,v4Len,GAP_END-GAP));
  e.writeMemory(toAddr(ENSURE),ens);e.writeMemory(toAddr(installer),v4);
  Asm j=new Asm();j.x(0xdc);j.w(installer-HOOK);e.writeMemory(toAddr(HOOK),j.finish());decodeCache.clear();
  rl(String.format("PLACEMENT ENSURE %08x..%08x (%d B), installer v4 %08x..%08x (%d B): %d of %d B; table %08x (48 B)",ENSURE,ENSURE+ensureLen,ensureLen,installer,installer+v4Len,v4Len,ensureLen+v4Len,GAP_END-GAP,TABLE2));
  Files.writeString(Paths.get(getScriptArgs()[0]).resolve("installer-disasm.txt"),"hook:\n"+disasm(HOOK,5)+"ensure (task context):\n"+disasm(ENSURE,ensureLen)+"installer v4 (interrupt context):\n"+disasm(installer,v4Len)+"wrapper 0 head:\n"+disasm(recs[0][2],48));
  int objects=objectID;
  // c1: section 7 not loaded -> defer.
  e.writeMemoryValue(toAddr(LOADED),4,bits&~0x40L);runHook("c1-section7-not-loaded");stateLine("c1");
  check(u8(INSTALLED)!=1,"c1 installs nothing");for(long[] r:RECORDS)check(u32(field(r))==r[2],"c1 fields stock");
  e.writeMemoryValue(toAddr(LOADED),4,bits|0x40L);
  // c2: foreign field -> nothing written.
  e.writeMemoryValue(toAddr(field(RECORDS[2])),4,0x12345678L);runHook("c2-one-field-not-stock");stateLine("c2");
  check(u8(INSTALLED)!=1,"c2 not installed");for(int i:new int[]{0,1,3})check(u32(field(RECORDS[i]))==RECORDS[i][2],"c2 validate-first field "+i);
  e.writeMemoryValue(toAddr(field(RECORDS[2])),4,RECORDS[2][2]);
  // install (interrupt context): no OS call, no mutex yet.
  runHook("install");stateLine("install");
  check(u8(INSTALLED)==1&&objectID==objects&&u8(ST+17)==0&&u32(ST+20)==0&&ectx==1,"Install: redirect only, no OS call, no mutex");
  for(int i=0;i<4;i++)check(u32(field(RECORDS[i]))==recs[i][2],"Installed wrapper field "+i);
  rl("INSTALL v4: four fields redirected from interrupt context with no OS call; mutex not yet created");
  // c3: first wrapper call (task context) with create failure -> stock handler, feature off, no mutex.
  {boolean mb=modelButtonBodies, routed=redirected;modelButtonBodies=true;redirected=false;int calls=buttonCalls;rejectCreate=true;
   rl("CONTROL c3: direct wrapper ABI call; GUI routing disabled for this control only, original body modeled");
   var saved=saveRegisters();
   try{e.writeRegister("A0",0x700b4000L);e.writeRegister("A1",0x700b5000L);runNative(recs[0][2],0,0);}
   finally{restoreRegisters(saved);modelButtonBodies=mb;redirected=routed;rejectCreate=false;}
   stateLine("c3");
   check(buttonCalls==calls+1&&u8(ST+6)==0&&u8(ST+17)==2&&u32(ST+20)==0,"c3: create failure -> stock handler called once, feature off, no mutex");
   rl("C3 first wrapper call with create failure: stock handler ran, S+6=0, S+17=2");
   resetState("c3");}
  rl("V4 READY: matrix follows; its first wrapper call must create the mutex in task context");
  // Live access audit of the installed v4 layout (inherited, once).
  if(!audited){audited=true;try{auditAll();}catch(Exception ex){auditResult="BOUNDARY "+ex;}writeAudit();}
 }
 @Override void auditAll()throws Exception{
  for(long[] b:blocks)audit(String.format("live block %08x<-%08x",b[1],b[0]),b[1],(int)b[2]);
  audit("ENSURE (task context, freed section-1 gap)",ENSURE,ensureLen);
  audit("installer v4 (interrupt context, freed section-1 gap)",installer,v4Len);
  audit("hook (key-port callback prologue)",HOOK,5);
  audit("patched stock accessor",0x609b3bb2L,9);
  audit("patched stock entry",0x603cedfeL,5);
  rep.add(String.format("== installer table %08x (section 2, read-only data, 48 B)",TABLE2));
  for(int i=0;i<4;i++){long fld=u32(TABLE2+12*i),stock=u32(TABLE2+12*i+4),wrap=u32(TABLE2+12*i+8);
   rep.add(String.format("   entry %d field=%08x stock=%08x wrapper=%08x current=%08x",i,fld,stock,wrap,u32(fld)));
   if(fld%4!=0)f("MISALIGNED-TABLE-FIELD",String.format("entry %d %08x",i,fld));
   if(fld<SEC7_LO||fld>=SEC7_HI)f("TABLE-FIELD-OUTSIDE-SECTION7",String.format("entry %d %08x",i,fld));
   else f("TABLE-FIELD-SECTION7-CACHED-W",String.format("entry %d %08x (installer store, core 0)",i,fld));
   if(!inPlaced(wrap))f("TABLE-WRAPPER-NOT-PLACED",String.format("entry %d %08x",i,wrap));
   if(stock!=RECORDS[i][2])f("TABLE-STOCK-MISMATCH",String.format("entry %d %08x",i,stock));}
  auditResult="AUDITED live blocks="+blocks.size()+" + ENSURE("+ensureLen+" B) + installer v4("+v4Len+" B) + hook + 2 patched sites + table";
 }
 @Override boolean inPlaced(long a){return super.inPlaced(a)||a>=ENSURE&&a<ENSURE+ensureLen+v4Len;}
 @Override public void run()throws Exception {
  try{super.run();}finally{
   List<String> s=new ArrayList<>();s.add("E_CTX refusals (interrupt context) = "+ectx);s.add("task-context mutex creates = "+taskCreates);
   s.add(String.format("state at end: S+6=%d S+17=%d S+20=%08x installed=%d",u8(ST+6),u8(ST+17),u32(ST+20),u8(INSTALLED)));
   Files.write(Paths.get(getScriptArgs()[0]).resolve("task-context-mutex-summary.txt"),s);
  }
 }
}
