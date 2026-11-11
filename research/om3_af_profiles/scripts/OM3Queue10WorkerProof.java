// Persistent native property-service task. Kernel queue/flag operations use the
// existing declared models; every command result and reply comes from ROM code.
// @category OM3
import java.util.*;
public class OM3Queue10WorkerProof extends OM3StockModeSequenceProof {
 boolean inTask10,task10Started;
 Map<String,java.math.BigInteger> task10Context;
 Map<String,java.math.BigInteger> saveRegisters(){
  Map<String,java.math.BigInteger> s=new LinkedHashMap<>();
  for(var r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())s.put(r.getName(),e.readRegister(r.getName()));
  return s;
 }
 void restoreRegisters(Map<String,java.math.BigInteger> s){for(var r:s.entrySet())e.writeRegister(r.getKey(),r.getValue());}
 void runTask10()throws Exception {
  check(!inTask10,"Recursive task10 scheduling");
  var caller=saveRegisters();long oldTop=stackTop;stackTop=0x700e0000L;inTask10=true;
  try{
   if(!task10Started){
    loadStaticFlags(11);
    if(!hookTablesInit){runNative(0x6004cfd9L,0,4);hookTablesInit=true;}
    task10Started=true;trace.add("TASK10:first native entry");runNative(0x60065881L,0,0);
   }else{restoreRegisters(task10Context);trace.add("TASK10:resume saved native context");continueNative(stackTop,0x70fff000L);}
   throw new Exception("Unexpected task10 return");
  }catch(TaskIdle idle){task10Context=saveRegisters();trace.add("TASK10:suspended at unsatisfied own flag11 wait");}
  finally{inTask10=false;stackTop=oldTop;restoreRegisters(caller);}
 }
 @Override boolean schedulePending()throws Exception {
  if(!inTask10&&!mbfQueue.getOrDefault(10L,new ArrayDeque<>()).isEmpty()){runTask10();return true;}
  return super.schedulePending();
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x60037598L&&(reg("D0")&65535)==10&&!task10Started)runTask10();
  if(inTask10&&t==0x60038ea5L&&(reg("D0")&65535)==11){
   loadStaticFlags(11);long wait=reg("D1"),mode=reg("A1")&255,pat=eventFlags.get(11L);
   if(mode==1?(pat&wait)==0:(pat&wait)!=wait)throw new TaskIdle();
  }
  if(inTask10&&t==0x6003193eL){e.writeMemoryValue(toAddr(reg("A0")),2,10);e.writeRegister("D0",0);return true;}
  if(t==0x60034cc7L){
   long id=reg("D0")&65535,out=reg("A0");long[] mb=messageBuffers.get(id);
   check(inTask10&&id==10&&mb!=null,"ref_mbf model scoped to task10/queue10");
   var q=mbfQueue.getOrDefault(id,new ArrayDeque<>());
   // No blocked send/receive task exists in this single-context queue model.
   e.writeMemoryValue(toAddr(out),2,0);e.writeMemoryValue(toAddr(out+2),2,0);
   e.writeMemoryValue(toAddr(out+4),4,q.size());
   long used=q.stream().mapToLong(b->((b.length+3)&~3)+4).sum();
   long raw=Math.max(0,mb[1]-used),unit=mb[0]+4;
   e.writeMemoryValue(toAddr(out+8),4,raw/unit*mb[0]+Math.max(0,raw%unit-4));
   e.writeRegister("D0",0);trace.add("MODEL:ref_mbf queue10 count="+q.size());return true;
  }
  if(inTask10&&t==0x60065afbL)trace.add(String.format("TASK10:stock command=%x payload=%08x",reg("D0"),reg("A0")));
  if(inTask10&&t==0x60037598L)trace.add(String.format("TASK10:stock reply mbf=%d bytes=%s",reg("D0"),hex(reg("A0"),(int)reg("D1"))));
  return super.external(t);
 }
}
