// Isolated mode lifecycle through native command submission and worker code.
// No button, frame, lens reply or AF completion is supplied.
// @category OM3
import java.nio.file.*;
public class OM3NativeAFModeProbe extends OM3NativeAFModeConsumerProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String result;
  int tx=currentProgram.startTransaction("Temporary native mode probe mapping");
  try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_mode_probe",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}
  finally{currentProgram.endTransaction(tx,true);}
  profileInit(6,out);
  try{
   heap=0x70010000L;objectID=1000;prepareResident(out);load(1,0xa5);load(4,0x55);coreFixture();
   e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
    public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided native-mode read "+a+" at "+e.getExecutionAddress());}
    public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown native-mode address "+a);}
   });
   prepareNativeAFMode();
   result="RETURNED: native MODE_START and MODE_UPDATE accepted and produced their mode guards; no button/frame/AF result supplied";
  }catch(Exception ex){result=String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex);}
  Files.write(out.resolve("native-mode-trace.txt"),trace);Files.write(out.resolve("native-mode-evidence.txt"),nativeModeEvidence);
  Files.writeString(out.resolve("native-mode-outcome.txt"),result+"\n");println(result);e.dispose();
 }
}
