// Reproduce retry behavior after a failed wait, without granting fake completion.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3RecoveryAudit extends OM3NativeFaults {
 List<String> delayed=new ArrayList<>();
 @Override boolean external(long t)throws Exception{
  if(t==0x600760f9L){delayed.add("deferred-timer:"+Long.toHexString(reg("A0")));e.writeRegister("D0",0);return true;}
  return super.external(t);
 }
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary recovery audit mapping; read-only discard");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  for(int fault:new int[]{16,8}){failedMask=0;delayed.clear();profileInit(6,out);try{
   event(0,6,false,false);event(HP,6,true,false);if(fault==8)event(AP,6,true,true);
   failedMask=fault;raw(fault==16?AP:AR);check(u8(0xa33a1c18L)==(fault==16?2:1),"Missing uncompleted command");raw(AR);
   check(!delayed.isEmpty()&&u8(0xa33a1c94L)==(fault==16?2:1),"Retry did not use replacement slot");
   results.add("REPRODUCED prior prototype: failed wait mask="+fault+", subsequent release submits again while original command remains pending; replacement kind="+u8(0xa33a1c94L)+", deferred timers="+delayed.size());Files.write(out.resolve("recovery-before-trace-"+fault+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("recovery-before-results.txt"),results);for(String r:results)println(r);
 }
}
