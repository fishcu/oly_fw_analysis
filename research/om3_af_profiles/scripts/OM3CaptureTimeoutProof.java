// Continuation of OM3CaptureLinkProof. The SCPU never answers: task 207's positive-timeout wait on
// flag 225 returns the stock timeout code (-50) instead of stopping the run. This models an absent or
// silent SCPU (a real stock outcome), not a success. Original button handlers then run, and every
// message-buffer send is logged with its destination, especially AF command queue 95 and AF worker 94.
// @category OM3
import java.util.*;
public class OM3CaptureTimeoutProof extends OM3CaptureLinkProof {
 boolean timedOut;
 String safeByte(long a){try{return String.format("%02x",e.readMemory(toAddr(a),1)[0]&0xff);}catch(RuntimeException ex){return "unprovided";}}
 @Override boolean external(long t)throws Exception {
  if(t==0x60038ea5L){
   long id=reg("D0")&0xffff,tmo=u32(reg("SP")+4);
   loadStaticFlags(id);
   if(tmo!=0&&eventFlags.containsKey(id)){
    long wai=reg("D1"),mode=reg("A1")&0xff,pat=eventFlags.get(id);boolean ok=mode==1?(pat&wai)!=0:(pat&wai)==wai;
    if(!ok){
     if(!port2Ran&&!dtq.getOrDefault(2L,new ArrayDeque<>()).isEmpty()){trace.add("MODEL:port-2-task-not-run-in-timeout-probe (link hardware absent)");port2Ran=true;}
     timedOut=true;e.writeRegister("D0",0xffffffceL);
     trace.add(String.format("MODEL:event-flag-wait-TIMEOUT:id=%d wait=%08x timeout=%d (no SCPU reply modelled as silence)",id,wai,tmo));return true;}
   }
  }
  if(t==0x60570f8eL){long rec=reg("D1");StringBuilder h=new StringBuilder();for(int k=0;k<0x40;k++){try{h.append(String.format("%02x",e.readMemory(toAddr(rec+k),1)[0]&0xff));}catch(RuntimeException ex){h.append("..");}}
   trace.add(String.format("AF-MODE-RECORD:caller-ret=%08x D0=%08x D1(rec)=%08x A0=%08x A1=%08x sp=%08x rec[0..3f]=%s",reg("MDR"),reg("D0"),rec,reg("A0"),reg("A1"),reg("SP"),h));
   long sp=reg("SP");StringBuilder s=new StringBuilder();for(int k=0;k<0x100;k+=4){try{long v=u32(sp+k);if(v>=0x60021000L&&v<0x62000000L)s.append(String.format("%x@%x ",v,k));}catch(RuntimeException ex){}}
   trace.add("AF-MODE-RECORD-STACK-CODEPTRS:"+s);}
  if(t==0x60063380L){long k=reg("D0")&0xffff;if(k==0x4501||k==0x91b1||k==0xc011||k==0x8121)trace.add(String.format("AF-MODE-SETTING-READ:id=%04x index=%d pc=%08x modelled=%s",k,reg("D1"),e.getExecutionAddress().getOffset(),settings.containsKey((reg("D0")<<16)|reg("D1"))?"ram-map":"native-or-factory"));}
  if(t==0x6031c0ebL)trace.add(String.format("AF-RAW-MODE-GETTER:called pc=%08x flag62b0fde8=%s",e.getExecutionAddress().getOffset(),safeByte(0x62b0fde8L)));
  if(t==0x6070d4a2L&&e.getExecutionAddress().getOffset()==0x605aa39eL)trace.add(String.format("AF-RAW-MODE-CODE:record+2=%02x (value returned by 6031c0eb)",u8(reg("A0"))));
  if(t==0x605712deL){trace.add(String.format("AF-REGISTRY-LOOKUP:key=%02x pc=%08x A0=%08x",reg("D0")&0xff,e.getExecutionAddress().getOffset(),reg("A0")));}
  if(t==0x60024d0eL){trace.add(String.format("AF-DAMAGE-LOG:code=%04x (stock damage_info recorder, logged not executed)",reg("D0")&0xffff));return true;}
  if(t==0x60031149L){
   // del_mbf-shaped service (table +0xe8 family, called by 6004d00c after the RPC): D0=id.
   long id=reg("D0")&0xffff;check(messageBuffers.containsKey(id)&&id>218,"Delete of unmodelled or static message buffer "+id);
   check(mbfQueue.getOrDefault(id,new ArrayDeque<>()).isEmpty(),"Delete of non-empty message buffer "+id);
   messageBuffers.remove(id);mbfQueue.remove(id);e.writeRegister("D0",0);trace.add("MODEL:message-buffer-delete:id="+id);return true;}
  if(t==0x60037598L){long id=reg("D0")&0xffff;if(id==95||id==94)trace.add(String.format("AF-QUEUE-SEND:mbf=%d size=%d",id,reg("D1")));}
  if(t==0x60318c44L||t==0x60700fb4L||t==0x607117acL||t==0x600756e6L||t==0x60416facL)trace.add(String.format("AF-SEND-HELPER:%08x D0=%08x D1=%08x A0=%08x A1=%08x",t,reg("D0"),reg("D1"),reg("A0"),reg("A1")));
  return super.external(t);
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   java.nio.file.Path o=java.nio.file.Paths.get(getScriptArgs()[0]);
   List<String> af=new ArrayList<>();for(String s:trace)if(s.startsWith("AF-")||s.contains("TIMEOUT")||s.startsWith("RETURNED")||s.startsWith("BOUNDARY"))af.add(s);
   java.nio.file.Files.write(o.resolve("af-sends.txt"),af);
   java.nio.file.Files.write(o.resolve("timeout-trace.txt"),trace);
  }
 }
}
