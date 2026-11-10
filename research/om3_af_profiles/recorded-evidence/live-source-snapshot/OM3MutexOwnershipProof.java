// Native RTOS mutex ownership checks with explicit kernel-structure fixtures.
// Does not emulate the scheduler or establish the camera's GUI event ordering.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3MutexOwnershipProof extends OM3NativeQueue {
 static class Contended extends Exception {}
 int expectedOwner;
 @Override boolean external(long t)throws Exception {
  if(t==0x600316d2L){e.writeRegister("D0",0);trace.add("MODEL:task-context-eligible");return true;}
  if(t==0x60038bfdL){check(reg("D0")==0xffff8000L,"Native interrupt-mask argument");trace.add("MODEL:kernel-interrupt-mask");return true;}
  if(t==0x60038c74L){trace.add("MODEL:kernel-interrupt-restore");return true;}
  if(t==0x60033eefL){check(expectedOwner==2&&reg("D1")==0x700b500cL,"Unexpected native contended wait");throw new Contended();}
  return super.external(t);
 }
 void fixture(int owner)throws Exception {
  init();expectedOwner=owner;
  e.writeMemoryValue(toAddr(0x8050),4,0);
  e.writeMemoryValue(toAddr(0x97f00004L),4,0x700b0000L);e.writeMemoryValue(toAddr(0x97f00008L),4,0x700b2000L);
  e.writeMemoryValue(toAddr(0x700b0010L),4,0x700b1000L);e.writeMemoryValue(toAddr(0x700b017cL),4,2);
  e.writeMemoryValue(toAddr(0x700b203cL),4,0x700b3000L);e.writeMemoryValue(toAddr(0x700b3016L),2,1);
  e.writeMemoryValue(toAddr(0x700b20e0L),4,0x700b4000L);e.writeMemoryValue(toAddr(0x700b4000L),4,0x700b5000L);
  e.writeMemoryValue(toAddr(0x700b0060L),4,0x700b6000L);e.writeMemoryValue(toAddr(0x700b6000L),4,0x700b7000L);
  e.writeMemoryValue(toAddr(0x700b5008L),2,1);e.writeMemoryValue(toAddr(0x700b5014L),1,2);e.writeMemoryValue(toAddr(0x700b5018L),2,owner);
  e.writeMemoryValue(toAddr(0x700b7010L),2,1);e.writeMemoryValue(toAddr(0x700b700aL),2,10);
  e.writeRegister("D0",0x1001);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  for(int owner:new int[]{1,2}){fixture(owner);try{
   try{runNative(0x60032312L,0xf0,0x14);check(owner==1&&reg("D0")==0xffffffe4L,"Native same-owner mutex acquisition result="+Long.toHexString(reg("D0")));results.add("PASS native mutex take rejects same-task recursive acquisition with -28 before scheduler wait; explicit CPU/domain/task/mutex fixtures and interrupt/context service models");}
   catch(Contended ex){check(owner==2,"Same owner entered scheduler wait");results.add("PASS native different-owner mutex take reaches actual scheduler-wait call; scheduler completion/fairness excluded");}
   Files.write(out.resolve("mutex-ownership-trace-"+owner+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("mutex-ownership-results.txt"),results);println("MUTEX OWNERSHIP: "+results.size()+" PASS");
 }
}
