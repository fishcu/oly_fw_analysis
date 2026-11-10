// Execute the stock create-mutex context rejection; no successful allocation is modeled or attempted.
// Kernel control block/core ID/context bytes are explicit supplied unit-test inputs, not hardware observations.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3NativeMutexContextProbe extends OM3TaskContextMutexProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);List<String> results=new ArrayList<>();String outcome="NOT RUN";
  profileInit(6,out);
  try{
   long kcb=0x700b7000L,nest=0x700b7200L,packet=0x700b7300L;
   e.writeMemory(toAddr(kcb),new byte[0x20]);e.writeMemory(toAddr(nest),new byte[2]);e.writeMemory(toAddr(packet),new byte[8]);
   e.writeMemoryValue(toAddr(0x8050),4,0);e.writeMemoryValue(toAddr(0x97f00004L),4,kcb);e.writeMemoryValue(toAddr(kcb+0x1c),4,nest);e.writeMemoryValue(toAddr(packet),4,2);
   e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
    public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided native-context read "+a+" at "+e.getExecutionAddress());}
    public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown native-context address "+a);}
   });
   for(int[] c:new int[][]{{1,0},{0,1}}){
    e.writeMemoryValue(toAddr(nest),1,c[0]);e.writeMemoryValue(toAddr(nest+1),1,c[1]);e.writeRegister("A0",packet);
    int before=objectID;runNative(0x60030659L,0xa0,0x10);
    check(reg("D0")==0xffffffe7L&&objectID==before,"Native E_CTX with no object allocation");
    results.add("PASS native60030659 packet attr=2 nest="+c[0]+" context1="+c[1]+" returns ffffffe7 (-25); root stack restored; no modeled create or allocation");
   }
   outcome="PASS both stock context-rejection branches; supplied kernel/core/context unit fixture; physical IRQ and successful native allocation untested";
  }catch(Exception ex){outcome="BOUNDARY at "+e.getExecutionAddress()+": "+ex;}
  Files.writeString(out.resolve("native-context-outcome.txt"),outcome+"\n");Files.write(out.resolve("native-context-results.txt"),results);Files.write(out.resolve("native-context-trace.txt"),trace);println(outcome);e.dispose();
 }
}
