// Verify stock missing-device result and its native software notification.
// @category OM3
import java.nio.file.*;
public class OM3MissingDeviceCallbackProbe extends OM3Queue10MissingDeviceProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String outcome;
  init();trace.clear();e.writeRegister("LIR",0);e.writeRegister("LAR",0);
  e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
   public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided callback read "+a+" at "+e.getExecutionAddress());}
   public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown callback address "+a);}
  });
  try{
   for(int i=0;i<5;i++){
   long packet=0x700a0000L+0x100*i,cell=packet+0x80,flag=u16(0x60043164L),endpoint=u8(0x6012000cL+2*i);
   loadStaticFlags(flag);eventFlags.put(flag,0L);e.writeMemory(toAddr(packet),new byte[56]);allocations.put(packet,56L);
   e.writeMemoryValue(toAddr(packet+2),1,endpoint);e.writeMemoryValue(toAddr(packet+0x10),4,0x60064085L);
   e.writeMemoryValue(toAddr(packet+0x14),4,cell);e.writeMemoryValue(toAddr(cell),4,1);
   isolatedMissingDevice=true;e.writeRegister("A0",packet);runNative(0x6006fd32L,0xb0,0x10);
   check(reg("D0")==1&&missingCallbacks==i+1,"Native submit must retain missing-device result1");
   check((eventFlags.get(flag)&1)!=0,"Native completion callback must notify the supplied flag bit");
   check(u8(0xa32bff14L)==0,"No device registry or sample introduced");
   trace.add("NATIVE-MISSING-ENDPOINT-RESULT endpoint="+endpoint+" submit-result=1 completion-bit=1 registry-empty=true");
   }
   outcome="RETURNED: five ROM-listed endpoints; native missing-device submit result1; native callback delivered flag notification; registry remains empty; no sample or successful device result supplied";
  }catch(Exception ex){outcome=String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex);}
  Files.write(out.resolve("missing-device-trace.txt"),trace);Files.writeString(out.resolve("missing-device-outcome.txt"),outcome+"\n");println(outcome);e.dispose();
 }
}
