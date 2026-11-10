// Negative tests: do not treat failed kernel waits as successful transitions.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3NativeFaults extends OM3NativeHooks {
 int failedMask=0;
 @Override boolean external(long t)throws Exception{
  if(t==0x60890a0dL&&!worker&&reg("D1")==failedMask&&failedMask!=0){trace.add("INJECTED-WAIT-FAILURE:"+failedMask);e.writeRegister("D0",1);return true;}
  return super.external(t);
 }
 void raw(long ev)throws Exception{e.writeRegister("D0",ev);runNative(CODE,0,0);}
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  int tx=currentProgram.startTransaction("Temporary negative-test mapping; discarded read-only");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  try{for(int fault=0;fault<4;fault++){failedMask=0;profileInit(6,out);try{event(0,6,false,false);event(HP,6,true,false);byte[] before=e.readMemory(toAddr(0xa33ca384L),14);
   if(fault==0)e.writeMemoryValue(toAddr(0xa33ca314L),2,0);
   if(fault==1)e.writeMemoryValue(toAddr(0xa33ca2b8L),2,0x3000);
   if(fault==2)failedMask=16;
   if(fault<3){long address=CODE+0x900;e.writeMemory(toAddr(address),wrapper(address,AP,0x610b962aL));breakpoints=Set.of(0x610b962aL);hitBreakpoint=0;runNative(address,0,0);check(hitBreakpoint==0,"Rejected transition forwarded original focus handler");check(u8(S+5)==(fault<2?1:2),"Stop/gate error status");check(Arrays.equals(before,e.readMemory(toAddr(0xa33ca384L),14)),"Profile changed after failed prerequisite");}
   else {event(AP,6,true,true);failedMask=8;raw(AR);check(u8(S+5)==3&&u8(0xa33a1d10L)==0,"Uncompleted start accepted");}
   results.add("PASS injected fault="+fault+": "+new String[]{"target update denied; original AF-ON handler withheld","target state 0x3000; original AF-ON handler withheld","stop wait returns failure before worker runs; cache unchanged and original AF-ON handler withheld","start wait returns failure before worker runs; native controller records start failure"}[fault]);Files.write(out.resolve("native-fault-trace-"+fault+".txt"),trace);
  }finally{breakpoints=Set.of();e.dispose();}}
  Files.write(out.resolve("native-fault-results.txt"),results);println("NATIVE FAULTS: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("native-fault-results.txt"),results);Files.write(out.resolve("native-fault-last-trace.txt"),trace);Files.writeString(out.resolve("native-fault-failure.txt"),ex.toString());throw ex;}
 }
}
