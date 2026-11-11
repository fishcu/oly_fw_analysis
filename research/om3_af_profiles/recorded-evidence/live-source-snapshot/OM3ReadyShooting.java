// Continue with explicitly bounded OS heap/create models, never replace UI gates.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.program.model.address.Address;
public class OM3ReadyShooting extends OM3ShootingRuntime {
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary shooting runtime probe mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  long[] entries={0x610b9197L,0x610b962aL,0x610b9653L,0x610b96f0L},ev={HP,AP,AR,HR};
  for(int i=0;i<4;i++){profileInit(6,out);try{heap=0x70010000L;objectID=1000;setting(0x56b1,0,0);setting(0x56c1,0,0);byteAt(0x62a88d58L,0);setting(0x6782,0,0);setting(0xf1c1,0,0);e.writeMemoryValue(toAddr(0xa31f2030L),4,0);e.writeMemoryValue(toAddr(0xa31f2034L),2,0);e.writeMemory(toAddr(0xa31f203cL),new byte[0x2cec]);e.writeMemoryValue(toAddr(0xa31f4d28L),4,0);runNative(0x60405865L,0xb0,0xc);runNative(0x603f215aL,0xb0,0xc);runNative(0x60aea281L,0,0);e.writeMemory(toAddr(0x62b76554L),new byte[0xb50]);e.writeRegister("A0",0x62b503c8L);runNative(0x60b8879aL,0,0);e.writeMemoryValue(toAddr(0x60369ad4L),4,0x62b503c8L);e.writeMemoryValue(toAddr(0x6036ee80L),4,0);
   long obj=0x700b4000L,ctx=0x700b5000L,machine=0x700b6000L;e.writeMemoryValue(toAddr(machine+0xac),4,0x5100);e.writeMemoryValue(toAddr(machine+0xb8),4,0x5a05);e.writeRegister("A0",machine);e.writeRegister("A1",ctx);runNative(0x610b9eb7L,0xf0,0x18);e.writeMemoryValue(toAddr(obj),4,ev[i]);e.writeMemoryValue(toAddr(ctx+0xc4),4,0x5a05);e.writeMemoryValue(toAddr(ctx+0xbc),4,0x5100);long address=CODE+0x900;e.writeMemory(toAddr(address),wrapper(address,ev[i],entries[i]));e.writeRegister("A0",obj);e.writeRegister("A1",ctx);e.writeRegister("D0",ev[i]);e.writeRegister("D1",0);trace.clear();
   e.setMemoryFaultHandler(new MemoryFaultHandler(){public boolean uninitializedRead(Address a,int n,byte[] d,int o){String s="MISSING-RUNTIME-READ:pc="+e.getExecutionAddress()+":address="+a+":size="+n;trace.add(s);throw new IllegalStateException(s);}public boolean unknownAddress(Address a,boolean w){throw new IllegalStateException("UNKNOWN:"+a+":"+w);}});
   try{runNative(address,0,0);results.add("RETURNED original handler "+Long.toHexString(entries[i])+" under heap/create models and supplied shooting context; downstream AF completion not asserted");}catch(Exception ex){results.add("BOUNDARY original handler "+Long.toHexString(entries[i])+" with bounded OS heap/create models: "+ex);}
   Files.write(out.resolve("ready-shooting-trace-"+i+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("ready-shooting-results.txt"),results);for(String r:results)println(r);
 }
}
