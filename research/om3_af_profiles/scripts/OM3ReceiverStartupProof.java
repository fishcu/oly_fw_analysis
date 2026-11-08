// Native framework getter, stock prototype constructor and supplied start event.
// Strict startup diagnostics; no synthesized positive device/AF response.
// @category OM3
import java.nio.file.*;
public class OM3ReceiverStartupProof extends OM3LiveReceiverTrace {
 @Override boolean external(long t)throws Exception {
  if(t==0x60030bcfL){long id=reg("D0")&65535;check(eventFlags.containsKey(id),"Clearing unknown event flag "+id);eventFlags.put(id,eventFlags.get(id)&reg("D1"));e.writeRegister("D0",0);trace.add("MODEL:owned-eventflag-clear-mask:"+id);return true;}
  return super.external(t);
 }
 void initializeReceiverStatics()throws Exception{for(long constructor:new long[]{0x60db2a87L,0x60dbb1a0L,0x60dbd655L})runNative(constructor,0,0);}
 @Override void beforeOriginal()throws Exception {
  super.beforeOriginal();
  e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
   public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided startup read "+a+" at "+e.getExecutionAddress());}
   public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown startup address "+a);}
  });
  try{
   for(int id=1;id<=133;id++){long descriptor=0x6003a214L+(id-1)*16;check(u32(descriptor)==id&&u32(descriptor+4)<=1&&u32(descriptor+8)<=u32(descriptor+12)&&u32(descriptor+12)>0&&u32(descriptor+12)<65536,"Static semaphore ROM descriptor "+id);semaphores.putIfAbsent((long)id,new long[]{u32(descriptor+8),u32(descriptor+12)});}
   trace.add("MODEL:133-static-semaphore-descriptors-from-stock-ROM");
   dispatching=true;initializeReceiverStatics();runNative(0x60dd7bb4L,0,4);check(reg("A0")==0x62b76554L,"Native main-thread singleton");runNative(0x60db2addL,0,4);
   check(u32(0x62b730dcL)==0x60f114b0L&&u32(0x62b73870L)==0x60f11388L,"Native framework singleton layout");
   long origin=CODE+0x3800;Asm a=new Asm();a.x(0xcf,0x20);a.imm(0,0x1c);callAt(a,origin,0x60023fe6L,0,0);callAt(a,origin,0x60aebe2aL,0,4);a.ptr(1,0x62b73870L);callAt(a,origin,0x60dd7aedL,0,0);a.x(0x91);a.ptr(0,0x62b76554L);callAt(a,origin,0x60dda369L,0,0);a.x(0xdf,0x20,4);e.writeMemory(toAddr(origin),a.finish());decodeCache.clear();
   trace.add("SUPPLIED-STARTUP:event-19f before original button input");scheduled(origin,0,0,0,0);
   int jobs=0;while(observedQueue!=0&&u32(u32(observedQueue+8))!=0){check(jobs<128,"Startup did not quiesce within 128 native messages");long job=scheduled(0x60dda845L,observedQueue-8,0,0x30,0xc);check(job!=0,"Native startup queue mismatch");trace.add(String.format("STARTUP:native-message id=%04x",u16(job+4)));scheduled(0x60dda369L,0x62b76554L,job,0,0);jobs++;}
   trace.add("STARTUP:native-queue-quiescent:jobs="+jobs+":root-state="+u32(0x62b73870L+0x100));
   Files.deleteIfExists(Paths.get(getScriptArgs()[0]).resolve("startup-boundary.txt"));
   Files.write(Paths.get(getScriptArgs()[0]).resolve("startup-trace.txt"),trace);
  }catch(Exception ex){Files.write(Paths.get(getScriptArgs()[0]).resolve("startup-failure-trace.txt"),trace);Files.writeString(Paths.get(getScriptArgs()[0]).resolve("startup-boundary.txt"),ex.toString());throw ex;}
  finally{dispatching=false;}
 }
}
