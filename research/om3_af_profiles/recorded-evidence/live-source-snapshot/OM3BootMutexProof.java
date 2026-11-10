// Dedicated mutex initialization through the native section-4 constructor loop.
// OS object creation is an explicit model. No installable firmware is emitted.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3BootMutexProof extends OM3FullShooting {
 static final long INIT=0x6031ead0L,TABLE=0x6031e910L;
 boolean rejectCreate=false;
 @Override boolean external(long t)throws Exception {
  if(t==0x60030659L&&rejectCreate){rejectCreate=false;e.writeRegister("D0",0xffffffdeL);trace.add("MODEL:mutex-create-resource-exhaustion");return true;}
  return super.external(t);
 }
 byte[] initializer()throws Exception {
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0);a.load8(S+17);a.x(0xa0,1);a.eq("done");
  a.imm(0,0);a.x(0x42,4,0x42,8);a.imm(0,2);a.x(0xf8,0x92,4,0x3c,0x50);callAt(a,INIT,0x60030659L,0xa0,0x10);
  a.x(0xa0,0,0xc2,7);a.jump("failure");a.x(0xa0,0);a.eq("failure");store32(a,S+20);a.imm(0,1);a.store8(S+17);a.jump("done");
  a.label("failure");a.imm(0,0);store32(a,S+20);a.imm(0,2);a.store8(S+17);
  a.label("done");a.x(0xdf,0xf0,0x30);return a.finish();
 }
 @Override void prepareResident(Path out)throws Exception {
  super.prepareResident(out);byte[] init=absoluteData(initializer(),INIT);check(INIT+init.length<=0x6031f000L,"Initializer extent");
  for(long[] span:new long[][]{{INIT,init.length},{TABLE,4}}){byte[] stock=new byte[(int)span[1]];currentProgram.getMemory().getBytes(toAddr(span[0]),stock);for(byte v:stock)check((v&255)==255,"Initializer is not in inspected padding");}
  byte[] entry=new byte[4];put(entry,0,INIT);inImage(TABLE,entry);inImage(INIT,init);
  // Exact stock instruction fingerprints, before replacing their immediates.
  check(java.util.HexFormat.of().formatHex(Arrays.copyOfRange(image,(int)(0x602153fbL-0x60021020L),(int)(0x602153fbL-0x60021020L)+6)).equals("fcce00000000"),"Stock constructor count fingerprint");
  check(java.util.HexFormat.of().formatHex(Arrays.copyOfRange(image,(int)(0x60215405L-0x60021020L),(int)(0x60215405L-0x60021020L)+6)).equals("fcde88f0a860"),"Stock constructor table fingerprint");
  byte[] word=new byte[4];put(word,0,4);inImage(0x602153fdL,word);put(word,0,TABLE);inImage(0x60215407L,word);
  Files.write(out.resolve("boot-mutex-initializer.emulator-only.bin"),init);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary boot mutex mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  for(boolean fail:new boolean[]{false,true}){profileInit(6,out);try{objectID=1000;prepareResident(out);load(1,0xa5);load(4,0x55);rejectCreate=fail;runNative(0x602153fbL,0xa0,0xc);
   check(u8(DATA+17)==(fail?2:1)&&u8(DATA+6)==0,"Initialization status/disabled default");long id=u32(DATA+20);check(fail?id==0:mutexes.containsKey(id)&&!mutexes.get(id),"Dedicated mutex ownership");
   results.add("PASS native constructor loop after whole section loads: mutex creation "+(fail?"failure leaves feature disabled and records error":"success records a dedicated owned mutex, feature remains disabled")+"; OS create service modeled");
   if(!fail){int next=objectID;runNative(0x602153fbL,0xa0,0xc);check(objectID==next&&u32(DATA+20)==id,"Repeated constructor leaked mutex");results.add("PASS repeated native constructor loop is idempotent, mutex ID retained");}
   else {runNative(0x602153fbL,0xa0,0xc);check(u8(DATA+17)==1&&mutexes.containsKey(u32(DATA+20)),"Failed initialization cannot retry");results.add("PASS native constructor retry after modeled resource failure");}
   Files.write(out.resolve("boot-mutex-trace-"+fail+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("boot-mutex-results.txt"),results);println("BOOT MUTEX: "+results.size()+" PASS; whole boot and OS scheduling excluded");
 }
}
