// Conditional branch probe: supply stock buffer-controller input 120.
// This does NOT prove the producer/timing of 120 or synthesize an AF response.
// @category OM3
public class OM3ReceiverUnblockedProof extends OM3ReceiverStartupProof {
 int suppliedUnblocks;
 @Override void init(){super.init();suppliedUnblocks=0;}
 @Override boolean external(long t)throws Exception {
  if(t!=0x60037769L||dispatching)return super.external(t);
  long id=reg("D0");
  try{return super.external(t);}
  catch(Exception ex){
   long[] sem=semaphores.get(id);
   if(!ex.getMessage().startsWith("Semaphore would block")||sem==null||sem[0]!=0||u32(0x62b7315cL+0xb4)!=7||suppliedUnblocks>=4)throw ex;
   long origin=CODE+0x3900;Asm a=new Asm();a.x(0xcf,0x20);a.imm(0,0x1c);callAt(a,origin,0x60023fe6L,0,0);a.imm(0,0x120);a.ptr(1,0x62b7315cL);callAt(a,origin,0x60dd7a0dL,0,0);a.x(0x91);a.ptr(0,0x62b76554L);callAt(a,origin,0x60dda369L,0,0);a.x(0xdf,0x20,4);e.writeMemory(toAddr(origin),a.finish());decodeCache.clear();
   suppliedUnblocks++;trace.add("SUPPLIED-INPUT:event-120 to blocked buffer controller; producer/timing not proven");dispatching=true;
   try{scheduled(origin,0,0,0,0);}finally{dispatching=false;}
   return super.external(t);
  }
 }
}
