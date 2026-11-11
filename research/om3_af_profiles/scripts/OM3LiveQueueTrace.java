// Observe actual native queue producers at the original-handler response boundary.
// Does not consume jobs or supply synthetic positive replies.
// @category OM3
import java.util.*;
public class OM3LiveQueueTrace extends OM3LiveShooting {
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  if(ins.getAddress().getOffset()==0x60dda6eeL){
   long queue=reg("A0"),job=reg("A1");trace.add(String.format("NATIVE-ENQUEUE queue=%08x job=%08x jobBytes=%s",queue,job,java.util.HexFormat.of().formatHex(e.readMemory(toAddr(job),48))));
  }
  return super.instruction(ins);
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x60037769L){long[] sem=semaphores.get(reg("D0"));if(sem!=null&&sem[0]==0)trace.add(String.format("WAIT-CONTEXT id=%d A0=%08x A1=%08x A2=%08x A3=%08x",reg("D0"),reg("A0"),reg("A1"),reg("A2"),reg("A3")));}
  return super.external(t);
 }
}
