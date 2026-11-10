// Conditional native capture-composite construction, after declared startup.
// Supplying the parent is a fixture. No backend pointer or AF reply is invented.
// @category OM3
import java.nio.file.*;
public class OM3CaptureFactoryProof extends OM3ReceiverStartupProof {
 @Override void beforeOriginal()throws Exception {
  super.beforeOriginal();
  try{
   dispatching=true;e.writeRegister("A0",0x62b76554L);
   e.writeMemoryValue(toAddr(0x98e000d0L),4,0);trace.add("SUPPLIED-INPUT:hardware counter register 98e000d0=0; diagnostic timestamp fixture only");
   trace.add("SUPPLIED-INPUT:capture factory parent=main-thread; operational-mode event producer not established");
   runNative(0x60dae512L,0,4);
   check(reg("A0")==0x62b71778L,"Capture-composite public interface offset");
   check(u32(0x62b72f2cL)==0x60ebda38L,"Native embedded AE/AF lock controller vtable");
   trace.add(String.format("NATIVE-CAPTURE-FACTORY:interface=%08x aeaf-vtable=%08x",reg("A0"),u32(0x62b72f2cL)));
   Files.deleteIfExists(Paths.get(getScriptArgs()[0]).resolve("capture-factory-boundary.txt"));
   Files.write(Paths.get(getScriptArgs()[0]).resolve("capture-factory-trace.txt"),trace);
  }catch(Exception ex){Files.write(Paths.get(getScriptArgs()[0]).resolve("capture-factory-trace.txt"),trace);Files.writeString(Paths.get(getScriptArgs()[0]).resolve("capture-factory-boundary.txt"),ex.toString());throw ex;}
  finally{dispatching=false;}
 }
}
