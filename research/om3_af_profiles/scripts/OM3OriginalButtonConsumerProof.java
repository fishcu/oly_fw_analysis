// Service real pending AF tasks at original-button boundaries and before flag
// waits. An unsatisfied infinite AF wait stays blocked; it is never a timeout.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3OriginalButtonConsumerProof extends OM3OriginalButtonMatrixProof {
 int consumerRounds;
 void progress(String phase)throws Exception{Files.writeString(Paths.get(getScriptArgs()[0]).resolve("consumer-progress.txt"),java.time.Instant.now()+" "+phase+"\n");}
 @Override void coreFixture()throws Exception{super.coreFixture();progress("stock constructor groups completed");}
 @Override void beforeOriginal()throws Exception{progress("begin native settings reset and framework startup");super.beforeOriginal();}
 String observedBytes(long p,int n){StringBuilder b=new StringBuilder();for(int i=0;i<n;i++){try{b.append(String.format("%02x",u8(p+i)));}catch(Exception ex){b.append("??");}}return b.toString();}
 final List<String> consumerEvidence=new ArrayList<>();
 void consumerNote(String s){trace.add(s);consumerEvidence.add(s);}
 @Override boolean external(long t)throws Exception {
  if(t==0x6003193eL&&!taskStack.isEmpty()&&(taskStack.peek()==95||taskStack.peek()==94)){
   long queue=taskStack.peek(),task=queue==95?106:105,row=0x600390e0L+(task-1)*28;
   check(u32(row)==task&&u32(row+12)==(queue==95?0x6031787eL:0x609df84dL),"Stock AF task identity record");
   e.writeMemoryValue(toAddr(reg("A0")),2,task);e.writeRegister("D0",0);
   consumerNote("MODEL:AF-task-identity-from-ROM queue="+queue+" task="+task);return true;
  }
  if(t==0x60038ea5L&&!inTask10&&!taskStack.isEmpty()){
   long id=reg("D0")&65535,wai=reg("D1"),mode=reg("A1")&255,tmo=u32(reg("SP")+4);
   check(wai!=0&&mode<=1,"AF flag-wait mode/pattern contract");
   loadStaticFlags(id);check(eventFlags.containsKey(id),"AF wait requires a declared flag "+id);
   int rounds=0;
   while(!(mode==1?(eventFlags.get(id)&wai)!=0:(eventFlags.get(id)&wai)==wai)&&rounds<16&&schedulePending())rounds++;
   if(tmo==0xffffffffL&&!(mode==1?(eventFlags.get(id)&wai)!=0:(eventFlags.get(id)&wai)==wai)){
    String boundary=String.format("AF-INFINITE-WAIT flag=%d mask=%08x pc=%08x task=%s pending95=%d pending94=%d; no completion producer supplied",id,wai,e.getExecutionAddress().getOffset(),taskStack.peek(),mbfQueue.getOrDefault(95L,new ArrayDeque<>()).size(),mbfQueue.getOrDefault(94L,new ArrayDeque<>()).size());
    consumerNote(boundary);throw new CompletionWait(boundary);
   }
  }
  if(t==0x60318c44L&&reg("D0")==94){
   long p=reg("A0"),payload=u32(p+12);
   consumerNote(String.format("AF-WORKER-SUBMIT command=%x packet=%s payload=%08x bytes=%s owner=%d subject=%d",u32(p+8),hex(p,16),payload,observedBytes(payload,64),u8(ownedState()+4),u8(0x62a6a0ebL)));
  }
  return super.external(t);
 }
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  if(ins.getAddress().getOffset()==0x609b3bb2L&&!taskStack.isEmpty()){
   long p=u32(ownedState()+8);
   consumerNote(String.format("AF-CACHE-ACCESS task=%s owner=%d active-cache=%08x bytes=%s subject=%d",taskStack.peek(),u8(ownedState()+4),p,hex(p,10),u8(0x62a6a0ebL)));
  }
  return super.instruction(ins);
 }
 @Override void afterOriginal()throws Exception {
  super.afterOriginal();
  progress("profile checks="+matrixStep+"/28; beginning native AF task drain");
  int rounds=0;while(rounds<16&&schedulePending()){rounds++;consumerRounds++;}
  check(rounds<16,"AF consumers did not quiesce within the bounded schedule");
  consumerNote("AF-CONSUMERS-QUIESCENT after matrix-edge="+matrixStep+" rounds="+rounds);
 }
 @Override public void run()throws Exception {
  Files.createDirectories(Paths.get(getScriptArgs()[0]));progress("script compiled and entered run");
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);Files.write(out.resolve("af-consumer-evidence.txt"),consumerEvidence);
   String scope="Conditional native AF consumer scheduling after original edges and before AF flag waits. Unsatisfied infinite waits remain blocked. ROM task IDs105/106 used. Quiescent schedules="+consumerRounds+"; profile matrix checks="+matrixStep+"/28. No AF or device completion fabricated.\n";
   Files.writeString(out.resolve("af-consumer-outcome.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
