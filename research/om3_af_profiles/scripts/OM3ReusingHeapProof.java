// Keep the original bounded heap arena and bump behavior, but reuse gaps left
// by native frees when its high-water mark reaches the arena limit.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3ReusingHeapProof extends OM3PropertyFailurePathProof {
 int reusedAllocations;
 @Override boolean external(long t)throws Exception {
  if(t==0x60023fe6L){
   long n=reg("D0"),limit=0x70040000L;
   if(n>0&&n<=0x10000&&heap+n>=limit){
    long cursor=0x70010000L,chosen=0;
    for(var entry:new TreeMap<Long,Long>(allocations).entrySet()){
     long p=entry.getKey();if(p<0x70010000L||p>=limit)continue;
     if(cursor+n<=p){chosen=cursor;break;}
     cursor=Math.max(cursor,(p+entry.getValue()+15)&~15L);
    }
    if(chosen==0&&cursor+n<limit)chosen=cursor;
    check(chosen!=0,"Heap exhausted inside reserved arena; no live allocation or stack overwritten");
    allocations.put(chosen,n);e.writeMemory(toAddr(chosen),new byte[(int)n]);e.writeRegister("A0",chosen);
    reusedAllocations++;trace.add(String.format("MODEL:reuse-freed-heap-gap address=%08x size=%d high-water=%08x; arena unchanged",chosen,n,heap));
    return true;
   }
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);String scope="Bounded heap model reuses gaps in live-allocation map only after original bump capacity is reached. Arena remains70010000..70040000, allocation limit64KiB, native frees retained. Reused allocations="+reusedAllocations+". Not the camera's complete heap implementation.\n";
   Files.writeString(out.resolve("heap-reuse-model.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
