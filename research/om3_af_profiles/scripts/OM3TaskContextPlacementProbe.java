// Load the final task-context layout through the stock uncompressed section loader.
// Proposed component bytes exist only in memory; no firmware image/checksum repair is emitted.
// @category OM3
import java.nio.file.*;
import java.util.*;
import java.security.MessageDigest;
public class OM3TaskContextPlacementProbe extends OM3TaskContextMutexProof {
 final List<String> placement=new ArrayList<>();
 void note(String s){placement.add(s);println(s);}
 String hash(byte[] b)throws Exception{return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(b));}
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String outcome="NOT RUN";
  int tx=currentProgram.startTransaction("Temporary placement probe mapping");
  try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_placement_probe",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}
  finally{currentProgram.endTransaction(tx,true);}
  profileInit(6,out);
  try{
   heap=0x70010000L;objectID=1000;prepareResident(out);
   byte[] stock=Files.readAllBytes(Paths.get("analysis/decoded/00_0100_50000020.decoded.bin"));
   List<long[]> spans=new ArrayList<>();List<String> reasons=new ArrayList<>();
   for(long[] b:blocks){spans.add(new long[]{b[1],b[2]});reasons.add("placed feature block from "+Long.toHexString(b[0]));}
   spans.add(new long[]{DATA,0x1b0});reasons.add("initial feature state (uncached at runtime)");
   for(long a:new long[]{0x603cedfeL,0x609b3bb2L}){spans.add(new long[]{a,5});reasons.add("existing feature entry/accessor trampoline");}
   ensureLen=assembleEnsure(ENSURE).length;installer=ENSURE+ensureLen;byte[] ins=assembleV4(installer,TABLE2);v4Len=ins.length;installerSize=v4Len;
   check(installer+v4Len<=GAP_END,"Ensure and installer fit gap");
   inImage(ENSURE,assembleEnsure(ENSURE));inImage(installer,ins);
   spans.add(new long[]{ENSURE,ensureLen+v4Len});reasons.add("task-context ensure and interrupt-only table installer");
   java.nio.ByteBuffer tb=java.nio.ByteBuffer.allocate(48).order(java.nio.ByteOrder.LITTLE_ENDIAN);
   for(long[] r:RECORDS){long wrap=translated(CODE+0x900+128*r[3]);wrapperByEvent.put(r[1],wrap);tb.putInt((int)field(r)).putInt((int)r[2]).putInt((int)wrap);
    byte[] w=new byte[4];put(w,0,r[2]);inImage(field(r),w);e.writeMemoryValue(toAddr(field(r)),4,r[2]);}
   inImage(TABLE2,tb.array());spans.add(new long[]{TABLE2,48});reasons.add("runtime redirect descriptors; section 7 remains stock");
   Asm j=new Asm();j.x(0xdc);j.w(installer-HOOK);inImage(HOOK,j.finish());spans.add(new long[]{HOOK,5});reasons.add("key-port interrupt callback trampoline");
   List<String> csv=new ArrayList<>();csv.add("component_offset,runtime_address,stock_byte,proposed_byte,reason");int count=0;
   for(int i=0;i<image.length;i++)if(image[i]!=stock[i]){
    long a=0x60021020L+i;int owner=-1;
    for(int k=0;k<spans.size();k++){long[] s=spans.get(k);if(a>=s[0]&&a<s[0]+s[1]){check(owner<0,"Overlapping planned spans at "+Long.toHexString(a));owner=k;}}
    check(owner>=0,"Unexplained proposed byte at "+Long.toHexString(a));
    check((a>=0x60134000L&&a<0x6031f000L)||(a>=0x603ba800L&&a<0x60718800L)||(a>=0x60828000L&&a<0x60a8f800L),"Change outside uncompressed sections 1/2/4");
    csv.add(String.format("%08x,%08x,%02x,%02x,%s",i,a,stock[i]&255,image[i]&255,reasons.get(owner)));count++;
   }
   check(Arrays.equals(Arrays.copyOfRange(stock,(int)(SEC7_LO-0x60021020L),(int)(SEC7_HI-0x60021020L)),Arrays.copyOfRange(image,(int)(SEC7_LO-0x60021020L),(int)(SEC7_HI-0x60021020L))),"Section 7 stock-identical");
   for(long[] s:spans)for(long[] other:spans)if(s!=other)check(s[0]+s[1]<=other[0]||other[0]+other[1]<=s[0],"Placement spans overlap");
   Files.write(out.resolve("proposed-changed-bytes.csv"),csv);
   note("Stock decoded SHA256="+hash(stock));note("Proposed in-memory decoded SHA256="+hash(image));note("Changed bytes="+count+"; every byte justified; all changes confined to uncompressed sections 1/2/4; section 7 stock-identical; checksums not repaired; no image emitted");
   load(1,0xa5);load(4,0x55); // load(4) first loads section 2, with whole-section identity checks
   check(Arrays.equals(e.readMemory(toAddr(ENSURE),ensureLen),assembleEnsure(ENSURE)),"Loaded ENSURE exact");
   check(Arrays.equals(e.readMemory(toAddr(installer),v4Len),ins),"Loaded installer exact");
   check(Arrays.equals(e.readMemory(toAddr(TABLE2),48),tb.array()),"Loaded table exact");
   check(Arrays.equals(e.readMemory(toAddr(HOOK),5),j.finish()),"Loaded hook exact");
   check(u8(ST+17)==0&&u32(ST+20)==0&&u8(INSTALLED)!=1,"No boot mutex or installed marker");
   for(long[] r:RECORDS)check(u32(field(r))==r[2],"No preinstalled section-7 redirect");
   long bits=u32(LOADED);runHook("native-loaded-without-section7");check(u8(INSTALLED)!=1,"Defers before section 7");
   e.writeMemoryValue(toAddr(LOADED),4,bits|0x40);note("FIXTURE:section-7 decoded bytes already supplied; bit 6 set explicitly (compressed loader not run)");
   runHook("native-loaded-install");check(u8(INSTALLED)==1&&taskCreates==0&&ectx==0,"IRQ installs without OS create");
   for(long[] r:RECORDS)check(u32(field(r))==wrapperByEvent.get(r[1]),"Runtime field redirects exact");
   int before=objectID;runNative(ENSURE,0xf0,0x14);check(reg("D0")==1&&taskCreates==1&&objectID==before+1,"Loaded task ensure creates once");
   runNative(ENSURE,0xf0,0x14);check(reg("D0")==1&&taskCreates==1&&objectID==before+1,"Loaded ready ensure reuses mutex");
   outcome="PASS proposed byte diff, disjoint placement, native sections 1/2/4 whole-load identity, deferred IRQ install, runtime redirect and task-context create-once; no normal-boot/hardware/packaging proof";
  }catch(Exception ex){outcome="BOUNDARY at "+e.getExecutionAddress()+": "+ex;}
  Files.writeString(out.resolve("placement-outcome.txt"),outcome+"\n");Files.write(out.resolve("placement-evidence.txt"),placement);Files.write(out.resolve("runtime-redirect-log.txt"),rlog);Files.write(out.resolve("placement-trace.txt"),trace);
  println(outcome);e.dispose();
 }
}
