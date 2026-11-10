// Revised controller: finite states plus actual native deferred callback delivery.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3RevisionCoverage extends OM3RevisedProfiles {
 boolean injectReentry=false,reentrySeen=false;
 @Override boolean external(long t)throws Exception{
  if(injectReentry&&t==0x60890a0dL&&!worker){injectReentry=false;child(RECONCILE,0);check(u8(S+5)==6,"Nested call not rejected");reentrySeen=true;}
  return super.external(t);
 }
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary revised coverage mapping; read-only discard");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  try{for(int focus:new int[]{0,2})for(int scp=0;scp<=6;scp++){profileInit(scp,out);try{
   setting(0xc021,0,focus);byteAt(0xa33f2c9dL,focus);event(0,scp,false,false);
   for(int state=0;state<4;state++)for(int edge=0;edge<4;edge++){
    event(HR,scp,false,u8(S+1)==1);event(AR,scp,false,false);boolean half=(state&1)!=0,on=(state&2)!=0;if(half)event(HP,scp,true,false);if(on)event(AP,scp,half,true);
    if(edge==0)half=true;else if(edge==1)half=false;else if(edge==2)on=true;else on=false;event(new long[]{HP,HR,AP,AR}[edge],scp,half,on);check(settings.get(0xc0210000L)==focus&&u8(0xa33f2c9dL)==focus,"Shared focus setting changed");
   }
   results.add("PASS revised controller all 16 state/event edges: SCP="+scp+", focus="+focus+"; distinct kernel event-ID fixture");
  }finally{e.dispose();}}
  for(int scp=1;scp<=6;scp++){profileInit(scp,out);try{event(0,scp,false,false);event(HP,scp,true,false);
   long command=0x700b6000L;e.writeMemory(toAddr(command),new byte[124]);byteAt(command,3);byteAt(command+12,scp);e.writeRegister("A0",command);runNative(0x60841102L,0xb0,0x28);check(!callbacks.isEmpty(),"Missing competing pending command");
   event(AP,scp,true,true);check(timerDeliveries>0&&timers.isEmpty()&&callbacks.isEmpty(),"Native deferred retry was not delivered");
   results.add("PASS competing class-change submission precedes AF-ON stop, SCP="+scp+"; actual native deferred timer callback, retry dispatcher, FIFO and worker drain complete in order");Files.write(out.resolve("deferred-native-trace-"+scp+".txt"),trace);
  }finally{e.dispose();}}
  profileInit(6,out);try{event(0,6,false,false);event(HP,6,true,false);injectReentry=true;event(AP,6,true,true);check(reentrySeen&&u8(S+7)==0,"Reentry guard recovery");results.add("PASS actual nested native reconcile during parent wait is rejected; parent completes with correct held/profile state and releases its guard");Files.write(out.resolve("reentrant-native-trace.txt"),trace);}finally{e.dispose();}
  Files.write(out.resolve("revised-coverage-results.txt"),results);println("REVISED COVERAGE: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("revised-coverage-results.txt"),results);Files.write(out.resolve("revised-coverage-last-trace.txt"),trace);Files.writeString(out.resolve("revised-coverage-failure.txt"),ex.toString());throw ex;}
 }
}
