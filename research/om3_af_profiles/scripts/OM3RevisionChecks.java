// Validate concrete fixes, including delayed native callback completion.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3RevisionChecks extends OM3RevisedProfiles {
 void expected(boolean half,boolean on,int mode)throws Exception{check(u8(S)==(half?1:0)&&u8(S+1)==(on?1:0)&&u8(S+5)==0&&u8(S+7)==0,"Held/error/lock state");check(u8(S+4)==(on?2:half?1:0)&&u8(0x62a6a0ebL)==mode,"Owner/effective mode");check(u8(0xa33a1d10L)==(mode==0?0:1),"Worker state");check(Arrays.equals(e.readMemory(toAddr(0xa33ca384L),10),e.readMemory(toAddr(BANKS+(on?0x100:0)+16*u8(S+16)),10)),"Active captured profile");}
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary revision mapping; read-only discard");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  try{for(int mode=1;mode<=6;mode++)for(int fault:new int[]{16,8}){profileInit(mode,out);try{
   revisedEvent(0);revisedEvent(HP);if(fault==8)revisedEvent(AP);failedMask=fault;revisedEvent(fault==16?AP:AR);int queued=callbacks.size();check(u8(S+5)==(fault==16?2:3),"Injected failure missing");
   revisedEvent(AR);check(u8(S+5)==4&&callbacks.size()==queued&&timers.isEmpty()&&u8(0xa33a1c94L)==0,"Retry resubmitted pending work");
   failedMask=0;drain();revisedEvent(0);expected(true,false,mode);check(callbacks.isEmpty()&&timers.isEmpty()&&u32(0x62f757d0L)==0,"Recovery not quiescent");
   results.add("PASS class="+mode+", failed wait="+fault+": release does not resubmit pending command; original late completion and explicit reconcile restore latest held profile");Files.write(out.resolve("revised-recovery-trace-"+mode+"-"+fault+".txt"),trace);
  }finally{e.dispose();}}
  profileInit(6,out);try{revisedEvent(0);revisedEvent(HP);
   byte[] before=e.readMemory(toAddr(0xa33ca384L),10);targetSettings(0);setting(0x88b2,0,600);captureStock(0,0);revisedEvent(0);expected(true,false,6);check(!Arrays.equals(before,e.readMemory(toAddr(0xa33ca384L),10))&&u16(0xa33ca384L)==600,"Movement ignored");
   results.add("PASS native capture and same-owner reconciliation apply moved target frame 600 while half remains held");
   revisedEvent(AP);targetSettings(0);setting(0x88b2,0,100);captureStock(1,1);byteAt(S+16,1);revisedEvent(0);expected(true,true,0);check(u16(0xa33ca384L)==100,"Orientation bank ignored");
   byteAt(S+16,0);revisedEvent(0);expected(true,true,0);check(u16(0xa33ca384L)==526,"Orientation bank restoration");results.add("PASS separately captured orientation banks select/restore native target records; orientation event adapter is a supplied input");
   byteAt(S+7,1);byte[] held=e.readMemory(toAddr(S),2);revisedEvent(HR);check(u8(S+5)==6&&Arrays.equals(held,e.readMemory(toAddr(S),2)),"Reentrant admission changed active held state");byteAt(S+7,0);revisedEvent(HR);expected(false,true,0);results.add("PASS busy admission rejects reentrant entry without changing held state; caller retry succeeds after owner releases the guard");
   Files.write(out.resolve("revised-config-trace.txt"),trace);
  }finally{e.dispose();}
  Files.write(out.resolve("revised-results.txt"),results);println("REVISED CHECKS: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("revised-results.txt"),results);Files.write(out.resolve("revised-last-trace.txt"),trace);Files.writeString(out.resolve("revised-failure.txt"),ex.toString());throw ex;}
 }
}
