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
 final List<String> afLog=new ArrayList<>();final Deque<Long> lockIds=new ArrayDeque<>();
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
  if(t==0x60075f73L||t==0x60075fbcL){
   // Stock lock pair (649 callers), disassembled 7 Nov: take(D0=lock id) disables dispatch only when it is not
   // already disabled, raises interrupt level D0 via 6004f63f, and ORs 0x80000000 into the result if it disabled
   // dispatch; release(D0=saved) restores PSW via 6004f660 and re-enables dispatch only if bit 31 is set.
   // Nesting different lock ids is therefore legitimate. Model: LIFO stack of ids; outermost take returns bit 31,
   // nested takes return 0. 6004f63f is not a spinlock: it raises PSW interrupt-mask level (bits 8-10) to D0 only
   // if the current level is lower and returns the old PSW; 6004f660 restores PSW. Re-taking a level is a no-op.
   long pc=e.getExecutionAddress().getOffset();
   if(t==0x60075f73L){long id=reg("D0");
    lockIds.push(id);e.writeRegister("D0",lockIds.size()==1?0x80000000L:0);trace.add(String.format("MODEL:stock-lock-take id=%x depth=%d",id,lockIds.size()));return true;}
   check(!lockIds.isEmpty(),"Stock lock release without take pc="+Long.toHexString(pc));long saved=reg("D0");
   check(((saved>>>31)&1)==(lockIds.size()==1?1:0),String.format("Stock lock release flag/depth mismatch saved=%x depth=%d pc=%08x",saved,lockIds.size(),pc));
   long id=lockIds.pop();trace.add(String.format("MODEL:stock-lock-release id=%x depth=%d",id,lockIds.size()));return true;}
  if(t==0x50002909L){
   // Imported memcpy (D0=n, A0=dst, A1=src). The shared model rejects n==0; standard memcpy semantics make a
   // zero-length copy a no-op (reached from vector-grow 60b2e8bf copying an empty old array). Other cases defer
   // to the shared model after logging their arguments.
   long n=reg("D0"),dst=reg("A0"),src=reg("A1");
   if(n==0){log(String.format("MODEL:memcpy-zero-length-no-op pc=%08x dst=%08x src=%08x",e.getExecutionAddress().getOffset(),dst,src));return true;}
   if(!(n<=0x10000&&dst!=0&&src!=0))log(String.format("MODEL:memcpy-out-of-contract pc=%08x n=%x dst=%08x src=%08x",e.getExecutionAddress().getOffset(),n,dst,src));
  }
  if(!taskStack.isEmpty()&&taskStack.peek()==95){
   long pc=e.getExecutionAddress().getOffset();
   if(pc==0x6031792cL)log(String.format("AF-CMD-DISPATCH:command=%x handler=%08x request=%s",u32(reg("A0")+8),t,hex(reg("A0"),16)));
   if(t==0x60318ce2L)log(String.format("AF-CMD-COMMON-REPLY:D0=%08x D1=%08x A0=%08x A1=%08x",reg("D0"),reg("D1"),reg("A0"),reg("A1")));
  }
  return super.external(t);
 }
 // Router state-12 handler 60db3dca (run7 instrumentation, observation only). The handler fetches the current
 // message object (A0+0x68 via 60dd9d65) and calls its vtable+8 with D0=0x17 then D0=0x1b; a nonzero 0x17 result
 // takes the notstart path, a nonzero 0x1b result promotes the requested backend (60db3d96), otherwise the default
 // 60db3b09 runs. Results are read at the cmp following each call; nothing is written.
 final Map<String,Integer> state12=new TreeMap<>();long s12Router;
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc==0x60db3dcaL){s12Router=reg("A0");long m=0;String vt="?",f8="?",body="?";
   try{m=u32(s12Router+0x68);if(m!=0){vt=String.format("%08x",u32(m));f8=String.format("%08x",u32(u32(m)+8));body=hex(m,0x20);}}catch(RuntimeException ex){}
   String k="msg="+String.format("%08x",m)+" vtable="+vt+" isA="+f8;state12.merge(k,1,Integer::sum);
   log(String.format("STATE12-ENTER:router=%08x state=%d active=%08x requested=%08x %s body=%s task=%s",s12Router,u32(s12Router+0xb4),u32(s12Router+0xb8),u32(s12Router+0xbc),k,body,taskStack.isEmpty()?"caller":taskStack.peek()));}
  if(pc==0x60db3de8L)log(String.format("STATE12-ISA:type=0x17 result=%08x",reg("D0")));
  if(pc==0x60db3e28L)log(String.format("STATE12-ISA:type=0x1b result=%08x",reg("D0")));
  if(pc==0x60db3e2cL)log("STATE12-PATH:activate-requested-backend(60db3d96)");
  if(pc==0x60db3dfbL)log("STATE12-PATH:notstart(60db3048)");
  if(pc==0x60db3e36L)log("STATE12-PATH:default(60db3b09)");
  if(pc==0x60db3e3eL)log(String.format("STATE12-RETURN:D0=%08x",reg("D2")));
  return super.instruction(ins);
 }
 // Stock static-constructor group 602153e6: 13 constructors from ROM table 0x60718770 (count 0x34 bytes), run by
 // the stock section loader 60045f44 at 60046020. They build the memory-pool objects registered at 0x606e21a0 that
 // the connection's free-memory query 605423e3 dereferences. Run natively, before the reset scenario, because the
 // section loader runs before UI initialization. Disable with system property om3.noPoolCtors for the baseline.
 Object poolCtorsEmulator;
 // Per-emulator reset of the capture-chain model state inherited from the parent probes. Those fields were never
 // cleared between the four original-handler iterations (each a fresh emulator), so iteration 1 skipped the stock
 // hook-table publisher 6004cfd9 and task-207 scheduling and failed at 6004d286. Earlier probes never passed
 // iteration 0, so this carry-over had not been exercised before.
 @Override void init(){
  super.init();
  messageBuffers.clear();mbfQueue.clear();flagAttr.clear();dispatchDisabled=false;
  staticMbf=false;inTask207=false;task207Ran=false;guard=false;hookTablesInit=false;
  dtqCapacity.clear();dtq.clear();linkLock=false;inPort2=false;port2Ran=false;staticDtq=false;
  timedOut=false;infoReports=0;
  taskStack.clear();lockIds.clear();
  afLog.add("MODEL:per-emulator-capture-state-reset");
 }
 @Override void beforeOriginal()throws Exception {
  lockIds.clear();
  if(poolCtorsEmulator!=e&&System.getProperty("om3.noPoolCtors")==null){
   poolCtorsEmulator=e;check(u32(0x602153f2L)==0x60718770L,"Stock constructor-table fingerprint 602153f2");
   log("STOCK-INIT:running static-constructor group 602153e6 (13 entries, ROM table 60718770)");
   Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(ghidra.program.model.lang.Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
   long oldTop=stackTop;stackTop=0x700ec000L;boolean old=dispatching;dispatching=true;
   try{runNative(0x602153e6L,0xa0,0xc);}finally{dispatching=old;stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
   StringBuilder v=new StringBuilder();for(int i=0;i<0x77;i++){long p=u32(0x606e21a4L+i*8L);if(p!=0){String vt;try{vt=String.format("%08x",u32(p));}catch(RuntimeException ex){vt="unprovided";}v.append(String.format("%x:%08x->%s ",i,p,vt));}}
   log("STOCK-INIT:pool-registry vtables "+v);
  }
  super.beforeOriginal();
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);
  try{super.run();}finally{
   Files.write(out.resolve("af-task-log.txt"),afLog);
   String k=Files.exists(out.resolve("kernel-model-outcome.txt"))?Files.readString(out.resolve("kernel-model-outcome.txt")).trim():"(no kernel-model outcome)";
   StringBuilder s=new StringBuilder("AF-COMMAND-TASK PROBE (stock-reset scenario, silent SCPU; not a normal boot)\n");
   s.append("task runs: ").append(taskRuns).append('\n');
   try{s.append(String.format("connection state=%d backend=%08x requested=%08x\n",u32(0x62b7315cL+0xb4),u32(0x62b7315cL+0xb8),u32(0x62b7315cL+0xbc)));}catch(Exception ex){s.append("connection state unreadable: "+ex+"\n");}
   s.append("state-12 handler entries: ").append(state12).append("\n");
   s.append("terminal outcome: ").append(k).append('\n');
   s.append("No reply, status or AF completion was supplied; see af-task-log.txt for every queue 94/95/96/99 exchange.\n");
   Files.writeString(out.resolve("af-task-outcome.txt"),s.toString());println(s.toString());
  }
 }
}
