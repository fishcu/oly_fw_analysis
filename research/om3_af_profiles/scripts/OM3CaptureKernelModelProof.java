// Conditional continuation of the event-114 connection probe past kernel service 600303db.
// 600303db is modelled as a message-buffer create (packet attr, maxmsz, mbfsz, buffer),
// matching its native contract checks; dispatch disable/enable (60031521/60031609) are
// modelled as a nesting-checked flag. These are explicit kernel models like the existing
// semaphore/mutex/event-flag models. No device reply or AF success is synthesized.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CaptureKernelModelProof extends OM3CaptureConnectedProof {
 Map<Long,long[]> messageBuffers=new HashMap<>();boolean dispatchDisabled;Map<Long,ArrayDeque<byte[]>> mbfQueue=new HashMap<>();
 static class TaskIdle extends RuntimeException {}
 static class TransportBoundary extends RuntimeException {TransportBoundary(String s){super(s);}}
 static class CompletionWait extends RuntimeException {CompletionWait(String s){super(s);}}
 Map<Long,Long> flagAttr=new HashMap<>();
 void loadStaticFlags(long id)throws Exception {
  // Stock ROM 0x6003ab34: 283 records of {id, attr, initial pattern}; attr bits limited to 0..7.
  if(eventFlags.containsKey(id)||id<1||id>283)return;long r=0x6003ab34L+(id-1)*12;
  check(u32(r)==id&&u32(r+4)<=7,"Static event-flag ROM descriptor "+id);
  eventFlags.put(id,u32(r+8));flagAttr.put(id,u32(r+4));trace.add(String.format("MODEL:static-event-flag-from-ROM:id=%d attr=%d init=%08x",id,u32(r+4),u32(r+8)));
 }
 boolean staticMbf,inTask207,task207Ran,guard,hookTablesInit;
 void runTask207()throws Exception {
  // Separate task context: all base registers saved/restored, own stack (not 0x70050000 used by scheduled()).
  Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(ghidra.program.model.lang.Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
  long oldTop=stackTop;stackTop=0x70070000L;inTask207=true;task207Ran=true;
  try{runNative(0x610615f5L,0x20,0x20);throw new Exception("Stock task-207 loop returned");}
  catch(TaskIdle idle){trace.add("MODEL:task-207-quiescent");}
  finally{inTask207=false;stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
 }
 void loadStaticMessageBuffers()throws Exception {
  if(staticMbf)return;staticMbf=true;
  // Stock ROM 0x6003bab4: 218 records of {id, attr, maxmsz, mbfsz, buf}; same layout as the 600303db packet.
  for(int id=1;id<=218;id++){long r=0x6003bab4L+(id-1)*20;check(u32(r)==id&&u32(r+4)<=1&&u32(r+8)>0&&u32(r+8)<=u32(r+12)&&u32(r+12)<0x100000&&u32(r+16)==0,"Static message-buffer ROM descriptor "+id);messageBuffers.putIfAbsent((long)id,new long[]{u32(r+8),u32(r+12),0});}
  trace.add("MODEL:218-static-message-buffer-descriptors-from-stock-ROM-6003bab4");
 }
 @Override boolean external(long t)throws Exception {
  loadStaticMessageBuffers();
  if(t==0x6004d886L&&!hookTablesInit){
   // Stock startup routine 6004cfd9 (called from 60044f5f) publishes per-core message-hook table pointers
   // at a3258350..5c. Executed natively here before first RPC use; its boot ordering is not established.
   hookTablesInit=true;trace.add("STOCK-INIT:running 6004cfd9 per-core message-hook table publisher");
   Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(ghidra.program.model.lang.Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
   long oldTop=stackTop;stackTop=0x70078000L;
   try{runNative(0x6004cfd9L,0,4);}finally{stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
   trace.add(String.format("STOCK-INIT:hook-table core0=%08x",u32(0xa3258350L)));
   return false;}
  if(t==0x600303dbL){
   long pk=reg("A0");long attr=u8(pk),maxmsz=u32(pk+4),mbfsz=u32(pk+8),buf=u32(pk+12);
   check(attr<=1,"Message-buffer attribute contract (native returns -11)");
   check(maxmsz!=0,"Message-buffer maxmsz contract (native returns -17)");
   check(mbfsz>=maxmsz&&mbfsz<0x100000,"Message-buffer size contract");
   long id=objectID++;messageBuffers.put(id,new long[]{maxmsz,mbfsz,buf});e.writeRegister("D0",id);
   trace.add(String.format("MODEL:message-buffer-create:id=%d attr=%d maxmsz=%d mbfsz=%d buf=%08x",id,attr,maxmsz,mbfsz,buf));return true;}
  if(t==0x60037598L){
   // tsnd_mbf-shaped service: D0=id (core bits 12-14, index bits 0-11, table +0xe8), A0=msg, D1=size, A1=timeout.
   long id=reg("D0")&0xffff,msg=reg("A0"),size=reg("D1"),tmo=reg("A1");long[] mb=messageBuffers.get(id);
   check(mb!=null,"Send to unmodelled message buffer "+id);check(size>0&&size<=mb[0],"Message size exceeds maxmsz");
   long used=mbfQueue.computeIfAbsent(id,k->new ArrayDeque<>()).stream().mapToLong(b->b.length).sum();
   check(used+size<=mb[1],String.format("Message-buffer send would block id=%d timeout=%08x (no receiver task modelled)",id,tmo));
   byte[] m=new byte[(int)size];StringBuilder unwritten=new StringBuilder();
   for(int i=0;i<size;i++){try{m[i]=e.readMemory(toAddr(msg+i),1)[0];}catch(RuntimeException ex){m[i]=0;unwritten.append(i).append(',');}}
   if(unwritten.length()>0)trace.add("MODEL:never-written-message-bytes-copied-as-zero:offsets="+unwritten);
   mbfQueue.get(id).add(m);e.writeRegister("D0",0);
   trace.add(String.format("MODEL:message-buffer-send:id=%d size=%d timeout=%08x bytes=%s",id,size,tmo,HexFormat.of().formatHex(m)));return true;}
  if(t==0x60038ea5L){
   // twai_flg-shaped service: D0=id, D1=wait pattern, A1=mode (0 AND, 1 OR), A0=pattern out, stack +4=timeout.
   long id=reg("D0")&0xffff,wai=reg("D1"),mode=reg("A1")&0xff,out=reg("A0"),tmo=u32(reg("SP")+4);
   loadStaticFlags(id);check(eventFlags.containsKey(id),"Wait on unmodelled event flag "+id);check(wai!=0&&mode<=1,"Event-flag wait contract");
   long pat=eventFlags.get(id);boolean ok=mode==1?(pat&wai)!=0:(pat&wai)==wai;
   if(ok){e.writeMemoryValue(toAddr(out),4,pat);if((flagAttr.getOrDefault(id,0L)&4)!=0)eventFlags.put(id,0L);e.writeRegister("D0",0);trace.add(String.format("MODEL:event-flag-wait-satisfied:id=%d pattern=%08x",id,pat));return true;}
   if(tmo==0){e.writeRegister("D0",0xffffffceL);trace.add(String.format("MODEL:event-flag-poll-timeout:id=%d wait=%08x pattern=%08x",id,wai,pat));return true;}
   throw new CompletionWait(String.format("flag=%d wait=%08x mode=%d timeout=%d pattern=%08x",id,wai,mode,tmo,pat));}
  if(t==0x6003727eL){
   // trcv_mbf-shaped service: D0=id, A0=destination, D1=timeout; returns message size.
   long id=reg("D0")&0xffff,dst=reg("A0"),tmo=reg("D1");check(messageBuffers.containsKey(id),"Receive from unmodelled message buffer "+id);
   ArrayDeque<byte[]> q=mbfQueue.computeIfAbsent(id,k->new ArrayDeque<>());
   if(q.isEmpty()&&!inTask207&&!task207Ran&&!mbfQueue.getOrDefault(207L,new ArrayDeque<>()).isEmpty()){
    trace.add(String.format("MODEL:caller-blocks-on-message-buffer:id=%d timeout=%08x; scheduling stock task-207 loop 610615f5",id,tmo));
    runTask207();
    q=mbfQueue.computeIfAbsent(id,k->new ArrayDeque<>());
   }
   if(q.isEmpty()){
    if(inTask207&&id==207){trace.add("MODEL:task-207-idle-waiting-on-207");throw new TaskIdle();}
    throw new Exception(String.format("Message-buffer receive would block id=%d timeout=%08x",id,tmo));
   }
   byte[] m=q.poll();e.writeMemory(toAddr(dst),m);e.writeRegister("D0",m.length);
   trace.add(String.format("MODEL:message-buffer-receive:id=%d size=%d bytes=%s",id,m.length,HexFormat.of().formatHex(m)));return true;}
  if(t==0x6004d35eL||t==0x6004d43fL){boolean take=t==0x6004d35eL;check(guard!=take,"Command guard ownership");guard=take;e.writeRegister("D0",0);trace.add("MODEL:stock-command-guard:"+take);return true;}
  if(t==0x6007a7b5L){
   long env=reg("A0"),packet=u32(env),len=u32(env+4);
   trace.add(String.format("NATIVE-COMMAND-TRANSPORT:via-task-207 port=%d timeout=%d length=%d bytes=%s",reg("D0"),reg("D1"),len,HexFormat.of().formatHex(e.readMemory(toAddr(packet),(int)Math.min(len,256)))));
   throw new TransportBoundary(String.format("port=%d length=%d",reg("D0"),len));}
  if(t==0x60031521L){check(!dispatchDisabled,"Nested dispatch disable");dispatchDisabled=true;e.writeRegister("D0",0);trace.add("MODEL:dispatch-disable");return true;}
  if(t==0x60031609L){check(dispatchDisabled,"Dispatch enable without disable");dispatchDisabled=false;e.writeRegister("D0",0);trace.add("MODEL:dispatch-enable");return true;}
  return super.external(t);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);Files.deleteIfExists(out.resolve("kernel-model-outcome.txt"));
  try{
   super.run();
   String prior=Files.exists(out.resolve("capture-connection-outcome.txt"))?Files.readString(out.resolve("capture-connection-outcome.txt")):"";
   if(prior.startsWith("BOUNDARY"))Files.writeString(out.resolve("kernel-model-outcome.txt"),"UNCHANGED earlier 97f00004 boundary still reached; model not exercised\n");
   else Files.writeString(out.resolve("kernel-model-outcome.txt"),String.format("RETURNED connection probe with modelled 600303db; state=%d backend=%08x requested=%08x; inspect trace; physical completion excluded\n",u32(0x62b7315cL+0xb4),u32(0x62b7315cL+0xb8),u32(0x62b7315cL+0xbc)));
  }catch(Exception ex){
   Throwable w=ex;while(w!=null&&!(w instanceof CompletionWait))w=w.getCause();
   if(w!=null){Files.writeString(out.resolve("kernel-model-outcome.txt"),"BOUNDARY task-207 command path blocks waiting for completion event ("+w.getMessage()+"); no completion supplied\n");println("BOUNDARY completion wait");return;}
   Throwable c=ex;while(c!=null&&!(c instanceof TransportBoundary))c=c.getCause();
   if(c!=null){Files.writeString(out.resolve("kernel-model-outcome.txt"),"BOUNDARY event-114 connection reaches native transport 6007a7b5 through modelled message buffers and the stock task-207 loop ("+c.getMessage()+"); no submission, peer reply or AF completion tested\n");println("BOUNDARY at transport via task 207");return;}
   Files.writeString(out.resolve("kernel-model-outcome.txt"),"BOUNDARY after modelled 600303db: "+ex+"\n");
   println("BOUNDARY after modelled message-buffer create: "+ex);
  }
 }
}
