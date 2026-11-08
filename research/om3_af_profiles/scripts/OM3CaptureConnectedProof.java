// Conditional event-114 backend connection using the native capture factory.
// Event production/timing and physical device completion are not established.
// @category OM3
import java.nio.file.*;
public class OM3CaptureConnectedProof extends OM3CaptureFactoryProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.deleteIfExists(out.resolve("capture-connection-outcome.txt"));
  try{super.run();Files.writeString(out.resolve("capture-connection-outcome.txt"),"RETURNED conditional connection probe; inspect original-handler results; physical completion excluded\n");}
  catch(Exception ex){
   if(!ex.toString().contains("Unprovided startup read 97f00004 at 600303f5"))throw ex;
   Files.writeString(out.resolve("capture-connection-outcome.txt"),"BOUNDARY native capture initialization reaches unprovided kernel task/object state at 97f00004, pc=600303f5 via 600303db and 6004f3bd; no successful AF response established\n");
   println("BOUNDARY native capture initialization requires unprovided kernel task/object state; this is not a passing AF integration test");
  }
 }
 // Input seam for separately labelled experiments. The default body is the
 // original direct event-114 fixture; the shared native queue drain is unchanged.
 void enqueueConnectionInput()throws Exception {
  long origin=CODE+0x3a00;Asm a=new Asm();a.x(0xcf,0x20);a.imm(0,0x20);callAt(a,origin,0x60023fe6L,0,0);a.imm(0,0x114);a.ptr(1,0x62b7315cL);callAt(a,origin,0x60dd7a0dL,0,0);
  // Native message payload layout is read by 60db36aa through 60dd9d65.
  a.x(0xdf,0x20,4);
  e.writeMemory(toAddr(origin),a.finish());decodeCache.clear();
  trace.add("SUPPLIED-INPUT:event-114 backend=62b71778; native factory result; producer/timing unproven");runNative(origin,0,0);long message=reg("A0");check(allocations.containsKey(message)&&u16(message+4)==0x114,"Native connection input construction");e.writeMemoryValue(toAddr(message+0x1c),4,0x62b71778L);e.writeRegister("A0",0x62b76554L);e.writeRegister("A1",message);runNative(0x60dda369L,0,0);
 }
 @Override void beforeOriginal()throws Exception {
  super.beforeOriginal();
  try{
   dispatching=true;
   enqueueConnectionInput();
   int jobs=0;while(observedQueue!=0&&u32(u32(observedQueue+8))!=0){check(jobs<128,"Capture connection did not quiesce within 128 jobs");long job=scheduled(0x60dda845L,observedQueue-8,0,0x30,0xc);check(job!=0,"Native capture connection queue mismatch");trace.add(String.format("CONNECTION:native-message id=%04x",u16(job+4)));scheduled(0x60dda369L,0x62b76554L,job,0,0);jobs++;}
   trace.add(String.format("CONNECTION:quiescent jobs=%d state=%d backend=%08x requested=%08x",jobs,u32(0x62b7315cL+0xb4),u32(0x62b7315cL+0xb8),u32(0x62b7315cL+0xbc)));
   Files.deleteIfExists(Paths.get(getScriptArgs()[0]).resolve("capture-connection-boundary.txt"));
   Files.write(Paths.get(getScriptArgs()[0]).resolve("capture-connection-trace.txt"),trace);
  }catch(Exception ex){trace.add(String.format("CONNECTION:boundary state=%d backend=%08x requested=%08x",u32(0x62b7315cL+0xb4),u32(0x62b7315cL+0xb8),u32(0x62b7315cL+0xbc)));Files.write(Paths.get(getScriptArgs()[0]).resolve("capture-connection-trace.txt"),trace);Files.writeString(Paths.get(getScriptArgs()[0]).resolve("capture-connection-boundary.txt"),ex.toString());throw ex;}
  finally{dispatching=false;}
 }
}
