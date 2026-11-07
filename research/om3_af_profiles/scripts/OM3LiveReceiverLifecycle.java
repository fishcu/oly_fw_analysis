// Supplied lifecycle event 19f through its actual stock constructor/dispatcher.
// This is a conditional startup fixture, never evidence of real camera boot.
// @category OM3
public class OM3LiveReceiverLifecycle extends OM3LiveReceiverTrace {
 boolean lifecycleAttempted=false;
 @Override void init(){super.init();lifecycleAttempted=false;}
 @Override void beforeOriginal()throws Exception {super.beforeOriginal();runNative(0x60dbb1a0L,0,0);}
 @Override boolean external(long t)throws Exception {
  if(t==0x60037769L&&!dispatching&&!lifecycleAttempted&&observedQueue!=0){
   long[] sem=semaphores.get(reg("D0"));
   if(sem!=null&&sem[0]==0){
    lifecycleAttempted=true;long head=u32(observedQueue+8),job=u32(head),receiver=u32(job+0x18),origin=CODE+0x3800;
    check(job!=0&&receiver==0x62b73870L,"Lifecycle receiver fixture identification");
    trace.add(String.format("SUPPLIED-LIFECYCLE:stock-event-19f receiver=%08x prior-state=%d",receiver,u32(receiver+0x100)));
    Asm a=new Asm();a.x(0xcf,0x20);a.imm(0,0x1c);callAt(a,origin,0x60023fe6L,0,0);a.ptr(1,receiver);callAt(a,origin,0x60aebe2aL,0,4);a.ptr(1,receiver);callAt(a,origin,0x60dd7aedL,0,0);a.x(0x91);a.ptr(0,0x62b76554L);callAt(a,origin,0x60dda369L,0,0);a.x(0xdf,0x20,4);
    e.writeMemory(toAddr(origin),a.finish());decodeCache.clear();dispatching=true;
    try{scheduled(origin,0,0,0,0);trace.add("SUPPLIED-LIFECYCLE:stock-dispatch-returned:state="+u32(receiver+0x100));}finally{dispatching=false;}
   }
  }
  return super.external(t);
 }
}
