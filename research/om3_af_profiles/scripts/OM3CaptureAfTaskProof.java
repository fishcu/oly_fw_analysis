// Continuation of OM3CaptureResetProof (labelled STOCK-RESET scenario, SCPU modelled as silent).
// The carry-fixed reset run stops when the connection sends queue-95 command 0x1d and then waits forever on
// its reply buffer (1032), because no receiver task for queue 95 is scheduled. This probe applies the same
// pattern the harness already uses for task 207 and the port-2 task: when a caller would block on an empty
// message buffer, a stock task loop that serves a queue holding pending messages is run natively from its
// entry, in its own saved register context and stack, until it goes idle on its own queue.
//   queue 95 -> AF-command task 0x6031787e (ROM halfword 0x60043232; prologue movm [a2,a3], add -0x14)
//   queue 94 -> AF worker task  0x609df84d (ROM halfword 0x60043230; prologue movm [d2,a2,a3], add -0x14)
// Tasks may nest (a scheduled task's own blocking receive may schedule another). A task that is already on the
// nested context stack is never re-entered. A zero-timeout receive on an empty buffer returns -50 (polling
// timeout, as the event-flag model does). No reply, status or AF success is synthesized: every reply that
// arrives is produced by stock code. Every queue 94/95/96/99 send and receive is logged.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CaptureAfTaskProof extends OM3CaptureResetProof {
 // {queue id, entry, movm mask, frame, stack top}
 static final long[][] TASKS={{95,0x6031787eL,0x30,0x14,0x700fc000L},{94,0x609df84dL,0xb0,0x14,0x700f4000L}};
 final Deque<Long> taskStack=new ArrayDeque<>();final Map<Long,Integer> taskRuns=new LinkedHashMap<>();
 final List<String> afLog=new ArrayList<>();
 static boolean afQueue(long id){return id==94||id==95||id==96||id==99;}
 long[] servedBy(long q){for(long[] t:TASKS)if(t[0]==q)return t;return null;}
 void log(String s){trace.add(s);afLog.add(s);}
 String hex(long a,int n){try{return HexFormat.of().formatHex(e.readMemory(toAddr(a),n));}catch(RuntimeException ex){return "unprovided";}}
 void runStockTask(long[] t)throws Exception {
  Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(ghidra.program.model.lang.Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
  long oldTop=stackTop;stackTop=t[4];taskStack.push(t[0]);taskRuns.merge(t[0],1,Integer::sum);
  log(String.format("MODEL:scheduling-stock-task queue=%d entry=%08x run=%d nesting=%d",t[0],t[1],taskRuns.get(t[0]),taskStack.size()));
  try{runNative(t[1],(int)t[2],(int)t[3]);throw new Exception(String.format("Stock task for queue %d returned",t[0]));}
  catch(TaskIdle idle){log(String.format("MODEL:stock-task-quiescent queue=%d",t[0]));}
  finally{taskStack.pop();stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
 }
 boolean schedulePending()throws Exception {
  for(long[] t:TASKS){
   if(taskStack.contains(t[0]))continue;
   if(mbfQueue.getOrDefault(t[0],new ArrayDeque<>()).isEmpty())continue;
   runStockTask(t);return true;}
  return false;
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x60037598L){long id=reg("D0")&0xffff;if(afQueue(id)||id>218)log(String.format("AF-TASK-SEND:mbf=%d size=%d pc=%08x task=%s bytes=%s",id,reg("D1"),e.getExecutionAddress().getOffset(),taskStack.isEmpty()?"caller":taskStack.peek(),hex(reg("A0"),(int)Math.min(reg("D1"),32))));}
  if(t==0x6003727eL){
   long id=reg("D0")&0xffff,tmo=reg("D1");
   if(messageBuffers.containsKey(id)&&mbfQueue.getOrDefault(id,new ArrayDeque<>()).isEmpty()){
    // Own-queue idle: the innermost scheduled task waits for new work on the queue it serves.
    if(!taskStack.isEmpty()&&taskStack.peek()==id){log(String.format("MODEL:stock-task-idle-on-own-queue:%d",id));throw new TaskIdle();}
    // A blocking caller lets pending stock work run, repeatedly, until its message arrives or nothing is pending.
    if(tmo!=0){int rounds=0;while(mbfQueue.getOrDefault(id,new ArrayDeque<>()).isEmpty()&&rounds<16&&schedulePending())rounds++;}
    if(mbfQueue.getOrDefault(id,new ArrayDeque<>()).isEmpty()&&tmo==0){e.writeRegister("D0",0xffffffceL);log(String.format("MODEL:message-buffer-poll-timeout:id=%d",id));return true;}
   }
   if(afQueue(id)||id>218)log(String.format("AF-TASK-RECEIVE-ATTEMPT:mbf=%d timeout=%08x pending=%d task=%s",id,tmo,mbfQueue.getOrDefault(id,new ArrayDeque<>()).size(),taskStack.isEmpty()?"caller":taskStack.peek()));
  }
  if(!taskStack.isEmpty()&&taskStack.peek()==95){
   long pc=e.getExecutionAddress().getOffset();
   if(pc==0x6031792cL)log(String.format("AF-CMD-DISPATCH:command=%x handler=%08x request=%s",u32(reg("A0")+8),t,hex(reg("A0"),16)));
   if(t==0x60318ce2L)log(String.format("AF-CMD-COMMON-REPLY:status=%04x reply-mbf=%s",reg("D0")&0xffff,hex(u32(reg("A1")+0x154),4)));
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);
  try{super.run();}finally{
   Files.write(out.resolve("af-task-log.txt"),afLog);
   String k=Files.exists(out.resolve("kernel-model-outcome.txt"))?Files.readString(out.resolve("kernel-model-outcome.txt")).trim():"(no kernel-model outcome)";
   StringBuilder s=new StringBuilder("AF-COMMAND-TASK PROBE (stock-reset scenario, silent SCPU; not a normal boot)\n");
   s.append("task runs: ").append(taskRuns).append('\n');
   s.append(String.format("connection state=%d backend=%08x requested=%08x\n",u32(0x62b7315cL+0xb4),u32(0x62b7315cL+0xb8),u32(0x62b7315cL+0xbc)));
   s.append("terminal outcome: ").append(k).append('\n');
   s.append("No reply, status or AF completion was supplied; see af-task-log.txt for every queue 94/95/96/99 exchange.\n");
   Files.writeString(out.resolve("af-task-outcome.txt"),s.toString());println(s.toString());
  }
 }
}
