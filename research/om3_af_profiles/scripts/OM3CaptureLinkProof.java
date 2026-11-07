// Continuation of OM3CaptureKernelModelProof: runs native transport 6007a7b5 instead of stopping at it,
// models its link spin-lock (60075f73/60075fbc) and kernel data-queue send/receive (60037413/600370b6)
// with the five static data queues from stock ROM 0x6003b908, and schedules the stock port-2 receiver
// task 6007908c (from its entry, including its own initialization) in a separate saved context when
// task 207 starts its positive-timeout completion wait. No completion, peer reply or AF success is supplied.
// @category OM3
import java.util.*;
public class OM3CaptureLinkProof extends OM3CaptureKernelModelProof {
 Map<Long,Long> dtqCapacity=new HashMap<>();Map<Long,ArrayDeque<Long>> dtq=new HashMap<>();
 boolean linkLock,inPort2,port2Ran,staticDtq;
 void loadStaticDataQueues()throws Exception {
  if(staticDtq)return;staticDtq=true;
  for(int id=1;id<=5;id++){long r=0x6003b908L+(id-1)*16;check(u32(r)==id&&u32(r+4)<=1&&u32(r+8)>0&&u32(r+8)<0x1000&&u32(r+12)==0,"Static data-queue ROM descriptor "+id);dtqCapacity.put((long)id,u32(r+8));}
  trace.add("MODEL:5-static-data-queue-descriptors-from-stock-ROM-6003b908");
 }
 void runPort2()throws Exception {
  Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(ghidra.program.model.lang.Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
  long oldTop=stackTop;stackTop=0x70060000L;inPort2=true;port2Ran=true;
  trace.add("MODEL:scheduling-stock-port-2-task 6007908c from entry");
  try{runNative(0x6007908cL,0x30,0x10);throw new Exception("Stock port-2 task returned");}
  catch(TaskIdle idle){trace.add("MODEL:port-2-task-quiescent");}
  finally{inPort2=false;stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
 }
 @Override public void run()throws Exception {
  super.run();
  java.nio.file.Path o=java.nio.file.Paths.get(getScriptArgs()[0]).resolve("kernel-model-outcome.txt");String s=java.nio.file.Files.readString(o);
  String text=s.contains("Unprovided startup read 9b8831a0 at 60074890")
   ?"BOUNDARY hardware: native transport posted the 36-byte command-40 packet in slot a32c66b0 to data queue 2; the stock port-2 task 6007908c initialization reaches peripheral interrupt-mask register 9b8831a0 (ROM descriptor 60026900[191], logical interrupt 102, vector 77, handler 60074d3f, peripheral base 9b881b80); no device register state, interrupt, peer reply, flag-225 completion or AF acquisition supplied\n"
   :"UNEXPECTED link-probe outcome: "+s;
  java.nio.file.Files.writeString(o.resolveSibling("link-outcome.txt"),text);println(text.trim());
 }
 @Override boolean external(long t)throws Exception {
  loadStaticDataQueues();
  if(t==0x6007a7b5L){long env=reg("A0");trace.add(String.format("NATIVE-TRANSPORT-ENTRY port=%d timeout=%d length=%d",reg("D0"),reg("D1"),u32(env+4)));return false;}
  if(t==0x60075f73L){check(!linkLock,"Nested link lock");linkLock=true;e.writeRegister("D0",0x80000000L);trace.add("MODEL:link-spinlock-take");return true;}
  if(t==0x60075fbcL){check(linkLock,"Link unlock without lock");linkLock=false;trace.add("MODEL:link-spinlock-release");return true;}
  if(t==0x60037413L){
   long id=reg("D0")&0xffff,data=reg("D1"),tmo=reg("A0");check(dtqCapacity.containsKey(id),"Send to unmodelled data queue "+id);
   ArrayDeque<Long> q=dtq.computeIfAbsent(id,k->new ArrayDeque<>());check(q.size()<dtqCapacity.get(id),"Data-queue send would block id="+id);
   q.add(data);e.writeRegister("D0",0);trace.add(String.format("MODEL:data-queue-send:id=%d data=%08x timeout=%08x slot-bytes=%s",id,data,tmo,HexFormat.of().formatHex(e.readMemory(toAddr(data),36))));return true;}
  if(t==0x600370b6L){
   long id=reg("D0")&0xffff,out=reg("A0"),tmo=reg("D1");check(dtqCapacity.containsKey(id),"Receive from unmodelled data queue "+id);
   ArrayDeque<Long> q=dtq.computeIfAbsent(id,k->new ArrayDeque<>());
   if(q.isEmpty()){if(inPort2&&id==2){trace.add("MODEL:port-2-task-idle-waiting-on-data-queue-2");throw new TaskIdle();}throw new Exception("Data-queue receive would block id="+id+" timeout="+Long.toHexString(tmo));}
   long v=q.poll();e.writeMemoryValue(toAddr(out),4,v);e.writeRegister("D0",0);trace.add(String.format("MODEL:data-queue-receive:id=%d data=%08x",id,v));return true;}
  if(t==0x60038ea5L&&u32(reg("SP")+4)!=0&&!port2Ran&&!dtq.getOrDefault(2L,new ArrayDeque<>()).isEmpty()){
   trace.add("MODEL:task-207-enters-completion-wait; data queue 2 non-empty");runPort2();}
  return super.external(t);
 }
}
