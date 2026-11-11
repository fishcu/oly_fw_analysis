// Continue with explicitly bounded OS heap/create models, never replace UI gates.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.program.model.address.Address;
public class OM3ShootingRuntime extends OM3NativeHooks {
 long heap=0x70010000L;int objectID=1000;
 @Override boolean external(long t)throws Exception{
  if(t==0x60023fe6L){long n=reg("D0");check(n>0&&n<=0x10000&&heap+n<0x70040000L,"Heap contract "+n);long p=heap;heap=(heap+n+15)&~15L;e.writeMemory(toAddr(p),new byte[(int)n]);e.writeRegister("A0",p);trace.add("MODEL:heap:"+Long.toHexString(p)+":"+n);return true;}
  if(t==0x60030659L||t==0x600306f1L||t==0x60030363L){e.writeRegister("D0",objectID++);trace.add("MODEL:kernel-create:"+Long.toHexString(t));return true;}
  if(t==0x60038b8aL){e.writeRegister("D0",0);trace.add("MODEL:not-interrupt-context");return true;}
  if(t==0x6003193eL){check(reg("A0")>=0x70000000L&&reg("A0")<0x70100000L,"Task-ID output contract");e.writeMemoryValue(toAddr(reg("A0")),2,1);e.writeRegister("D0",0);trace.add("MODEL:current-task=1");return true;}
  if(t==0x60032312L){e.writeRegister("D0",0);trace.add("MODEL:uncontended-mutex-acquire");return true;}
  if(t==0x6003791bL){e.writeRegister("D0",0);trace.add("MODEL:uncontended-mutex-release");return true;}
  return super.external(t);
 }
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary shooting runtime probe mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  long[] entries={0x610b9197L,0x610b962aL,0x610b9653L,0x610b96f0L},ev={HP,AP,AR,HR};
  for(int i=0;i<4;i++){profileInit(6,out);try{heap=0x70010000L;objectID=1000;runNative(0x60405865L,0xb0,0xc);runNative(0x603f215aL,0xb0,0xc);e.writeMemory(toAddr(0x62b76554L),new byte[0xb50]);e.writeRegister("A0",0x62b503c8L);runNative(0x60b8879aL,0,0);e.writeMemoryValue(toAddr(0x60369ad4L),4,0x62b503c8L);e.writeMemoryValue(toAddr(0x6036ee80L),4,0);
   long obj=0x700b4000L,ctx=0x700b5000L;e.writeMemoryValue(toAddr(obj),4,ev[i]);e.writeMemoryValue(toAddr(ctx+0xc4),4,0x5a05);e.writeMemoryValue(toAddr(ctx+0xbc),4,0x5100);long address=CODE+0x900;e.writeMemory(toAddr(address),wrapper(address,ev[i],entries[i]));e.writeRegister("A0",obj);e.writeRegister("A1",ctx);e.writeRegister("D0",ev[i]);e.writeRegister("D1",0);trace.clear();
   e.setMemoryFaultHandler(new MemoryFaultHandler(){public boolean uninitializedRead(Address a,int n,byte[] d,int o){String s="MISSING-RUNTIME-READ:pc="+e.getExecutionAddress()+":address="+a+":size="+n;trace.add(s);throw new IllegalStateException(s);}public boolean unknownAddress(Address a,boolean w){throw new IllegalStateException("UNKNOWN:"+a+":"+w);}});
   try{runNative(address,0,0);results.add("RETURNED original handler "+Long.toHexString(entries[i])+" under heap/create models and supplied shooting context; downstream AF completion not asserted");}catch(Exception ex){results.add("BOUNDARY original handler "+Long.toHexString(entries[i])+" with bounded OS heap/create models: "+ex);}
   Files.write(out.resolve("shooting-runtime-trace-"+i+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("shooting-runtime-results.txt"),results);for(String r:results)println(r);
 }
}
