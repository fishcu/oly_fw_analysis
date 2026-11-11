// Full-size decoded main component, actual stock validator and checksum loop.
// Diagnostic output alone is modeled. No update service or flash operation.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3FullComponentProof extends OM3NativeQueue {
 long checksumCalls;
 @Override boolean external(long t)throws Exception {
  if(t==0x60023f59L)return true;
  if(t==0x60155816L){
   long sp=reg("SP"),pc=reg("PC"),mdr=reg("MDR"),top=0x70050000L,stop=0x70ffe000L;
   e.writeMemoryValue(toAddr(top),4,stop);e.writeMemoryValue(toAddr(top-4),4,reg("D2"));
   e.writeRegister("SP",top-4);e.writeRegister("MDR",stop);e.setBreakpoint(toAddr(stop));
   try{check(e.run(toAddr(t),null,monitor),"Full checksum execution: "+e.getLastError());check(e.getExecutionAddress().getOffset()==stop&&reg("SP")==top,"Full checksum return ABI");}
   finally{e.clearBreakpoint(toAddr(stop));e.writeRegister("SP",sp);e.writeRegister("PC",pc);e.writeRegister("MDR",mdr);}
   checksumCalls++;trace.add("NATIVE:full-component-checksum");return true;
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=getScriptArgs().length>1&&Files.exists(out.resolve("full-component-results.txt"))?new ArrayList<>(Files.readAllLines(out.resolve("full-component-results.txt"))):new ArrayList<>();
  for(String name:(getScriptArgs().length>1?new String[]{getScriptArgs()[1]}:new String[]{"stock","changed-unrepaired","changed-repaired","wrong-trailer"})){
   init();try{checksumCalls=0;byte[] image=Files.readAllBytes(out.resolve(name+".decoded-research-only.bin"));check(image.length==0x2000000,"Full main component length");
    long p=0x71000000L,d=0x700b0000L;e.writeMemory(toAddr(p),image);e.writeMemory(toAddr(d),new byte[32]);e.writeMemoryValue(toAddr(d+4),4,p);e.writeMemoryValue(toAddr(d+16),4,1);
    e.writeRegister("A0",d);e.writeRegister("D0",0);long before=System.nanoTime();runNative(0x6106b712L,0xf0,0x14);
    long expected=name.equals("changed-unrepaired")?0x3211:name.equals("wrong-trailer")?0x3202:0;
    check(reg("D0")==expected,"Validator result "+name+":"+Long.toHexString(reg("D0")));check(checksumCalls==(name.equals("wrong-trailer")?0:1),"Checksum reachability");
    results.add("PASS full 33554432-byte decoded main component: "+name+", native validator result="+Long.toHexString(expected)+", native full checksum calls="+checksumCalls+", seconds="+((System.nanoTime()-before)/1e9)+"; no device/update-service/boot/flash assertion");
    Files.write(out.resolve("full-component-results.txt"),results);println(results.get(results.size()-1));
   }finally{e.dispose();}
  }
 }
}
