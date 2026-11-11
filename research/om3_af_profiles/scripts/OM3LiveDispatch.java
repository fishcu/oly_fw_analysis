// Schedule the actual native queued main-thread message, never invent an AF reply.
// Kernel task scheduling and task IDs are explicit models; native pop/dispatch run.
// @category OM3
import java.util.*;
import ghidra.program.model.lang.Register;
public class OM3LiveDispatch extends OM3LiveQueueTrace {
 boolean dispatching=false;long observedQueue;int dispatched;
 @Override void init(){super.init();dispatching=false;observedQueue=0;dispatched=0;}
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  if(ins.getAddress().getOffset()==0x60b2ecbdL)trace.add(String.format("NATIVE-RESPONSE-STATUS-MAP input=%08x",reg("D0")));
  if(ins.getAddress().getOffset()==0x60dda6eeL)observedQueue=reg("A0");
  return super.instruction(ins);
 }
 @Override void afterOriginal()throws Exception {
  super.afterOriginal();
  int owner=u8(OWN+4);if(owner==1||owner==2)check(Arrays.equals(e.readMemory(toAddr(u32(OWN+8)),10),e.readMemory(toAddr(0xa33ca384L),10)),"Original handler disturbed owned target cache");
  if(owner==2)check(u8(0x62a6a0ebL)==0,"Original AF-ON handler re-enabled Subject Detect");
  trace.add("CHECK:scheduled-original-return:owner="+owner+":effective-subject="+u8(0x62a6a0ebL)+":native-dispatches="+dispatched);
 }
 long scheduled(long entry,long a0,long a1,int mask,int frame)throws Exception {
  Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
  long oldTop=stackTop;stackTop=0x70050000L;
  try{e.writeRegister("A0",a0);e.writeRegister("A1",a1);runNative(entry,mask,frame);return reg(entry==0x60dda845L?"A0":"D0");}
  finally{stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x60031299L){long id=reg("D0")&65535;check(semaphores.remove(id)!=null,"Deleting unknown response semaphore");e.writeRegister("D0",0);trace.add("MODEL:owned-response-semaphore-delete:"+id);return true;}
  if(dispatching&&t==0x6003193eL){e.writeMemoryValue(toAddr(reg("A0")),2,2);e.writeRegister("D0",0);return true;}
  if(t==0x60037769L&&!dispatching){
   long id=reg("D0");long[] sem=semaphores.get(id);
   if(sem!=null&&sem[0]==0&&observedQueue!=0){
    check(observedQueue==0x62b7659cL,"Unidentified main-thread queue");check(dispatched<32,"Native response task made no bounded progress");dispatching=true;
    try{
     for(int round=0;round<8&&sem[0]==0;round++){
      long job=scheduled(0x60dda845L,observedQueue-8,0,0x30,0xc);if(job==0){trace.add("SCHEDULED:native-main-thread-queue-empty");break;}
      trace.add(String.format("SCHEDULED:native-main-thread-pop job=%08x id=%04x",job,u16(job+4)));
      scheduled(0x60dda369L,0x62b76554L,job,0,0);dispatched++;
      trace.add("SCHEDULED:native-main-thread-dispatch-returned:response-count="+sem[0]);
     }
    }finally{dispatching=false;}
   }
  }
  return super.external(t);
 }
}
