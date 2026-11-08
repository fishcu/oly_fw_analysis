// Inspect the stock registered-device path separately from missing-device
// fallback. No MMIO value or hardware interrupt is supplied; infinite waits
// cannot be converted into synthetic timeouts in this probe.
// @category OM3
import java.nio.file.*;
public class OM3DeviceRegistryProbe extends OM3PropertyFailurePathProof {
 @Override boolean external(long t)throws Exception {
  if(t==0x60038ea5L&&u32(reg("SP")+4)==0xffffffffL){
   long id=reg("D0")&65535;loadStaticFlags(id);
   if(eventFlags.containsKey(id)){
    long pat=eventFlags.get(id),wai=reg("D1"),mode=reg("A1")&255;
    if(mode==1?(pat&wai)==0:(pat&wai)!=wai)throw new CompletionWait("No hardware interrupt/completion supplied for infinite wait flag="+id);
   }
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String result;
  init();trace.clear();
  for(var r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())e.writeRegister(r.getName(),0);
  e.writeRegister("SP",stackTop);
  // Raw6004f99b..f9b5 loads D0 then overwrites it before use. This models
  // only its discarded value, not physical read-barrier ordering or interrupts.
  e.writeMemoryValue(toAddr(0x97f00000L),4,0);
  e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
   public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided registered-path read "+a+" at "+e.getExecutionAddress());}
   public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown registered-path address "+a+" write="+w);}
  });
  try{
   trace.add("INPUT-FIXTURE:isolated zero CPU context; inherited ROM hardware-table selector0; discarded IRQ read97f00000 representative0; no hardware response/interrupt or ordering proof");
   runNative(0x6006fc01L,0,4);
   trace.add(String.format("NATIVE-REGISTRY table=%08x count=%d",u32(0xa32bff10L),u8(0xa32bff14L)));
   check(u8(0xa32bff14L)>0,"Stock registry initialization must select its ROM records");
   initializePropertyRequests();
   e.writeRegister("D0",1);runNative(0x60063f0cL,0xf0,0x40);
   result="RETURNED registered-device request; inspect trace; no measurement or hardware success asserted";
  }catch(Exception ex){result=String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex);}
  trace.add(String.format("FINAL-REGISTRY table=%08x count=%d",u32(0xa32bff10L),u8(0xa32bff14L)));
  Files.write(out.resolve("registered-device-trace.txt"),trace);Files.writeString(out.resolve("registered-device-outcome.txt"),result+"\n");println(result);e.dispose();
 }
}
