// Consolidated first-use installer (v3): the feature's dedicated mutex is created by the runtime installer at the first
// key-port callback instead of by a boot-time constructor, and the table redirect follows. No new code runs at boot.
// Changes versus the tested chain (all labelled):
//  - IMAGE: OM3BootMutexProof's boot hook is reverted to stock in the emulated image before the sections load:
//    constructor count 0x602153fd = 0, table pointer 0x60215407 = 0x60a8f088, initializer 0x6031ead0.. and table entry
//    0x6031e910 back to FF. The section-4 constructor loop is then a stock no-op and no mutex exists after boot.
//  - CODE: v3 installer in the freed section-1 gap 0x6031ead0..0x6031eb80; its {field, stock, wrapper} table in the
//    section-2 padding 0x607187d0..0x60718800 (after the 43-byte mode block). Both sections are uncompressed.
//  - State: uncached alias base ST=0xa031e920 (as the live chain's dataAddress mapping): S+6 enabled, S+17 mutex status,
//    S+20 mutex id; scratch ST+0x18 (D0), +0x1c (installed byte), +0x74/+0x78/+0x7c (D1/A0/A1 around the OS call).
// Logic: push d2,d3,a2,a3; save D0; installed -> done; section 7 not loaded -> done; if S+17 != 1 { save D1/A0/A1;
//  create mutex through 0x60030659 with the same packet as the boot initializer; restore; on success S+20=id, S+17=1;
//  on failure S+6=0, S+20=0, S+17=2 and done (no redirect) }; validate all four fields; write all four; installed=1;
//  done: restore D0, pop, replay prologue, jmp 0x6017a601.
// Encodings: all confirmed against stock instructions (see HARDWARE-STAGE0-RECORD.md).
// Controls: section 7 not loaded (defer, no mutex); modelled mutex-create failure (disabled, no redirect); foreign field
// (mutex created, nothing written); install; then the 28-edge engine-routed matrix with the hook before every edge.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3ConsolidatedInstallerProof extends OM3RuntimeRedirectProof {
 static final long ST=0xa031e920L,TABLE2=0x607187d0L,MUTEX_CREATE=0x60030659L;
 @Override void prepareResident(Path out)throws Exception {
  super.prepareResident(out);
  byte[] ff122=new byte[122];Arrays.fill(ff122,(byte)0xff);inImage(0x6031ead0L,ff122);
  inImage(0x6031e910L,new byte[]{(byte)0xff,(byte)0xff,(byte)0xff,(byte)0xff});
  byte[] w=new byte[4];put(w,0,0);inImage(0x602153fdL,w);put(w,0,0x60a8f088L);inImage(0x60215407L,w);
  byte[] g=Arrays.copyOfRange(image,(int)(0x602153fbL-0x60021020L),(int)(0x602153fbL-0x60021020L)+16),s=new byte[16];currentProgram.getMemory().getBytes(toAddr(0x602153fbL),s);
  check(Arrays.equals(g,s),"Constructor group restored to stock bytes");
  rl("IMAGE:boot-time mutex initializer and section-4 constructor patch reverted to stock (no new code at boot)");
 }
 byte[] assembleV3(long at,long table)throws Exception{
  // Compact layout (consolidated-installer2 measured 209 B): short exit block right after the entry checks; A3 stays the
  // state base; A0 is the field pointer (saved at entry, restored in the exit block); 'and' sets Z (no cmp); no A3
  // reload after the OS call (its register list [d2,a2] excludes A3). Encodings confirmed against stock instructions.
  java.io.ByteArrayOutputStream b=new java.io.ByteArrayOutputStream();Map<String,Integer> lab=new HashMap<>();List<Object[]> fx=new ArrayList<>();
  java.util.function.Consumer<int[]> x=v->{for(int i:v)b.write(i&255);};
  java.util.function.LongConsumer w=v->{for(int i=0;i<4;i++)b.write((int)(v>>>(8*i))&255);};
  java.util.function.BiConsumer<Integer,String> br=(op,l)->{fx.add(new Object[]{b.size(),l});b.write(op);b.write(0);};
  x.accept(new int[]{0xcf,0xf0});                                     // movm [d2,d3,a2,a3],(sp)
  x.accept(new int[]{0xfc,0xdf});w.accept(ST);                        // A3 = state base (uncached)
  x.accept(new int[]{0xf8,0x13,0x18,0xf8,0x33,0x78});                 // save D0 (+0x18), A0 (+0x78)
  x.accept(new int[]{0xf8,0x43,0x1c,0xa0,0x01});br.accept(0xc8,"done"); // installed == 1 -> done
  x.accept(new int[]{0xfc,0xa4});w.accept(LOADED);x.accept(new int[]{0xfc,0xe0});w.accept(0x40);br.accept(0xc8,"done"); // section 7 not loaded -> done
  x.accept(new int[]{0xf8,0x43,0x11,0xa0,0x01});br.accept(0xc8,"have"); // mutex already created -> have
  x.accept(new int[]{0xf8,0x17,0x74,0xf8,0x37,0x7c});                 // save D1 (+0x74), A1 (+0x7c)
  x.accept(new int[]{0xf8,0xfe,0xf0,0x80,0x02,0x42,0x04,0x00,0x42,0x08,0x3c,0x50}); // packet (+4)=2, (+8)=0 (same bytes as the boot initializer); A0=sp+4
  int p=b.size();b.write(0xdd);w.accept(MUTEX_CREATE-(at+p));x.accept(new int[]{0xa0,0x10}); // call 0x60030659,[d2,a2],0x10
  x.accept(new int[]{0xf8,0xfe,0x10,0xf8,0x07,0x74,0xf8,0x27,0x7c});  // add 0x10,sp; restore D1, A1
  x.accept(new int[]{0xa0,0x00});br.accept(0xc3,"fail");              // id <= 0 -> fail
  x.accept(new int[]{0xf8,0x13,0x14,0x80,0x01,0xf8,0x53,0x11});br.accept(0xca,"have"); // S+20=id; S+17=1
  lab.put("fail",b.size());
  x.accept(new int[]{0x00,0xf8,0x53,0x06,0xf8,0x13,0x14,0x80,0x02,0xf8,0x53,0x11}); // S+6=0,S+20=0,S+17=2; fall into exit
  // Exit block placed mid-routine so every branch to it is within rel8 range (consolidated-installer3: d=-142).
  lab.put("done",b.size());
  x.accept(new int[]{0xf8,0x03,0x18,0xf8,0x23,0x78});                 // restore D0, A0
  x.accept(new int[]{0xce,0xf0,0xcf,0x20,0xf8,0xfe,0xf8});            // pop; replay movm [a2],(sp); add -0x8,sp
  p=b.size();b.write(0xdc);w.accept(RESUME-(at+p));                    // jmp 0x6017a601
  lab.put("have",b.size());
  x.accept(new int[]{0xfc,0xde});w.accept(table);x.accept(new int[]{0x8f,0x04}); // A2 = table, D3 = 4
  lab.put("v",b.size());
  x.accept(new int[]{0x7a,0xf1,0xe8,0x70,0xf8,0x0a,0x04,0xa8});br.accept(0xc8,"ok"); // A0=field; D0=(A0); == stock -> ok
  x.accept(new int[]{0xf8,0x0a,0x08,0xa8});br.accept(0xc9,"done");    // != wrapper -> done (write nothing)
  lab.put("ok",b.size());
  x.accept(new int[]{0x22,0x0c,0x2b,0xff});br.accept(0xc9,"v");
  x.accept(new int[]{0x22,0xd0,0x8f,0x04});                           // A2 -= 48; D3 = 4
  lab.put("wr",b.size());
  x.accept(new int[]{0x7a,0xf1,0xe8,0xf8,0x0a,0x08,0x68,0x22,0x0c,0x2b,0xff});br.accept(0xc9,"wr"); // (field) = wrapper
  x.accept(new int[]{0x80,0x01,0xf8,0x53,0x1c});br.accept(0xca,"done"); // installed = 1
  byte[] a=b.toByteArray();
  for(Object[] f:fx){int pos=(int)f[0];int d=lab.get((String)f[1])-pos;check(d>=-128&&d<=127,"rel8 range "+f[1]+" d="+d);a[pos+1]=(byte)d;}
  return a;
 }
 void stateLine(String label)throws Exception{rl(String.format("STATE %s S+6=%d S+17=%d S+20=%08x installed=%d",label,u8(ST+6),u8(ST+17),u32(ST+20),u8(INSTALLED)));}
 @Override void redirect()throws Exception {
  if(prepared)return;prepared=true;redirected=true;
  long[][] recs=new long[4][];
  for(int i=0;i<4;i++){long[] r=RECORDS[i];long wrapper=translated(CODE+0x900+128*r[3]);wrapperByEvent.put(r[1],wrapper);
   check(u32(r[0])==r[1],"Stock table record event");e.writeMemoryValue(toAddr(field(r)),4,r[2]);recs[i]=new long[]{field(r),r[2],wrapper};}
  rl("SECTION7-STOCK all four handler fields hold their stock handlers");
  stateLine("after-boot (no boot-time mutex expected)");check(u8(ST+17)==0&&u32(ST+20)==0,"No mutex may exist after boot once the boot hook is removed");
  rl(String.format("INITIAL installed byte=%02x (section-1 padding value; the installer treats only 1 as installed)",u8(INSTALLED)));
  byte[] gap=e.readMemory(toAddr(GAP),(int)(GAP_END-GAP));for(byte v:gap)check((v&255)==0xff,"Freed section-1 gap must be FF");
  byte[] t2=e.readMemory(toAddr(TABLE2),48);for(byte v:t2)check((v&255)==0xff,"Section-2 table area must be FF");
  installer=GAP;byte[] code=assembleV3(installer,TABLE2);installerSize=code.length;
  check(installer+code.length<=GAP_END,String.format("v3 installer must fit the freed gap: %d bytes > %d",code.length,GAP_END-GAP));
  java.nio.ByteBuffer tb=java.nio.ByteBuffer.allocate(48).order(java.nio.ByteOrder.LITTLE_ENDIAN);for(long[] r:recs){tb.putInt((int)r[0]);tb.putInt((int)r[1]);tb.putInt((int)r[2]);}
  e.writeMemory(toAddr(installer),code);e.writeMemory(toAddr(TABLE2),tb.array());
  rl(String.format("PLACEMENT code %08x..%08x (%d of %d B) in section 1; table %08x..%08x (48 B) in section 2",installer,installer+code.length,code.length,GAP_END-GAP,TABLE2,TABLE2+48));
  check(u8(HOOK)==0xcf&&u8(HOOK+1)==0x20&&u8(HOOK+2)==0xf8&&u8(HOOK+3)==0xfe&&u8(HOOK+4)==0xf8,"Stock hook prologue");
  Asm j=new Asm();j.x(0xdc);j.w(installer-HOOK);e.writeMemory(toAddr(HOOK),j.finish());decodeCache.clear();
  Files.writeString(Paths.get(getScriptArgs()[0]).resolve("installer-disasm.txt"),"hook:\n"+disasm(HOOK,5)+"installer:\n"+disasm(installer,installerSize));
  long bits=u32(LOADED);
  // Control 1: section 7 not loaded -> defer, no mutex.
  e.writeMemoryValue(toAddr(LOADED),4,bits&~0x40L);runHook("control-section7-not-loaded");stateLine("c1");
  check(u8(ST+17)==0&&u8(INSTALLED)!=1,"Defer creates no mutex and installs nothing");for(long[] r:RECORDS)check(u32(field(r))==r[2],"Fields stock while deferred");
  e.writeMemoryValue(toAddr(LOADED),4,bits|0x40L);rl("FIXTURE:section-7 loaded bit set (image bytes present; loader not run by harness)");
  // Control 2: modelled mutex-create failure -> feature disabled, no redirect.
  rejectCreate=true;runHook("control-mutex-create-failure");stateLine("c2");
  check(u8(ST+17)==2&&u8(ST+6)==0&&u32(ST+20)==0&&u8(INSTALLED)!=1,"Create failure disables the feature and installs nothing");
  for(long[] r:RECORDS)check(u32(field(r))==r[2],"Fields stock after create failure");
  e.writeMemoryValue(toAddr(ST+6),1,1);rl("FIXTURE:feature-enabled byte S+6 restored to 1 (profileInit setting) after the failure control");
  // Control 3: foreign field -> mutex created (retry), nothing written.
  e.writeMemoryValue(toAddr(field(RECORDS[2])),4,0x12345678L);runHook("control-one-field-not-stock");stateLine("c3");
  long id=u32(ST+20);check(u8(ST+17)==1&&id!=0&&mutexes.containsKey(id)&&!mutexes.get(id),"Retry creates the dedicated mutex");
  check(u8(INSTALLED)!=1,"Not installed with a foreign field");for(int i:new int[]{0,1,3})check(u32(field(RECORDS[i]))==RECORDS[i][2],"Validate-first, field "+i);
  // Install.
  e.writeMemoryValue(toAddr(field(RECORDS[2])),4,RECORDS[2][2]);int next=objectID;runHook("install");stateLine("install");
  check(u8(INSTALLED)==1&&u32(ST+20)==id&&objectID==next,"Install: no second mutex, installed set");
  for(int i=0;i<4;i++)check(u32(field(RECORDS[i]))==recs[i][2],"Installed wrapper field "+i);
  rl("CONSOLIDATED: mutex created at first use; redirect installed in RAM; no boot-time code; section 7 unchanged");
 }
}
