// Complete native request-builder -> missing-device callback -> wait -> free.
// A returned fallback zero is explicitly not a sampled device measurement.
// @category OM3
import java.nio.file.*;
public class OM3PropertyFailurePathProbe extends OM3PropertyFailurePathProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String outcome;
  init();trace.clear();
  // Explicit isolated CPU fixture, including SLEIGH scratch base registers.
  // The full UI fixture already establishes these before saveRegisters().
  for(var r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())e.writeRegister(r.getName(),0);
  e.writeRegister("SP",stackTop);
  e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
   public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided property failure read "+a+" at "+e.getExecutionAddress());}
   public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown property failure address "+a);}
  });
  try{
   initializePropertyRequests();isolatedMissingDevice=true;
   for(int i=0;i<5;i++){
    long endpoint=u8(0x6012000cL+2*i),before=allocations.size();
    e.writeRegister("D0",endpoint);runNative(0x60063f0cL,0xf0,0x40);
    check(reg("D0")==0&&missingCallbacks==i+1,"Native missing-device fallback must return zero after its callback");
    check(allocations.size()==before,"Native request packet must be freed");
    check(u32(0xa32bfb34L)==(1L<<(i+1)),"Native request-bit allocation progression");
    trace.add("NATIVE-FAILURE-PATH endpoint="+endpoint+" fallback=0 packet-freed=true; not a device measurement");
   }
   outcome="RETURNED: five native request builders completed via native missing-device failure callbacks, flag waits and packet frees; fallback zero is not a sensor sample; registry remains empty";
  }catch(Exception ex){outcome=String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex);}
  Files.write(out.resolve("property-failure-trace.txt"),trace);Files.writeString(out.resolve("property-failure-outcome.txt"),outcome+"\n");println(outcome);e.dispose();
 }
}
