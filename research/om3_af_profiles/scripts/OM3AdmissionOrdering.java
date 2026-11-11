// Adversarial instruction-boundary scheduling, not proof the stock UI permits it.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.app.util.PseudoInstruction;
public class OM3AdmissionOrdering extends OM3RevisionChecks {
 boolean inject=false,seen=false;long stateAddress,releaseEvent;
 @Override boolean instruction(PseudoInstruction ins)throws Exception{
  byte[] bytes=ins.getBytes();if(inject&&bytes.length==6&&(bytes[0]&255)==0xfc&&(bytes[1]&255)==0x82){long a=0;for(int i=0;i<4;i++)a|=(long)(bytes[2+i]&255)<<(8*i);if(a==stateAddress){inject=false;seen=true;long d0=reg("D0");e.writeRegister("D0",releaseEvent);child(RECONCILE,0);e.writeRegister("D0",d0);trace.add("INJECTED:later-release-before-parent-held-store");}}
  return super.instruction(ins);
 }
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary admission schedule probe mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  for(int button=0;button<2;button++){profileInit(6,out);try{revisedEvent(0);stateAddress=S+button;releaseEvent=button==0?HR:AR;seen=false;inject=true;revisedEvent(button==0?HP:AP);check(seen&&u8(stateAddress)==1&&u8(S+5)==0,"Expected admission ordering counterexample changed");results.add("BOUNDARY button="+button+": injected later release completes before parent held-state store; parent then leaves button held with success status. Requires serialized event ownership or atomic queued admission; stock dispatcher reachability of this schedule is unproved");Files.write(out.resolve("admission-ordering-trace-"+button+".txt"),trace);}finally{e.dispose();}}
  Files.write(out.resolve("admission-ordering-results.txt"),results);println("ADMISSION ORDERING: 2 BOUNDARY counterexamples");
 }
}
