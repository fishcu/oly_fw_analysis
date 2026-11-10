// Inject a negative RTOS wait result; do not invent a positive AF response.
// @category OM3
public class OM3LiveShootingErrors extends OM3LiveShooting {
 int injectedWaitErrors;
 @Override void init(){super.init();injectedWaitErrors=0;}
 @Override boolean external(long t)throws Exception {
  if(t==0x60037769L){
   long id=reg("D0");long[] sem=semaphores.get(id);
   if(sem!=null&&sem[0]==0&&reg("D1")==1000){
    if(injectedWaitErrors==2)throw new Exception("Stock response wait retried after two injected negative results; receiving-task response still required");
    e.writeRegister("D0",0xffffffceL);injectedWaitErrors++;
    trace.add("INJECTED:empty-response-wait-negative-result:"+id+":ffffffce");return true;
   }
  }
  return super.external(t);
 }
 @Override void afterOriginal()throws Exception {
  check(!mutexes.get(u32(OWN+20)),"Wrapper retained dedicated mutex after original handler returned");
  trace.add("CHECK:original-return-unlocked:injected-wait-errors="+injectedWaitErrors);
 }
}
