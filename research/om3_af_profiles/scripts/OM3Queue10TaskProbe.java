// Isolated stock queue-10 worker startup, without the expensive UI fixture.
// No request/reply is synthesized. An empty own event flag yields task idle.
// @category OM3
import java.nio.file.*;
public class OM3Queue10TaskProbe extends OM3CaptureAfTaskProof {
 boolean inTask10;
 @Override boolean external(long t)throws Exception {
  if(inTask10&&t==0x60038ea5L&&(reg("D0")&0xffff)==11){
   loadStaticFlags(11);long wait=reg("D1"),pat=eventFlags.get(11L);
   if((pat&wait)==0){trace.add("TASK10:idle on own flag 11");throw new TaskIdle();}
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String outcome;
  init();trace.clear();
  e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
   public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided task10 read "+a+" at "+e.getExecutionAddress());}
   public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown task10 address "+a);}
  });
  try{
   loadStaticMessageBuffers();loadStaticFlags(11);
   runNative(0x6004cfd9L,0,4);hookTablesInit=true;
   inTask10=true;runNative(0x60065881L,0,0);
   outcome="UNEXPECTED stock task returned";
  }catch(TaskIdle idle){outcome="IDLE: native task10 startup completed; no message or reply supplied";}
  catch(Exception ex){outcome=String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex);}
  finally{inTask10=false;}
  Files.write(out.resolve("task10-trace.txt"),trace);Files.writeString(out.resolve("task10-outcome.txt"),outcome+"\n");println(outcome);e.dispose();
 }
}
