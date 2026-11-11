// Dedicated mutex spans reconciliation and the original button handler.
// Original-handler effects and RTOS scheduling are explicit boundaries in ABI tests.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3SerializedProfiles extends OM3BootMutexProof {
 static final long SECOND=0x6031ec00L,SOURCES=CODE+0x2000;
 boolean probeOriginal=false,delayProgress=true;int originalCalls=0,delays=0;
 long[] expectedRegisters;String[] registers={"D0","D1","D2","D3","A0","A1","A2","A3"};
 @Override long translated(long p){for(int i=0;i<4;i++)if(p==CODE+0x900+128*i)return super.translated(SOURCES+512*i);return super.translated(p);}
 void volatileStore(Asm a){a.x(0x42,4,0x46,8,0x43,12,0x47,16);}
 void volatileRestore(Asm a){a.x(0x58,4,0x59,8,0x5c,12,0x5d,16);}
 void inputs(Asm a){volatileRestore(a);a.x(0x5a,44,0x5b,40,0x5e,36,0x5f,32);}
 @Override byte[] wrapper(long address,long event,long original)throws Exception {
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0);volatileStore(a);
  a.load8(S+6);a.x(0xa0,1);a.ne("stock");a.load8(S+17);a.x(0xa0,1);a.ne("reject");
  load32(a,S+20);callAt(a,address,0x60032312L,0xf0,0x14);a.x(0xa0,0);a.ne("reject");a.imm(2,16);
  a.label("retry");a.imm(0,event);callAt(a,address,RECONCILE,0,0);a.load8(S+5);a.x(0xa0,0);a.eq("original");a.x(0xa0,4);a.ne("unlockReject");
  a.x(0x2a,0xff,0xaa,0);a.eq("exhausted");a.imm(0,1);callAt(a,address,0x60031581L,0xb0,0x10);a.jump("retry");
  a.label("exhausted");a.imm(0,8);a.store8(S+5);a.label("unlockReject");load32(a,S+20);callAt(a,address,0x6003791bL,0xf0,0x18);a.jump("returnInputs");
  a.label("original");inputs(a);callAt(a,address,original,0,0);volatileStore(a);load32(a,S+20);callAt(a,address,0x6003791bL,0xf0,0x18);a.jump("returnInputs");
  a.label("stock");inputs(a);callAt(a,address,original,0,0);volatileStore(a);a.jump("returnInputs");
  a.label("reject");a.imm(0,9);a.store8(S+5);a.label("returnInputs");volatileRestore(a);a.x(0xf8,0xfe,0x20,0xce,0xf0,0xdf,0,0);return a.finish();
 }
 @Override void pack(Path out)throws Exception {
  int tx=currentProgram.startTransaction("Temporary serialized source decode mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE+0x1000))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_serialized_sources",toAddr(CODE+0x1000),0x3000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  List<Long> origins=new ArrayList<>(Arrays.asList(CODE,RECONCILE,CAPTURE,CODE+0x800,ACCESSOR));List<byte[]> bytes=new ArrayList<>(Arrays.asList(controller(),gatedReconcile(),capture(),guardedMode(),guardedAccessor()));
  for(int i=0;i<4;i++){long origin=SOURCES+512*i;origins.add(origin);bytes.add(wrapper(origin,new long[]{HP,HR,AP,AR}[i],new long[]{0x610b9197L,0x610b96f0L,0x610b962aL,0x610b9653L}[i]));}
  blocks.clear();long p=DEST,primaryEnd=DEST;boolean secondary=false;
  for(int i=0;i<bytes.size();i++){int n=bytes.get(i).length;if(!secondary&&p+n>0x60a8f800L){primaryEnd=p;p=SECOND;secondary=true;}check(p+n<=(secondary?0x6031f000L:0x60a8f800L),"Serialized placement capacity");blocks.add(new long[]{origins.get(i),p,n});byte[] stock=new byte[n];currentProgram.getMemory().getBytes(toAddr(p),stock);for(byte v:stock)check((v&255)==255,"Serialized placement stock fingerprint");p+=n;}
  if(!secondary)primaryEnd=p;packedSize=(int)(primaryEnd-DEST);
  for(int i=0;i<bytes.size();i++){long[] block=blocks.get(i);e.writeMemory(toAddr(block[1]),relocate(bytes.get(i),block[0],block[1]));}
  packedEntry=translated(RECONCILE);packedCapture=translated(CAPTURE);
  for(long[] hook:new long[][]{{0x603cedfeL,translated(CODE+0x800)},{0x609b3bb2L,translated(ACCESSOR)}}){Asm a=new Asm();a.x(0xdc);a.w(hook[1]-hook[0]);e.writeMemory(toAddr(hook[0]),a.finish());}
  decodeCache.clear();List<String> map=new ArrayList<>();for(long[] block:blocks)map.add(String.format("%08x -> %08x length=%d",block[0],block[1],block[2]));Files.write(out.resolve("serialized-relocation-map.txt"),map);
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x60031581L){check(reg("D0")==1,"Unexpected retry delay");delays++;if(delayProgress)drain();e.writeRegister("D0",0);trace.add("MODEL:retry-delay-worker-progress:"+delayProgress);return true;}
  if(probeOriginal&&(t==0x610b9197L||t==0x610b96f0L||t==0x610b962aL||t==0x610b9653L)){
   check(u8(DATA+6)==0||Boolean.TRUE.equals(mutexes.get(u32(DATA+20))),"Original handler entered without dedicated mutex");
   for(int i=0;i<registers.length;i++)check(reg(registers[i])==expectedRegisters[i],"Original input register "+registers[i]);
   e.writeRegister("D0",0x11223344L);e.writeRegister("D1",0x55667788L);e.writeRegister("A0",0x12345678L);e.writeRegister("A1",0x23456789L);originalCalls++;trace.add("MODEL:original-handler-ABI-only:"+Long.toHexString(t));return true;
  }
  return super.external(t);
 }
 void invoke(int button)throws Exception {
  expectedRegisters=new long[8];for(int i=0;i<8;i++){expectedRegisters[i]=0x71000000L+i*0x101;e.writeRegister(registers[i],expectedRegisters[i]);}
  runNative(translated(CODE+0x900+128*button),0,0);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary serialized source mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);if(currentProgram.getMemory().getBlock(toAddr(CODE+0x1000))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_serialized_sources",toAddr(CODE+0x1000),0x3000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  profileInit(6,out);try{prepareResident(out);load(1,0xa5);load(4,0x55);runNative(0x602153fbL,0xa0,0xc);probeOriginal=true;byteAt(DATA+6,1);originalCalls=0;
   for(int button:new int[]{0,2,3,1}){invoke(button);check(originalCalls>0&&!mutexes.get(u32(DATA+20)),"Mutex not released after original");check(reg("D0")==0x11223344L&&reg("D1")==0x55667788L&&reg("A0")==0x12345678L&&reg("A1")==0x23456789L,"Original volatile outputs lost");for(int i:new int[]{2,3,6,7})check(reg(registers[i])==expectedRegisters[i],"Callee-saved register lost");results.add("PASS serialized resident button="+button+": original ABI model sees all eight input registers under dedicated lock; original volatile outputs and caller stack survive unlock; lock released");}
   check(originalCalls==4,"Original handler count");byteAt(DATA+6,0);int before=originalCalls;invoke(2);check(originalCalls==before+1&&!mutexes.get(u32(DATA+20))&&u8(DATA+1)==0,"Disabled wrapper path");results.add("PASS disabled serialized wrapper calls original ABI model without owning mutex or changing held state");
   byteAt(DATA+6,1);
   for(boolean progress:new boolean[]{true,false}){
    long command=0x700b6000L;e.writeMemory(toAddr(command),new byte[124]);byteAt(command,3);byteAt(command+12,6);e.writeRegister("A0",command);runNative(0x60841102L,0xb0,0x28);check(!callbacks.isEmpty(),"Pending native worker command missing");byteAt(DATA+5,2);
    delayProgress=progress;delays=0;before=originalCalls;invoke(2);
    check(!mutexes.get(u32(DATA+20)),"Pending path retained mutex");
    if(progress){check(delays==1&&originalCalls==before+1&&u8(DATA+5)==0&&u8(DATA+4)==2,"Pending original was not resumed exactly once");results.add("PASS pending worker command: wrapper retains original input registers, yields once, drains actual native callback/FIFO/worker, reconciles, invokes original ABI model exactly once under lock, then unlocks");}
    else {check(delays==15&&originalCalls==before&&u8(DATA+5)==8,"Pending retry was not bounded/fail-closed");results.add("PASS worker does not progress: fifteen modeled delay yields, bounded retry reports status 8, original handler is not called with an uncommitted profile, dedicated lock released");delayProgress=true;drain();}
    invoke(3);check(u8(DATA+1)==0&&u8(DATA+5)==0,"Pending-path release recovery");
   }
   Files.write(out.resolve("serialized-profile-results.txt"),results);Files.write(out.resolve("serialized-profile-trace.txt"),trace);println("SERIALIZED PROFILES: "+results.size()+" PASS; contended/reentrant scheduling and original bodies excluded from ABI probe");
  }finally{e.dispose();}
 }
}
