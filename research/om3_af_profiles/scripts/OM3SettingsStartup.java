// Continue stock settings startup without inventing NVM contents or completion.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.pcode.memstate.MemoryFaultHandler;
import ghidra.program.model.address.Address;
public class OM3SettingsStartup extends OM3FullShooting {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);init();trace.clear();
  e.setMemoryFaultHandler(new MemoryFaultHandler(){public boolean uninitializedRead(Address a,int n,byte[] d,int o){throw new IllegalStateException("Missing startup input PC="+e.getExecutionAddress()+" address="+a+" bytes="+n);}public boolean unknownAddress(Address a,boolean w){throw new IllegalStateException("Unknown startup address "+a+" write="+w);}});
  try{try{runNative(0x60062691L,0,0x30);Files.writeString(out.resolve("settings-startup-result.txt"),"RETURNED native core startup; D0="+Long.toHexString(reg("D0"))+"; storage and boot completion not asserted");}catch(Exception ex){Files.writeString(out.resolve("settings-startup-result.txt"),"BOUNDARY native core startup: "+ex);}
   Files.write(out.resolve("settings-startup-trace.txt"),trace);
  }finally{e.dispose();}
 }
}
