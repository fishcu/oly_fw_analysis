// Execute original shooting bodies through the relocated serialized wrappers.
// @category OM3
public class OM3SerializedShooting extends OM3SerializedProfiles {
 @Override void load(int section,int fill)throws Exception {
  super.load(section,fill);
  // Explicit constructor stage after section loading. This does not assert that
  // the section loader itself executes constructors or that whole boot ran.
  if(section==4)runNative(0x602153fbL,0xa0,0xc);
 }
 @Override public void run()throws Exception {probeOriginal=false;shootingRun();}
}
