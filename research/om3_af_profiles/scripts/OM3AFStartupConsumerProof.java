// Native AF startup steps and model fixes for the full original-button consumer comparison.
// Same labelled steps as OM3NativeAFModeDiagProbe (which now extends this class), applied in the consumer chain so the
// original buttons run after MODE_START/MODE_UPDATE with the stock AF startup state:
//   Rerun of OM3NativeAFModeProbe (native-af-mode1 stopped on the shared "Task-ID output contract" check).
//   Diagnosis (native-af-mode-diag1): stock 60700fb4 is the AF-command API. Its ROM owner task ID (0x60042da2) is 106,
//   the queue-95 AF-command task. From any other task it takes the cross-task path 6004f3bd, which allocates a request
//   from the native pool (600240ea) and stores the caller's task ID into it through 6003193e with A0 in that pool
//   (observed 0xa3456e84). The inherited task-ID model accepted only stack outputs (0x70000000..0x70100000).
//   Model change (labelled): the same task-ID value the inherited model returns for non-AF tasks (1) may also be written
//   to a pool output that is already provided memory. Unprovided outputs still fail. Every task-ID call is recorded.
//   No AF reply, acknowledgement or worker state is supplied.
//   Diagnosis (native-af-mode-diag3): the forwarded request reaches worker 94, which faults at 609dbd6b reading its
//   context pointer 0xa33f3614 (=0). Its only writer 609db6ab is one of 13 sub-initializers of the AF module init
//   608fe1b0, called only from stock startup task 602188f1 (task table entry 0x60039584) at 6021897f. The harness never
//   runs that task. SUPPLIED-INPUT (labelled): run 608fe1b0 natively once before the mode commands; the task's earlier
//   steps (section loads 3/4, 60181a38, 6004d566, 605629cd) and later ones (609001ec, 609df7e4, ...) are not run here.
//   Disable with -Dom3.noAfModuleInit for the diag3 baseline.
// diag7-diag10: module init 602ef888 (with the discarded 97f00000 representative), AF worker defaults 609df7e4 and
// native AF trace logger 609dcddd; see OM3NativeAFModeDiagProbe history and the twenty-second follow-up.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3AFStartupConsumerProof extends OM3NativeAFModeConsumerProof {
 final List<String> taskIdCalls=new ArrayList<>();
 @Override boolean external(long t)throws Exception {
  if(t==0x50002a15L&&reg("D1")>0x10000){
   // Imported memset (A0=dst, D0=byte, D1=n). OM3NativeLifecycle bounds n to 64 KiB; AF init 6094721f legitimately
   // clears 0x11800 bytes at 60947242. Same semantics with a 2 MiB bound for RAM destinations, logged.
   long n=reg("D1"),dst=reg("A0");
   check(n<=0x200000&&((dst>=0x60000000L&&dst<0x64000000L)||(dst>=0xa0000000L&&dst<0xb0000000L)||(dst>=0x70000000L&&dst<0x71000000L)),String.format("Large memset contract n=%x dst=%08x",n,dst));
   byte[] b=new byte[(int)n];Arrays.fill(b,(byte)reg("D0"));e.writeMemory(toAddr(dst),b);e.writeRegister("A0",dst);
   String s=String.format("MODEL:large-memset n=%x dst=%08x value=%02x site=%08x",n,dst,reg("D0")&0xff,e.getExecutionAddress().getOffset());
   trace.add(s);taskIdCalls.add(s);return true;
  }
  if(t==0x60068a54L){
   // OM3NativeFlow also stops on 60068a54 as a "diagnostic path". It is the firmware's general errlog writer (4,928
   // callers; module code in D0, level/line/args on the stack; the caller continues afterwards). af-startup-consumer1
   // reached it from half press through the now-initialized AF module (status dispatcher 60903e88, code 0f804001,
   // level 3, line 9e9). OM-Emu records such errlog entries during ordinary S1 presses. Run natively; record every call.
   long sp=reg("SP");String args;try{args=String.format("%x,%x,%x,%x",u32(sp+4),u32(sp+8),u32(sp+0xc),u32(sp+0x10));}catch(Exception ex){args="unreadable";}
   String s=String.format("ERRLOG-CALL site=%08x code=%08x D1=%08x stack-args=%s (native)",e.getExecutionAddress().getOffset(),reg("D0"),reg("D1"),args);
   trace.add(s);if(taskIdCalls.size()<4000)taskIdCalls.add(s);
   return false;
  }
  if(t==0x609dcdddL){
   // OM3NativeFlow stops on 609dcddd as a "diagnostic path". Decoded 8 Nov: it is the AF module's trace logger
   // (-> 609479ef: if logging is enabled, a timestamped ring-buffer record of D0/D1/A0/A1 under lock 60075f73; 721
   // callers; e.g. 609321e3 calls it unconditionally first with tag "mb1"). Here it runs natively and is recorded.
   String s=String.format("AF-TRACE-LOG site=%08x D0=%08x D1=%08x A0=%08x A1=%08x (native)",e.getExecutionAddress().getOffset(),reg("D0"),reg("D1"),reg("A0"),reg("A1"));
   trace.add(s);if(taskIdCalls.size()<2000)taskIdCalls.add(s);
   return false;
  }
  if(t==0x60038ea5L&&!inTask10&&!taskStack.isEmpty()&&System.getProperty("om3.noTaskParking")==null){
   long id=reg("D0")&65535,wai=reg("D1"),mode=reg("A1")&255,q=taskStack.peek();
   try{return super.external(t);}
   catch(CompletionWait blocked){
    if(afTaskRow(q)==null)throw blocked;
    parked.put(q,new long[]{id,wai,mode});
    String s=String.format("SCHED:park queue=%d flag=%d mask=%08x mode=%d pc=%08x stack=%s (infinite wait unsatisfied; native context kept)",q,id,wai,mode,e.getExecutionAddress().getOffset(),taskStack);
    trace.add(s);taskIdCalls.add(s);consumerNote(s);
    throw new TaskBlocked();
   }
  }
  if(t==0x6003193eL&&!taskStack.isEmpty()&&taskStack.peek()==92){
   // Task identity for the queue-92 task from its ROM record (task 104), as OM3OriginalButtonConsumerProof does for 94/95.
   check(u32(0x600390e0L+103*28)==104,"Stock queue-92 task identity record");
   e.writeMemoryValue(toAddr(reg("A0")),2,104);e.writeRegister("D0",0);
   String s="MODEL:AF-task-identity-from-ROM queue=92 task=104";trace.add(s);taskIdCalls.add(s);return true;
  }
  if(t==0x6003193eL){
   long a0=reg("A0");
   String s=String.format("TASKID-CALL site=%08x A0=%08x SP=%08x stackTop=%08x taskStack=%s",e.getExecutionAddress().getOffset(),a0,reg("SP"),stackTop,taskStack);
   trace.add(s);taskIdCalls.add(s);
   boolean inAfTask=!taskStack.isEmpty()&&(taskStack.peek()==95||taskStack.peek()==94);
   if(!inAfTask&&!(a0>=0x70000000L&&a0<0x70100000L)){
    check(a0>=0xa0000000L&&a0<0xc0000000L,String.format("Task-ID output outside stack and uncached RAM: %08x",a0));
    // The output is word +4 of the request 6004f3bd just allocated and began filling (it stores the request's first
    // word at +0 one instruction earlier). Require that written header so a stray pointer still faults.
    e.readMemory(toAddr(a0-4),4);
    e.writeMemoryValue(toAddr(a0),2,1);e.writeRegister("D0",0);
    String m=String.format("MODEL:current-task=1 pool-output=%08x site=%08x (inherited task-1 value; output range widened)",a0,e.getExecutionAddress().getOffset());
    trace.add(m);taskIdCalls.add(m);return true;
   }
  }
  return super.external(t);
 }
 // af-startup-consumer2: after LOCK_START the worker sends request 0x5d to message buffer 92 (607117ac) and waits on 93.
 // ROM task table (records at 0x600390e0 + (id-1)*28, id at +0, entry at +12): task 104 entry 605a370a reads its queue
 // ID from halfword 0x6004322c (= 92), as task 105 reads 0x60043230 (94) and task 106 reads 0x60043232 (95). Prologue
 // movm [d2,d3,a2,a3]; add -0x40. It is scheduled exactly like the 94/95 tasks (persistent context, own-queue idle) on
 // its own stack (top 0x700e8000, unused elsewhere). Disable with -Dom3.noQueue92Task.
 static final long[] QUEUE92_TASK={92,0x605a370aL,0xf0,0x40,0x700e8000L};
 @Override boolean schedulePending()throws Exception {
  if(super.schedulePending())return true;
  if(System.getProperty("om3.noTaskParking")==null&&resumeParked())return true;
  if(System.getProperty("om3.noQueue92Task")!=null)return false;
  long[] t=QUEUE92_TASK;
  if(taskStack.contains(t[0])||mbfQueue.getOrDefault(t[0],new ArrayDeque<>()).isEmpty())return false;
  check(u32(0x600390e0L+103*28)==104&&u32(0x600390e0L+103*28+12)==t[1]&&u16(0x6004322cL)==92,"Stock queue-92 task identity record");
  runStockTask(t);return true;
 }
 // af-startup-consumer3: worker 94 submits its request through function pointer 603c8d71, which sets flag 68 bit
 // 0x100000 (the AF-command task's awaited event), registers callback 609ec651 (sets flag 67 bit 1, ROM halfword
 // 0x60042fa2) and waits on flag 67 at 609ec622. The worker was running nested inside task 95's flag-68 wait
 // (task stack [94,95]), so the nested model could not return to task 95 although its flag was now set. A uITRON kernel
 // would switch tasks. Scheduler model (labelled): an AF task whose infinite flag wait is unsatisfied is PARKED instead
 // of ending the run: its native context is kept exactly as for own-queue idle (TaskBlocked extends TaskIdle, so
 // OM3CompleteStaticOSConsumerProof stores it with PC at the wait call), control returns to the task or caller that
 // scheduled it, and schedulePending resumes it once its flag condition holds; the resumed wait call is re-executed and
 // re-checked by the stock wait model. No flag is set, no completion is supplied. Disable with -Dom3.noTaskParking.
 static class TaskBlocked extends TaskIdle {}
 final Map<Long,long[]> parked=new LinkedHashMap<>();
 long[] afTaskRow(long q){if(q==92)return QUEUE92_TASK;for(long[] t:TASKS)if(t[0]==q)return t;return null;}
 boolean flagMet(long id,long wai,long mode){Long p=eventFlags.get(id);if(p==null)return false;return mode==1?(p&wai)!=0:(p&wai)==wai;}
 boolean resumeParked()throws Exception {
  for(var en:new ArrayList<>(parked.entrySet())){
   long q=en.getKey();long[] w=en.getValue();
   if(taskStack.contains(q)||!flagMet(w[0],w[1],w[2]))continue;
   String s=String.format("SCHED:resume-parked queue=%d flag=%d mask=%08x pattern=%08x",q,w[0],w[1],eventFlags.get(w[0]));
   trace.add(s);taskIdCalls.add(s);consumerNote(s);
   runStockTask(afTaskRow(q));return true;
  }
  return false;
 }
 @Override void runStockTask(long[] t)throws Exception {parked.remove(t[0]);super.runStockTask(t);}
 boolean afModuleInit;
 @Override void prepareNativeAFMode()throws Exception {
  if(!afModuleInit&&System.getProperty("om3.noAfModuleInit")==null){
   afModuleInit=true;
   var caller=saveRegisters();long oldTop=stackTop;stackTop=0x700e2000L;
   try{
    // diag7: AF init sub-step 6098b138 reads object 0 of getter 602f6509 (0xa32c9c24 = null). Its writer 602f61a2 is
    // a sub-init of module init 602ef888, called by stock startup sequence 60045907 at 60045b09 (<- 60044f5f). That
    // sequence is not run by the harness. SUPPLIED-INPUT (labelled): run 602ef888 natively first, then 608fe1b0.
    if(System.getProperty("om3.noImageModuleInit")==null){
     String m=String.format("SUPPLIED-INPUT:stock module init 602ef888 (startup sequence 60045907 step 60045b09) run directly; a32c9c24 before=%08x",u32(0xa32c9c24L));
     trace.add(m);taskIdCalls.add(m);
     // diag8: its interrupt registration (6007602b -> 6004f86e) reaches the read of 0x97f00000 at 6004f99b. As in
     // OM3DeviceRegistryProbe (nineteenth follow-up): raw 6004f99b..f9b5 loads D0 and overwrites it before use, so
     // only that discarded value is represented (0). No interrupt, ordering or hardware response is modelled.
     try{e.readMemory(toAddr(0x97f00000L),4);}catch(RuntimeException unprovided){
      e.writeMemoryValue(toAddr(0x97f00000L),4,0);trace.add("INPUT-FIXTURE:discarded IRQ read 97f00000 representative 0 (as OM3DeviceRegistryProbe)");taskIdCalls.add("INPUT-FIXTURE:discarded IRQ read 97f00000 representative 0");}
     runNative(0x602ef888L,0,8);
     m=String.format("MODULE-INIT 602ef888 returned; a32c9c24=%08x a32c9c2c=%08x",u32(0xa32c9c24L),u32(0xa32c9c2cL));
     trace.add(m);taskIdCalls.add(m);
    }
    String s=String.format("SUPPLIED-INPUT:stock AF module init 608fe1b0 (startup task 602188f1 step 6021897f) run directly; context before=%08x",u32(0xa33f3614L));
    trace.add(s);taskIdCalls.add(s);
    runNative(0x608fe1b0L,0,4);
    // diag9: MODE_START/MODE_UPDATE round-trip natively but LOCK_START's guard byte 0xa33f3674 has one writer, the
    // startup default block 609df7e4 (sets it to 1), which task 602188f1 runs at 6021898d right after 608fe1b0
    // (6021897f) and the empty 609001ec (60218986). SUPPLIED-INPUT (labelled): run those next two steps in stock order.
    if(System.getProperty("om3.noAfDefaults")==null){
     runNative(0x609001ecL,0,0);   // retf: empty step, run for order only
     String d=String.format("SUPPLIED-INPUT:stock AF worker defaults 609df7e4 (task 602188f1 step 6021898d) run directly; a33f3674 before=%02x",u8(0xa33f3674L));
     trace.add(d);taskIdCalls.add(d);
     runNative(0x609df7e4L,0,4);
     d=String.format("AF-DEFAULTS returned; a33f3674=%02x a33f3640=%02x a33f364f=%02x",u8(0xa33f3674L),u8(0xa33f3640L),u8(0xa33f364fL));
     trace.add(d);taskIdCalls.add(d);
    }
    s=String.format("AF-MODULE-INIT returned; worker context a33f3614=%08x a33f3618=%08x a33f361c=%08x",u32(0xa33f3614L),u32(0xa33f3618L),u32(0xa33f361cL));
    trace.add(s);taskIdCalls.add(s);
   }finally{stackTop=oldTop;restoreRegisters(caller);}
  }
  super.prepareNativeAFMode();
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   for(var en:parked.entrySet()){long[] w=en.getValue();Long p=eventFlags.get(w[0]);
    taskIdCalls.add(String.format("SCHED:parked-at-end queue=%d flag=%d mask=%08x mode=%d pattern=%s (no producer set it)",en.getKey(),w[0],w[1],w[2],p==null?"none":Long.toHexString(p)));}
   Files.write(Paths.get(getScriptArgs()[0]).resolve("af-startup-steps.txt"),taskIdCalls);
  }
 }
}
