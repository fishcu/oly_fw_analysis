// Restore the stock software completion-bit allocator initializer. No hardware
// endpoint is registered and no sample is supplied by this experiment.
// @category OM3
import java.nio.file.*;
public class OM3PropertyFailurePathProof extends OM3Queue10MissingDeviceProof {
 void initializePropertyRequests()throws Exception {
  // Static kernel flags exist before a callback can signal them; materialize
  // the ROM record before the first set, not only at the later wait.
  loadStaticFlags(u16(0x60043164L));
  var saved=saveRegisters();long oldTop=stackTop;stackTop=0x700dc000L;
  try{runNative(0x60063edaL,0,0);check(u32(0xa32bfb34L)==1,"Native request-bit initializer");}
  finally{stackTop=oldTop;restoreRegisters(saved);}
  trace.add("STOCK-INIT:native60063eda request-bit allocator initialized; no endpoint registered");
 }
 @Override void beforeOriginal()throws Exception {initializePropertyRequests();super.beforeOriginal();}
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);String scope="Stock software initializer60063eda executed before framework connection; this does not establish complete property-service startup or any hardware device.\n";
   Files.writeString(out.resolve("property-request-initializer.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
