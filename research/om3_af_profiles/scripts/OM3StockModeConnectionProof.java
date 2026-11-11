// Conditional input experiment: replace the direct event-114 fixture with a
// stock-constructed type-1a4 mode-selection input. Let stock code construct its
// category hierarchy, register its observers and produce connection requests.
// Input timing remains a fixture; no backend/result/lifecycle value is written.
// @category OM3
import java.nio.file.*;
public class OM3StockModeConnectionProof extends OM3BackendNotifyTrace {
 @Override String state(long p){
  try{if(u32(p)==0x60f10f50L)return backendState(p);
   return String.format("obj=%08x vt=%08x raw+b0=%08x raw+b4=%08x raw+a8=%08x event=%08x",p,u32(p),u32(p+0xb0),u32(p+0xb4),u32(p+0xa8),u32(p+0x68));
  }catch(Exception ex){return "unprovided "+ex;}
 }
 @Override void enqueueConnectionInput()throws Exception {
  check(u32(0x62b73870L)==0x60f11388L,"Native mode-controller class");
  check(u32(0x62b73870L+0x100)==11,"Mode controller must be in its observed idle state");
  long origin=CODE+0x3a00;Asm a=new Asm();
  a.x(0xcf,0x20);a.imm(0,0x20);callAt(a,origin,0x60023fe6L,0,0);
  a.ptr(1,0);callAt(a,origin,0x60aebee9L,0,4);
  a.ptr(1,0x62b73870L);callAt(a,origin,0x60dd7aedL,0,0);
  a.x(0xdf,0x20,4);e.writeMemory(toAddr(origin),a.finish());decodeCache.clear();
  trace.add("SUPPLIED-INPUT:stock-constructed event-1a4 to mode controller; physical producer/timing unproven; no direct event-114 fixture");
  runNative(origin,0,0);long message=reg("A0");
  check(allocations.containsKey(message)&&u16(message+4)==0x1a4,"Native mode input construction");
  e.writeRegister("A0",0x62b76554L);e.writeRegister("A1",message);runNative(0x60dda369L,0,0);
 }
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc==0x60db1753L||pc==0x60dd39c2L||pc==0x60dd4a4fL||pc==0x60dbf5f7L||pc==0x60db216bL)
   note(String.format("STOCK-CONNECTION pc=%08x A0=%08x A1=%08x D0=%08x",pc,reg("A0"),reg("A1"),reg("D0")));
  return super.instruction(ins);
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Files.writeString(Paths.get(getScriptArgs()[0]).resolve("backend-start-outcome.txt"),
    (snapshotComplete?"OBSERVATION COMPLETE: conditional native mode-selection connection; stopped before original buttons":"BOUNDARY in conditional native mode-selection experiment; inspect retained traces")+
    "\nSupplied stock-constructed mode input 0x1a4. No completion reply, backend pointer or lifecycle value supplied by this subclass. Inherited reset, OS models and silent SCPU remain explicit fixtures.\n");
  }
 }
}
