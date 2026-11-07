// Continue with explicitly bounded OS heap/create models, never replace UI gates.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.app.util.PseudoInstruction;
import ghidra.app.util.PseudoDisassembler;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.program.model.address.Address;
public class OM3FullShooting extends OM3GuardedResident {
 long heap=0x70010000L;int objectID=1000,nativeInstructionLimit=2000000;
 Map<Long,Long> eventFlags=new HashMap<>();Map<Long,Boolean> mutexes=new HashMap<>();
 Map<Long,long[]> semaphores=new HashMap<>();Map<Long,Long> allocations=new HashMap<>();
 Long factory(long key,long index)throws Exception {
  Long found=null;
  long[][] ranges={{0,0x8d0,0x6062555cL,0x605f6d90L},{10000,71,0x606279b2L,0x605f90d0L},{15000,456,0x60627aceL,0x605f91ecL}};
  for(long[] r:ranges)for(int i=0;i<r[1];i++)if(u16(r[2]+4*i)==key&&u16(r[2]+4*i+2)==index){long v=u32(r[3]+4*i);check(found==null||found==v,"Conflicting factory aliases for "+Long.toHexString(key));found=v;}
  if(found==null){for(long[] table:new long[][]{{0x600b8f54L,0x600bb5e0L,544},{0x600e4becL,0x6011fe20L,1215}}){long p=table[0];int records=0;while(p<table[1]){int k=u16(p),n=u16(p+2),size=(k&3)==0?4:k&3;check(k!=0&&n<65536,"Core runtime default table");if(k==key&&index<n){byte[] raw=e.readMemory(toAddr(p+4+index*size),size);long v=0;for(int j=0;j<size;j++)v|=(raw[j]&255L)<<(8*j);if((k&8)!=0&&size==1)v=(byte)v;else if((k&8)!=0&&size==2)v=(short)v;found=v&0xffffffffL;}p=(p+4+(long)n*size+3)&~3L;records++;}check(p==table[1]&&records==table[2],"Core defaults extent");}}
  return found;
 }
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {long pc=ins.getAddress().getOffset();if(pc==0x60b2e356L){long p=reg("A1");trace.add("TRANSACTION:packet="+Long.toHexString(p)+":id="+Integer.toHexString(u16(p+4))+":enable="+u32(p+32)+":kind="+u32(p+36)+":context="+u32(p+40)+":owner="+u8(ownedState()+4)+":effective-subject="+u8(0x62a6a0ebL));}if(pc==0x6108ae0eL)trace.add("POLICY-CHECK-RETURN:"+reg("D0"));return super.instruction(ins);}
 @Override boolean external(long t)throws Exception {
  if(t==0x60063356L&&reg("D0")!=0x194)return false;
  if(t==0x60023fe6L){long n=reg("D0");check(n>0&&n<=0x10000&&heap+n<0x70040000L,"Heap contract");long p=heap;heap=(heap+n+15)&~15L;allocations.put(p,n);e.writeMemory(toAddr(p),new byte[(int)n]);e.writeRegister("A0",p);trace.add("MODEL:owned-allocation:"+Long.toHexString(p)+":"+n);return true;}
  if(t==0x60024018L){long p=reg("A0");check(allocations.remove(p)!=null,"Free of unowned/already-freed allocation "+Long.toHexString(p));trace.add("MODEL:owned-free:"+Long.toHexString(p));return true;}

  if(t==0x60b337c8L&&reg("D0")==0x1e){e.writeRegister("D0",1);trace.add("MODEL:physical-LLPSW-not-pressed");return true;}
  if(t==0x600306f1L){long cfg=reg("A0"),count=u32(cfg+4),maximum=u32(cfg+8);check(maximum>0&&count<=maximum&&maximum<65536,"Semaphore create contract");long id=objectID++;semaphores.put(id,new long[]{count,maximum});e.writeRegister("D0",id);trace.add("MODEL:semaphore-create:"+id+":"+count+":"+maximum);return true;}
  if(t==0x60037769L){long id=reg("D0");long[] sem=semaphores.get(id);check(sem!=null,"Unknown semaphore "+id);check(sem[0]>0,"Semaphore would block id="+id+", timeout="+Long.toHexString(reg("D1")));sem[0]--;e.writeRegister("D0",0);trace.add("MODEL:semaphore-take:"+id);return true;}
  if(t==0x60035febL&&semaphores.containsKey(reg("D0"))){long id=reg("D0");long[] sem=semaphores.get(id);check(sem[0]<sem[1],"Semaphore overflow");sem[0]++;e.writeRegister("D0",0);trace.add("MODEL:semaphore-give:"+id);return true;}
if(t==0x50002909L){long n=reg("D0"),dst=reg("A0"),src=reg("A1");check(n>0&&n<=0x10000&&dst!=0&&src!=0,"ROM copy contract");e.writeMemory(toAddr(dst),e.readMemory(toAddr(src),(int)n));trace.add("MODEL:ROM-byte-copy:"+n);return true;}if(t==0x60063380L&&!settings.containsKey((reg("D0")<<16)|reg("D1"))){Long value=factory(reg("D0"),reg("D1"));check(value!=null,"No factory default for "+Long.toHexString(reg("D0"))+"["+reg("D1")+"]");trace.add("MODEL:stock-factory-setting:"+Long.toHexString(reg("D0"))+":"+reg("D1")+"="+value);e.writeRegister("D0",value);return true;}if(t==0x50002900L){e.writeRegister("D0",0);trace.add("MODEL:hardware-table-selector=0");return true;}if(t==0x60030659L){long id=objectID++;mutexes.put(id,false);e.writeRegister("D0",id);trace.add("MODEL:owned-mutex-create:"+id);return true;}if(t==0x60030363L){long id=objectID++,cfg=reg("A0");check((u8(cfg)&0xf8)==0,"Event flag attributes");eventFlags.put(id,u32(cfg+4));e.writeRegister("D0",id);trace.add("MODEL:owned-eventflag-create:"+id);return true;}if(t==0x60035ee7L){long id=reg("D0")&0xffff;check(eventFlags.containsKey(id),"Unknown event flag "+id);long value=eventFlags.get(id)|reg("D1");eventFlags.put(id,value);e.writeRegister("D0",0);trace.add("MODEL:eventflag-set:"+id+":"+Long.toHexString(value));return true;}
  if(t==0x60038b8aL){e.writeRegister("D0",0);return true;}
  if(t==0x6003193eL){check(reg("A0")>=0x70000000L&&reg("A0")<0x70100000L,"Task-ID output contract");e.writeMemoryValue(toAddr(reg("A0")),2,1);e.writeRegister("D0",0);return true;}
  if(t==0x60032312L||t==0x6003791bL){long id=reg("D0")&0xffff;check(mutexes.containsKey(id),"Unknown mutex "+id);boolean take=t==0x60032312L;check(mutexes.get(id)!=take,"Mutex would block/unowned release "+id);mutexes.put(id,take);e.writeRegister("D0",0);trace.add("MODEL:owned-uncontended-mutex:"+id+":"+take);return true;}
  return super.external(t);}
 @Override void init(){super.init();semaphores.clear();allocations.clear();eventFlags.clear();mutexes.clear();
  // Stock entry 60021020 calls 60021466(628ac700,a3410088). The helper
  // zeros that physical BSS range through the uncached alias. Mirror both
  // aliases explicitly; this is power-on memory, not whole-camera boot.
  byte[] zeros=new byte[0x63410088-0x628ac700];
  e.writeMemory(toAddr(0x628ac700L),zeros);e.writeMemory(toAddr(0xa28ac700L),zeros);for(int i=0;i<8;i++)e.writeMemoryValue(toAddr(0x97000000L+0x40*i),1,0); // Explicit uncontended hardware semaphore register fixture.
 }
 void coreFixture()throws Exception{for(long table:new long[]{0x60095584L,0x600b8f54L,0x600bb5ecL,0x600bda78L,0x600e4becL}){e.writeRegister("A0",table);e.writeRegister("A1",0);e.writeRegister("D0",0xa32a990cL);runNative(0x60062536L,0xf0,0x30);}}
 long ownedState(){return DATA;}
 void beforeOriginal()throws Exception{}
 void afterOriginal()throws Exception{}
 @Override public void run()throws Exception{shootingRun();}
 void shootingRun()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary shooting runtime probe mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  long[] entries={0x610b9197L,0x610b962aL,0x610b9653L,0x610b96f0L},ev={HP,AP,AR,HR};
  for(int i=0;i<4;i++){profileInit(6,out);try{heap=0x70010000L;objectID=1000;prepareResident(out);load(1,0xa5);load(4,0x55);byteAt(ownedState()+6,1);coreFixture();runNative(0x60471a7fL,0xe0,0x20);setting(0x3851,0,2);setting(0x9321,0,0);setting(0x8f31,0,0);setting(0x8601,0,0);e.writeMemoryValue(toAddr(0xa32c9c58L),2,1);e.writeMemoryValue(toAddr(0xa32c9c5aL),1,1);setting(0x56b1,0,0);setting(0x56c1,0,0);byteAt(0x62a88d58L,0);setting(0x6782,0,0);setting(0xf1c1,0,0);e.writeMemoryValue(toAddr(0xa31f2030L),4,0);e.writeMemoryValue(toAddr(0xa31f2034L),2,0);e.writeMemory(toAddr(0xa31f203cL),new byte[0x2cec]);e.writeMemoryValue(toAddr(0xa31f4d28L),4,0);runNative(0x60405865L,0xb0,0xc);runNative(0x603f215aL,0xb0,0xc);runNative(0x60aea281L,0,0);runNative(0x60b2f82bL,0,0);runNative(0x60dbdc5eL,0,0);runNative(0x60415df1L,0,0);runNative(0x601778b6L,0,4);e.writeMemory(toAddr(0x62b76554L),new byte[0xb50]);e.writeRegister("A0",0x62b503c8L);runNative(0x60b8879aL,0,0);e.writeMemoryValue(toAddr(0x60369ad4L),4,0x62b503c8L);e.writeMemoryValue(toAddr(0x6036ee80L),4,0);
   long obj=0x700b4000L,ctx=0x700b5000L,machine=0x700b6000L;e.writeMemoryValue(toAddr(machine+0xac),4,0x5100);e.writeMemoryValue(toAddr(machine+0xb8),4,0x5a05);e.writeRegister("A0",machine);e.writeRegister("A1",ctx);runNative(0x610b9eb7L,0xf0,0x18);e.writeMemoryValue(toAddr(obj),4,ev[i]);e.writeMemoryValue(toAddr(ctx),4,ev[i]);e.writeMemoryValue(toAddr(ctx+0xc4),4,0x5a05);e.writeMemoryValue(toAddr(ctx+0xbc),4,0x5100);long address=translated(CODE+0x900+128*new int[]{0,2,3,1}[i]);e.writeRegister("A0",obj);e.writeRegister("A1",ctx);e.writeRegister("D0",ev[i]);e.writeRegister("D1",0);beforeOriginal();e.writeRegister("A0",obj);e.writeRegister("A1",ctx);e.writeRegister("D0",ev[i]);e.writeRegister("D1",0);trace.clear();
   e.setMemoryFaultHandler(new MemoryFaultHandler(){public boolean uninitializedRead(Address a,int n,byte[] d,int o){String s="MISSING-RUNTIME-READ:pc="+e.getExecutionAddress()+":address="+a+":size="+n;trace.add(s);throw new IllegalStateException(s);}public boolean unknownAddress(Address a,boolean w){throw new IllegalStateException("UNKNOWN:"+a+":"+w);}});
   try{runNative(address,0,0);afterOriginal();results.add("RETURNED original handler "+Long.toHexString(entries[i])+" under heap/create models and supplied shooting context; downstream AF completion not asserted");}catch(Exception ex){results.add("BOUNDARY original handler "+Long.toHexString(entries[i])+" with bounded OS heap/create models, pc="+Long.toHexString(e.getExecutionAddress().getOffset())+": "+ex);}
   Files.write(out.resolve("full-shooting-trace-"+i+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("full-shooting-results.txt"),results);for(String r:results)println(r);
 }
 void runNative(long entry,int mask,int frame)throws Exception{
  long top=stackTop,stop=0x70fff000L,p=top;e.writeMemoryValue(toAddr(top),4,stop);
  String[] rs={"D2","D3","A2","A3"};int[] bits={128,64,32,16};
  for(int i=0;i<4;i++)if((mask&bits[i])!=0){p-=4;e.writeMemoryValue(toAddr(p),4,reg(rs[i]));}
  e.writeRegister("SP",top-frame);e.writeRegister("MDR",stop);e.writeRegister("PC",entry);
  PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  for(int i=0;i<nativeInstructionLimit;i++){
   long pc=e.getExecutionAddress().getOffset();observedStackLow=Math.min(observedStackLow,reg("SP"));if(pc==stop){check(reg("SP")==top,"Root stack did not restore");return;}if(breakpoints.contains(pc)){hitBreakpoint=pc;return;}
   PseudoInstruction ins=decodeCache.get(pc);if(ins==null){ins=dis.disassemble(toAddr(pc),e.readMemory(toAddr(pc),16));check(ins!=null,"Decode "+Long.toHexString(pc)+" bytes="+java.util.HexFormat.of().formatHex(e.readMemory(toAddr(pc),16)));decodeCache.put(pc,ins);}
   if(instruction(ins))continue;
   if(ins.getMnemonicString().startsWith("udf"))throw new Exception("Opaque instruction "+Long.toHexString(pc)+" "+ins);
   if(ins.getFlowType().isCall()){
    long t=callTarget(ins);
    if(external(t)){e.writeRegister("MDR",pc+ins.getLength());e.writeRegister("PC",pc+ins.getLength());continue;}
    trace.add("native-call:"+Long.toHexString(t));
   }
   check(e.step(monitor),"Native failure "+Long.toHexString(pc)+": "+e.getLastError());
  }throw new Exception("Native bound exceeded");
 }
}
