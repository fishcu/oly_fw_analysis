// Explicit application-input scenario: use stock worker MODE_START and
// MODE_UPDATE commands, never write worker readiness fields or an AF ack.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3NativeAFModeConsumerProof extends OM3CompleteStaticOSConsumerProof {
 boolean nativeModePrepared;
 final List<String> nativeModeEvidence=new ArrayList<>();
 void modeNote(String s){trace.add(s);nativeModeEvidence.add(s);}
 void prepareNativeAFMode()throws Exception {
  if(nativeModePrepared)return;
  var caller=saveRegisters();long oldTop=stackTop;stackTop=0x700e2000L;
  try{
   for(int command:new int[]{0,2}){
    modeNote(String.format("SUPPLIED-APPLICATION-INPUT queue94 command=%x through stock60700fb4; native state before=%s",command,observedBytes(0xa33f3648L,0x40)));
    e.writeRegister("D0",94);e.writeRegister("D1",command);e.writeRegister("A0",0);
    runNative(0x60700fb4L,0xe0,0x14);
    modeNote(String.format("NATIVE-MODE-RESULT command=%x result=%x state=%s",command,reg("D0"),observedBytes(0xa33f3648L,0x40)));
    check((reg("D0")&65535)==0,"Native mode command must accept the supplied input");
   }
   check(u8(0xa33f3654L)==1,"MODE_START must produce native mode-active state");
   check(u8(0xa33f364fL)!=0||u8(0xa33f3674L)==1,"Native MODE_UPDATE did not meet LOCK_START's baseline mode guard; no readiness bit will be forced");
   nativeModePrepared=true;
  }finally{stackTop=oldTop;restoreRegisters(caller);}
 }
 @Override void beforeNativeButton(long event)throws Exception {prepareNativeAFMode();super.beforeNativeButton(event);}
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);Files.write(out.resolve("native-mode-evidence.txt"),nativeModeEvidence);
   String scope="Explicit native MODE_START0 / MODE_UPDATE2 inputs to queue94 before original buttons. Not proof of their physical boot producer/timing. No worker state or AF acknowledgement written by the fixture. Prepared="+nativeModePrepared+".\n";
   Files.writeString(out.resolve("native-mode-outcome.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
