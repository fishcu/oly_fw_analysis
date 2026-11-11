// Verify reuse within the fixed arena, preservation of live blocks and failure
// on real exhaustion. This is an OS allocation model test, not firmware proof.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3ReusingHeapProbe extends OM3ReusingHeapProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String result;
  init();trace.clear();
  try{
   long base=0x70010000L,end=0x70040000L;heap=end;allocations.clear();
   List<long[]> live=new ArrayList<>();live.add(new long[]{base,0x400});
   for(long p=base+0x800;p<end;){long n=Math.min(0x10000,end-p);live.add(new long[]{p,n});p+=n;}
   for(long[] block:live){allocations.put(block[0],block[1]);byte[] data=new byte[(int)block[1]];Arrays.fill(data,(byte)0x6d);e.writeMemory(toAddr(block[0]),data);}
   byte[] hole=new byte[0x400];Arrays.fill(hole,(byte)0xcc);e.writeMemory(toAddr(base+0x400),hole);
   e.writeRegister("D0",896);check(external(0x60023fe6L),"Allocation handled");
   long reused=reg("A0");check(reused==base+0x400,"Reuse the freed gap inside the reserved arena");
   for(byte b:e.readMemory(toAddr(reused),896))check(b==0,"Requested allocation cleared");
   for(byte b:e.readMemory(toAddr(reused+896),0x400-896))check(b==(byte)0xcc,"Unallocated tail unchanged");
   for(long[] block:live)for(byte b:e.readMemory(toAddr(block[0]),(int)block[1]))check(b==0x6d,"Live allocation overwritten");
   e.writeRegister("A0",reused);external(0x60024018L);
   e.writeRegister("D0",0x400);external(0x60023fe6L);check(reg("A0")==reused,"Native free made the whole gap reusable");
   boolean exhausted=false;try{e.writeRegister("D0",16);external(0x60023fe6L);}catch(Exception ex){if(!ex.getMessage().startsWith("Heap exhausted"))throw ex;exhausted=true;}
   check(exhausted,"A completely occupied arena must fail without expanding into stacks");
   result="RETURNED: 896-byte gap reuse, preserved live canaries and unused tail, free/reuse, and bounded exhaustion verified; arena not enlarged";
  }catch(Exception ex){result="BOUNDARY: "+ex;}
  Files.write(out.resolve("heap-reuse-trace.txt"),trace);Files.writeString(out.resolve("heap-reuse-outcome.txt"),result+"\n");println(result);e.dispose();
 }
}
