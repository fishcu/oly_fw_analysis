// Materialize complete core-0 ROM object tables before tasks run, and retain
// each AF task's native loop context across own-queue idle waits.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CompleteStaticOSConsumerProof extends OM3OriginalButtonConsumerProof {
 final Map<Long,Map<String,java.math.BigInteger>> afContexts=new HashMap<>();
 @Override void init(){super.init();afContexts.clear();}
 void initializeStaticOS()throws Exception {
  super.loadStaticMessageBuffers();super.loadStaticDataQueues();
  for(int i=0;i<142;i++){
   long r=0x6003a214L+16*i,id=u32(r),attr=u32(r+4),initial=u32(r+8),maximum=u32(r+12);
   check(id>0&&id<=146&&attr<=1&&initial<=maximum&&maximum>0&&maximum<65536,"ROM semaphore descriptor");
   semaphores.putIfAbsent(id,new long[]{initial,maximum});
  }
  check(u32(0x6003aaf4L)==0,"ROM semaphore terminator");
  for(int i=0;i<294;i++)loadStaticFlags(u32(0x6003ab34L+12*i));
  check(u32(0x6003b8fcL)==0,"ROM event-flag terminator");
  for(int i=0;i<242;i++){
   long r=0x6003bab4L+20*i,id=u32(r),max=u32(r+8),capacity=u32(r+12);
   check(id>0&&id<=257&&u32(r+4)<=1&&max>0&&max<=capacity&&capacity<0x100000&&u32(r+16)==0,"ROM message-buffer descriptor");
   messageBuffers.putIfAbsent(id,new long[]{max,capacity,0});
  }
  check(u32(0x6003cd9cL)==0,"ROM message-buffer terminator");
  check(eventFlags.containsKey(197L),"AF worker clear target197 must exist before its first clear");
  trace.add("MODEL:complete-core0-ROM-objects semaphores142 flags294 data-queues5 message-buffers242; initial values preserved; no device completion supplied");
 }
 @Override void coreFixture()throws Exception {initializeStaticOS();super.coreFixture();}
 @Override void runStockTask(long[] t)throws Exception {
  var caller=saveRegisters();long oldTop=stackTop;stackTop=t[4];taskStack.push(t[0]);taskRuns.merge(t[0],1,Integer::sum);
  try{
   var context=afContexts.get(t[0]);
   if(context==null){log("MODEL:first-persistent-AF-task-entry queue="+t[0]);runNative(t[1],(int)t[2],(int)t[3]);}
   else{restoreRegisters(context);log("MODEL:resume-persistent-AF-task queue="+t[0]);continueNative(stackTop,0x70fff000L);}
   throw new Exception("Unexpected AF task return queue="+t[0]);
  }catch(TaskIdle idle){afContexts.put(t[0],saveRegisters());log("MODEL:persistent-AF-task-idle queue="+t[0]);}
  catch(Exception ex){consumerNote(String.format("AF-TASK-BOUNDARY queue=%d pc=%08x error=%s",t[0],e.getExecutionAddress().getOffset(),ex));throw ex;}
  finally{taskStack.pop();stackTop=oldTop;restoreRegisters(caller);}
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);String scope="Complete ROM core0 object tables: semaphores142, flags294, data queues5, message buffers242. Initial patterns/counts are ROM values, not completions. AF tasks retain native idle contexts; no restart of worker initialization at each job.\n";
   Files.writeString(out.resolve("complete-static-os-model.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
