// Conditional stock mode-input sequence: family 1a4, then subtype 1a1.
// These are the two photo-mode constructors used by 60afd647/60afd577/60afce68.
// Target/timing are explicit fixtures. All category/backend pointers, callbacks
// and completion events must be produced by the stock code, never supplied.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3StockModeSequenceProof extends OM3StockModeConnectionProof {
 final List<String> buttonResults=new ArrayList<>();
 long[] nativeButtonSequence(){return new long[]{AP,AR};}
 void beforeNativeButton(long event)throws Exception{}
 String nativeButtonLabel(long event){return event==HP?"shutter half press":event==HR?"shutter half release":event==AP?"AF-ON press":"AF-ON release";}
 void drainModeQueue(String label)throws Exception {
  int jobs=0;
  while(observedQueue!=0&&u32(u32(observedQueue+8))!=0){
   check(jobs<128,"Mode sequence did not quiesce within 128 jobs: "+label);
   long job=scheduled(0x60dda845L,observedQueue-8,0,0x30,0xc);
   check(job!=0,"Mode sequence queue mismatch");
   trace.add(String.format("MODE-SEQUENCE:%s job=%08x type=%04x",label,job,u16(job+4)));
   scheduled(0x60dda369L,0x62b76554L,job,0,0);jobs++;
  }
  note(String.format("MODE-SEQUENCE stage=%s jobs=%d router-state=%d active=%08x",label,jobs,u32(0x62b7315cL+0xb4),u32(0x62b7315cL+0xb8)));
 }
 @Override void enqueueConnectionInput()throws Exception {
  super.enqueueConnectionInput();drainModeQueue("family-1a4");
  long category=u32(0x62b7315cL+0xb8);
  check(category!=0&&u32(category)==0x60f18aa8L,"Native photo category must be selected before subtype input");
  long origin=CODE+0x3b00;Asm a=new Asm();a.x(0xcf,0x20);
  a.imm(0,0x20);callAt(a,origin,0x60023fe6L,0,0);
  a.ptr(1,0);callAt(a,origin,0x60aebe7dL,0,4);
  a.ptr(1,category);callAt(a,origin,0x60dd7aedL,0,0);
  a.x(0xdf,0x20,4);e.writeMemory(toAddr(origin),a.finish());decodeCache.clear();
  trace.add("SUPPLIED-INPUT:stock-constructed subtype event-1a1 to natively selected photo category; physical producer/timing unproven");
  runNative(origin,0,0);long message=reg("A0");
  check(allocations.containsKey(message)&&u16(message+4)==0x1a1,"Native subtype input construction");
  e.writeRegister("A0",0x62b76554L);e.writeRegister("A1",message);runNative(0x60dda369L,0,0);
 }
 @Override void beforeOriginal()throws Exception {
  try{super.beforeOriginal();}catch(Exception ex){if(!snapshotComplete)throw ex;}
  // The parent has retained the connection snapshot and intentionally stopped.
  // Continue only when stock code actually activated the physical capture component.
  int first=trace.size();
  try{
   check(u32(0x62b71778L+0xfc)==4,"Capture backend not active after native mode-input sequence");
   long obj=0x700b4000L,ctx=0x700b5000L;
   for(long event:nativeButtonSequence()){
    beforeNativeButton(event);
    long wrapper=translated(CODE+0x900+128*(event==HP?0:event==HR?1:event==AP?2:3));
    e.writeMemoryValue(toAddr(obj),4,event);e.writeMemoryValue(toAddr(ctx),4,event);
    e.writeRegister("A0",obj);e.writeRegister("A1",ctx);e.writeRegister("D0",event);e.writeRegister("D1",0);
    trace.add("SUPPLIED-INPUT:original-button "+nativeButtonLabel(event)+" through inherited resident wrapper and shooting-context fixture");
    runNative(wrapper,0,0);afterOriginal();
    buttonResults.add("RETURNED "+nativeButtonLabel(event)+"; acquisition and hardware completion not asserted");
   }
  }catch(Exception ex){buttonResults.add(String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex));}
  finally{
   note("BUTTON-END "+backendState(0x62b71778L));
   Path out=Paths.get(getScriptArgs()[0]);
   Files.write(out.resolve("mode-sequence-button-results.txt"),buttonResults);
   Files.write(out.resolve("mode-sequence-button-trace.txt"),trace.subList(first,trace.size()));
  }
  throw new Exception("INTENTIONAL STOP after conditional mode sequence and bounded original AF-ON attempt; inspect mode-sequence-button-results.txt");
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Files.writeString(Paths.get(getScriptArgs()[0]).resolve("backend-start-outcome.txt"),
    (snapshotComplete?"CONNECTION OBSERVED; original AF-ON results recorded separately":"BOUNDARY before complete mode-sequence connection snapshot")+
    "\nSupplied stock-constructed inputs 0x1a4 then 0x1a1, with a native queue drain between them. Original button inputs/context are conditional fixtures. No completion reply, backend pointer or lifecycle value supplied. Inherited reset, OS models and silent SCPU remain fixtures.\n");
  }
 }
}
