// Explore original shooting bodies; explicitly record unsupported runtime boundaries.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.program.model.address.Address;
public class OM3ShootingContinuation extends OM3NativeHooks {
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  int tx=currentProgram.startTransaction("Temporary shooting probe mapping; discarded read-only");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  long[] entries={0x610b9197L,0x610b962aL,0x610b9653L,0x610b96f0L};long[] events={HP,AP,AR,HR};
  for(int i=0;i<entries.length;i++){profileInit(6,out);try{
   e.writeRegister("A0",0x62b503c8L);runNative(0x60b8879aL,0,0);e.writeMemoryValue(toAddr(0x60369ad4L),4,0x62b503c8L);e.writeMemoryValue(toAddr(0x6036ee80L),4,0);
   long obj=0x700b4000L,ctx=0x700b5000L;e.writeMemoryValue(toAddr(obj),4,events[i]);e.writeMemoryValue(toAddr(ctx+0xc4),4,0x5a05);e.writeMemoryValue(toAddr(ctx+0xbc),4,0x5100);
   long address=CODE+0x900;e.writeMemory(toAddr(address),wrapper(address,events[i],entries[i]));e.writeRegister("A0",obj);e.writeRegister("A1",ctx);e.writeRegister("D0",events[i]);e.writeRegister("D1",0);trace.clear();
   e.setMemoryFaultHandler(new MemoryFaultHandler(){public boolean uninitializedRead(Address a,int n,byte[] data,int offset){String s="MISSING-RUNTIME-READ:pc="+e.getExecutionAddress()+":address="+a+":size="+n;trace.add(s);throw new IllegalStateException(s);}public boolean unknownAddress(Address a,boolean write){throw new IllegalStateException("UNKNOWN-ADDRESS:"+a+":write="+write);}});
   try{runNative(address,0,0);results.add("RETURNED original handler "+Long.toHexString(entries[i])+"; synthetic context, not full stock initialization");}
   catch(Exception ex){results.add("BOUNDARY original handler "+Long.toHexString(entries[i])+": "+ex);}
   Files.write(out.resolve("shooting-continuation-trace-"+i+".txt"),trace);
   if(i==0){List<String> methods=new ArrayList<>();methods.add(e.getClass().getProtectionDomain().getCodeSource().toString());for(var m:e.getClass().getMethods())if(m.getName().toLowerCase().contains("fault")||m.getName().toLowerCase().contains("uninit")||m.getName().equals("getEmulator"))methods.add(m.toString());Files.write(out.resolve("emulator-fault-api.txt"),methods);}
  }finally{e.dispose();}}
  Files.write(out.resolve("shooting-continuation-results.txt"),results);for(String r:results)println(r);
 }
}
