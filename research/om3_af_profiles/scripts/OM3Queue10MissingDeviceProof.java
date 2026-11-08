// Deliver only the native unregistered-device callback. This models scheduler
// delivery, not a device sample, registration or successful hardware completion.
// @category OM3
import java.nio.file.*;
public class OM3Queue10MissingDeviceProof extends OM3Queue10StatusIndependentProof {
 boolean isolatedMissingDevice;
 int missingCallbacks;
 @Override void loadStaticFlags(long id)throws Exception {
  // Core-0 ROM descriptors after id283 resume at287, not284. The legacy
  // contiguous-prefix loader misses valid static flags287..297.
  if(!eventFlags.containsKey(id)&&id>=287&&id<=297){
   long row=0x6003b878L+12*(id-287);
   check(u32(row)==id&&u32(row+4)<=7,"Stock sparse-tail event-flag descriptor");
   eventFlags.put(id,u32(row+8));flagAttr.put(id,u32(row+4));
   trace.add("MODEL:sparse-tail-static-flag-from-ROM id="+id+" initial="+u32(row+8));return;
  }
  super.loadStaticFlags(id);
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x60072c53L&&reg("A0")==0x600701ecL){
   long packet=reg("A1");
   check((inTask10||isolatedMissingDevice)&&allocations.containsKey(packet)&&allocations.get(packet)==56,
    "Missing-device callback must own its native-size request packet");
   boolean endpoint=false;for(int i=0;i<5;i++)if(u8(packet+2)==u8(0x6012000cL+2*i)&&u8(0x6012000dL+2*i)==1)endpoint=true;
   check(reg("D0")==0&&endpoint&&u32(packet+0x10)==0x60064085L,
    String.format("Missing property request must match ROM endpoint table: D0=%x endpoint=%x callback=%08x",reg("D0"),u8(packet+2),u32(packet+0x10)));
   check(u8(0xa32bff14L)==0,"This comparison retains the empty device registry");
   trace.add(String.format("MODEL:deliver-native-unregistered-device-callback entry=600701ec endpoint=%x; no sample or success supplied",u8(packet+2)));
   var caller=saveRegisters();long oldTop=stackTop;stackTop=0x700d8000L;
   try{e.writeRegister("A0",packet);runNative(0x600701ecL,0,0);}
   finally{stackTop=oldTop;restoreRegisters(caller);}
   missingCallbacks++;e.writeRegister("D0",0); // scheduler accepted; submitter's native result remains 1
   return true;
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);String scope="Conditional immediate delivery of native callback600701ec for empty-registry endpoint from ROM table6012000c, owned56-byte packet, original callback60064085. Scheduler accept result is modeled; native submit failure1 and callback body are not replaced. Deliveries="+missingCallbacks+". No device registered or sample supplied.\n";
   Files.writeString(out.resolve("missing-device-model.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
