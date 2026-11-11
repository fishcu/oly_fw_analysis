// Isolated installer/ensure controls before the full shooting startup.
// OS create remains modeled; no camera or native AF completion is supplied.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3TaskContextMutexProbe extends OM3TaskContextMutexProof {
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc>=GAP&&pc<0x6031f000L)trace.add(String.format("MUTEX-STEP %08x sp=%08x mdr=%08x D0=%08x A3=%08x %s",pc,reg("SP"),reg("MDR"),reg("D0"),reg("A3"),ins));
  return super.instruction(ins);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String result="NOT RUN";
  int tx=currentProgram.startTransaction("Temporary mutex probe mapping");
  try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_mutex_probe",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}
  finally{currentProgram.endTransaction(tx,true);}
  profileInit(6,out);
  try{
   heap=0x70010000L;objectID=1000;prepareResident(out);load(1,0xa5);load(4,0x55);coreFixture();
   redirect();
   check(ectx==1&&taskCreates==0,"Controls completed without successful feature create");
   String[] rs={"D2","D3","A2","A3"};long[] vals={0x71234560L,0x72345670L,0x73456780L,0x74567890L};
   for(int i=0;i<rs.length;i++)e.writeRegister(rs[i],vals[i]);
   int before=objectID;
   runNative(ENSURE,0xf0,0x14);
   check(reg("D0")==1&&taskCreates==1&&objectID==before+1&&u8(ST+17)==1&&u32(ST+20)>0,"First task ensure creates once");
   for(int i=0;i<rs.length;i++)check(reg(rs[i])==vals[i],"ENSURE callee-saved "+rs[i]);
   runNative(ENSURE,0xf0,0x14);
   check(reg("D0")==1&&taskCreates==1&&objectID==before+1,"Ready ensure does not create again");
   for(int i=0;i<rs.length;i++)check(reg(rs[i])==vals[i],"Ready ENSURE callee-saved "+rs[i]);
   runHook("post-ensure-fast-path");check(taskCreates==1&&ectx==1,"Installed IRQ fast path performs no create");
   result="PASS isolated controls c0-c3, task-context create-once, ready fast path, callee-saved registers and root stack; no full matrix or hardware claim";
  }catch(Exception ex){result="BOUNDARY at "+e.getExecutionAddress()+": "+ex;}
  Files.writeString(out.resolve("mutex-probe-outcome.txt"),result+"\n");Files.write(out.resolve("runtime-redirect-log.txt"),rlog);Files.write(out.resolve("mutex-probe-trace.txt"),trace);
  println(result);e.dispose();
 }
}
