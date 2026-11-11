// Continuation of OM3CaptureAfTaskProof (labelled STOCK-RESET scenario, SCPU modelled as silent; not a normal boot).
// The parent chain's connection input posts a supplied event 0x114 naming capture interface 0x62b71778 to router
// 0x62b7315c. Static decode (8 Nov) and an OM-Emu cross-check show that stock code instead:
//   - builds the capture container singleton 0x62b76180 (getter 60dd47a8, flag 6036d6d0, class 60f18c20), which holds
//     its own router at +0x70 (0x62b761f0, class 60f11758) and the capture owner at +0x1fc (0x62b7637c, 60f18dd8);
//   - attaches the capture composite to that owner with 60dd4a4f (owner vtable slot 60f18ea0): factory 60dd4ad2,
//     interface vt+0xb8(owner), two channel connections 60dbcc7f from owner+0x148's router to the interface, and
//     registration of the interface under key D0 in the owner's backend list (60dcaf5b);
//   - in owner state 10 (60dd504d via 60dd5045) looks up backend key 1 (60dd4af6 returns 1; 60dcb0bc), sends it a
//     start message and posts 0x114 naming it to the owner's router.
// This probe replaces the supplied event with those stock calls on the stock objects. Labelled supplied inputs:
//   SUPPLIED-INPUT:container parent = main thread 0x62b76554 (as OM3CaptureFactoryProof supplies for 60dae512)
//   SUPPLIED-INPUT:attach call 60dd4a4f(owner, key 1) and state-10 entry 60dd5045(owner) are called directly; their
//     stock producers (the higher category's attach 60dd39c2 and the owner's own transition) are not run.
// Nothing else is written. No reply, status or AF result is synthesized. Each stage drains the native event queue
// and records both routers. Run with -Dom3.attachOnly to stop after the attach stage.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CaptureAttachProof extends OM3CaptureAfTaskProof {
 static final long CONTAINER=0x62b76180L,OWNER=CONTAINER+0x1fc,ROUTER2=CONTAINER+0x70,ROUTER1=0x62b7315cL,IFACE=0x62b71778L,MAIN=0x62b76554L;
 final List<String> attachLog=new ArrayList<>();
 void alog(String s){log(s);attachLog.add(s);}
 String routers(){
  StringBuilder b=new StringBuilder();
  for(long r:new long[]{ROUTER1,ROUTER2}){try{b.append(String.format("router %08x vt=%08x state=%d active=%08x requested=%08x; ",r,u32(r),u32(r+0xb4),u32(r+0xb8),u32(r+0xbc)));}catch(Exception ex){b.append(String.format("router %08x unreadable; ",r));}}
  return b.toString();
 }
 int drain(String stage)throws Exception {
  int jobs=0;
  while(observedQueue!=0&&u32(u32(observedQueue+8))!=0){
   check(jobs<256,"Capture "+stage+" did not quiesce within 256 jobs");
   long job=scheduled(0x60dda845L,observedQueue-8,0,0x30,0xc);check(job!=0,"Native capture queue mismatch");
   alog(String.format("ATTACH-%s:native-message id=%04x target=%08x",stage,u16(job+4),u32(job+0x18)));
   scheduled(0x60dda369L,MAIN,job,0,0);jobs++;}
  alog(String.format("ATTACH-%s:quiescent jobs=%d %s",stage,jobs,routers()));
  return jobs;
 }
 @Override void enqueueConnectionInput()throws Exception {
  alog("ATTACH:before "+routers());
  // Stage 1: stock container singleton (constructs container, its router and the capture owner).
  alog("SUPPLIED-INPUT:container parent=main-thread 62b76554 (as for the capture factory); producer of the call not run");
  e.writeRegister("A0",MAIN);runNative(0x60dd47a8L,0,4);
  long owner=reg("A0");
  check(owner==OWNER,String.format("Capture owner address %08x",owner));
  check(u32(CONTAINER)==0x60f18c20L&&u32(OWNER)==0x60f18dd8L&&u32(ROUTER2)==0x60f11758L,"Stock container/owner/router vtables");
  alog(String.format("ATTACH:container=%08x owner=%08x owner+0x148=%08x owner+0x12c=%08x %s",CONTAINER,owner,u32(owner+0x148),u32(owner+0x12c),routers()));
  // Stage 2: stock attach of the capture composite to the owner, backend key 1.
  alog("SUPPLIED-INPUT:direct call 60dd4a4f(owner, key 1); stock caller (owner vtable slot 60f18ea0) not run");
  e.writeRegister("A0",owner);e.writeRegister("D0",1);runNative(0x60dd4a4fL,0xf0,0x8);   // prologue movm [d2,d3,a2,a3]; add -0x8,sp
  alog(String.format("ATTACH:attached result=%08x owner+0x12c=%08x %s",reg("A0"),u32(owner+0x12c),routers()));
  drain("ATTACH");
  if(System.getProperty("om3.attachOnly")!=null)return;
  // Stage 3: stock owner state-10 entry: picks backend key 1, sends it a start message, posts 0x114 to its router.
  alog("SUPPLIED-INPUT:direct call 60dd5045(owner) (owner state 10 entry); the owner's own transition is not run");
  e.writeRegister("A0",owner);runNative(0x60dd5045L,0,4);
  alog(String.format("ATTACH:state10 owner+0x12c=%08x owner+0x150=%d %s",u32(owner+0x12c),u32(owner+0x150),routers()));
  drain("START");
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);
  try{super.run();}finally{
   attachLog.add("final: "+routers());
   Files.write(out.resolve("attach-log.txt"),attachLog);
  }
 }
}
