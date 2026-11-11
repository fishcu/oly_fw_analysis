// Native leaf check for the two complete value classes (zero/nonzero) of
// MMIO getter 600216f2 in status builder 600644d5, under source flag zero.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3StatusPropertyProbe extends OM3CaptureAfTaskProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);List<String> results=new ArrayList<>();
  for(long value:new long[]{0,0xffffffffL}){
   init();trace.clear();e.writeRegister("LIR",0);e.writeRegister("LAR",0);
   e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
    public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided leaf read "+a+" at "+e.getExecutionAddress());}
    public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown leaf address "+a);}
   });
   try{
    check(u8(0x6299555eL)==0,"Declared reset source flag must be zero");
    e.writeMemoryValue(toAddr(0x97f00090L),4,value);
    e.writeMemory(toAddr(0x700a0000L),new byte[]{(byte)0xa5,(byte)0xa5,(byte)0xa5});
    e.writeRegister("A0",0x700a0000L);runNative(0x600644d5L,0,0);
    String bytes=hex(0x700a0000L,3);
    check(reg("D0")==255&&bytes.equals("000001"),"Native reset-source result must be independent of the MMIO value");
    results.add(String.format("RETURNED mmio=%08x source-flag=0 status=%02x bytes=%s",value,reg("D0"),bytes));
   }catch(Exception ex){results.add(String.format("BOUNDARY mmio=%08x pc=%08x: %s",value,e.getExecutionAddress().getOffset(),ex));}
   finally{Files.write(out.resolve(String.format("status-trace-%08x.txt",value)),trace);e.dispose();}
  }
  Files.write(out.resolve("status-property-results.txt"),results);for(String r:results)println(r);
 }
}
