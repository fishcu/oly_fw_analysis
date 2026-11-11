// Original button bodies with native mutable core settings and serialized hooks.
// Camera inputs are supplied; NVM cache and kernel services remain models.
// @category OM3
public class OM3LiveShooting extends OM3LiveProfiles {
 @Override long ownedState(){return OWN;}
 @Override void afterOriginal()throws Exception {check(!mutexes.get(u32(OWN+20)),"Original handler returned while dedicated mutex remained held");trace.add("CHECK:original-return-unlocked");}
 @Override void coreFixture()throws Exception {initializeRAM();}
 @Override void beforeOriginal()throws Exception {
  // Explicit valid HDMI-information setting used by this shooting fixture.
  setting(0x7e61,0,1);
  // ROM's static semaphore descriptor: ID, attributes, initial count, maximum.
  long descriptor=0x6003a7b4L;check(u32(descriptor)==91&&u32(descriptor+4)==0&&u32(descriptor+8)==1&&u32(descriptor+12)==1,"Static display semaphore descriptor");
  semaphores.put(91L,new long[]{u32(descriptor+8),u32(descriptor+12)});
  // Apply the declared shooting fixtures to registered data, so native getters
  // and direct pointer bindings observe the same values. This is fixture setup,
  // not a claim that these values were read from a camera.
  for(java.util.Map.Entry<Long,Integer> entry:settings.entrySet()){
   int key=(int)(entry.getKey()>>>16),index=(int)(entry.getKey()&65535),width=(key&3)==0?4:key&3;long meta=0xa32a990cL+8*(key>>4),p=u32(meta+4);
   check(p!=0&&index<u16(meta+2),"Shooting fixture key missing from native metadata "+Integer.toHexString(key));
   e.writeMemoryValue(toAddr(p+(long)index*width),width,entry.getValue());
   if(p>=0x62000000L&&p<0x64000000L)e.writeMemoryValue(toAddr(p+0x40000000L+(long)index*width),width,entry.getValue());
  }
 }
 @Override public void run()throws Exception {probeOriginal=false;shootingRun();}
}
