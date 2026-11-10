// ABI test of proposed table wrappers, stopping at unchanged original handlers.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3NativeHooks extends OM3NativeProfiles {
 byte[] wrapper(long address,long event,long original)throws Exception{
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0);a.x(0x42,4,0x46,8,0x43,12,0x47,16);a.imm(0,event);
  int p=a.b.size();a.x(0xdd);a.w(CODE-(address+p));a.x(0,0);
  a.load8(S+5);a.x(0xa0,0);a.eq("continue");a.x(0x58,4,0x59,8,0x5c,12,0x5d,16,0xf8,0xfe,0x20,0xce,0xf0,0xdf,0,0);a.label("continue");
  a.x(0x58,4,0x59,8,0x5c,12,0x5d,16,0xf8,0xfe,0x20,0xce,0xf0);p=a.b.size();a.x(0xdc);a.w(original-(address+p));return a.finish();
 }
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  int tx=currentProgram.startTransaction("Temporary emulator wrapper mapping; discarded read-only");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  long[] tables={0x6131bd50L,0x6131c290L,0x6131c2a0L,0x6131bd60L},events={HP,AP,AR,HR},originals={0x610b9197L,0x610b962aL,0x610b9653L,0x610b96f0L};
  String[] regs={"D0","D1","D2","D3","A0","A1","A2","A3"};
  try{profileInit(6,out);try{event(0,6,false,false);
   for(int i=0;i<4;i++){
    check(u32(tables[i])==events[i]&&u32(tables[i]+12)==originals[i],"Stock handler table identity");long address=CODE+0x900+i*0x80;byte[] bytes=wrapper(address,events[i],originals[i]);e.writeMemory(toAddr(address),bytes);e.writeMemoryValue(toAddr(tables[i]+12),4,address);
    for(int j=0;j<regs.length;j++)e.writeRegister(regs[j],0x71000000L+j*0x101);
    breakpoints=Set.of(originals[i]);hitBreakpoint=0;runNative(u32(tables[i]+12),0,0);check(hitBreakpoint==originals[i],"Original handler continuation");check(reg("SP")==stackTop,"Wrapper stack restoration");for(int j=0;j<regs.length;j++)check(reg(regs[j])==0x71000000L+j*0x101,"Wrapper register restoration "+regs[j]);
    check(u8(S+4)==new int[]{1,2,1,0}[i],"Wrapper profile ownership");check(u8(0x62a6a0ebL)==(i==1?0:6),"Wrapper detection selection");
    results.add("PASS native table wrapper event="+Long.toHexString(events[i])+": profile transaction completes before original "+Long.toHexString(originals[i])+"; eight general registers and SP preserved; original handler body not executed");breakpoints=Set.of();
   }
   Files.write(out.resolve("native-hook-trace.txt"),trace);Files.write(out.resolve("native-hook-results.txt"),results);println("NATIVE HOOKS: "+results.size()+" PASS");
  }finally{e.dispose();}}catch(Exception ex){Files.write(out.resolve("native-hook-results.txt"),results);Files.write(out.resolve("native-hook-last-trace.txt"),trace);Files.writeString(out.resolve("native-hook-failure.txt"),ex.toString());throw ex;}
 }
}
