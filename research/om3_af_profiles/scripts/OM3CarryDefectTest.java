// Isolated CPU-model test for the MN10300 aliased register-add carry defect.
// Emulates the REAL instructions in OM3_main_full through EmulatorHelper, which
// decodes with the compiled .sla directly. Run unchanged before and after the
// language fix; compare carry-test-result.txt. Read-only; no firmware change.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.program.model.address.Address;
import java.nio.file.*;
import java.util.*;
public class OM3CarryDefectTest extends GhidraScript {
 EmulatorHelper e;
 final long ADD=0x6004c28cL, ROL=0x6004c28dL; // add D0,D0 ; rol D1  (normalize loop body of 0x6004c266)
 List<String> out=new ArrayList<>();
 long r(String n){return e.readRegister(n).longValue()&0xffffffffL;}
 void stepAt(long pc)throws Exception{e.writeRegister("PC",pc);if(!e.step(monitor))throw new Exception("step failed at "+Long.toHexString(pc)+": "+e.getLastError());}
 String unit(long d0)throws Exception{
  e.writeRegister("D0",d0&0xffffffffL);e.writeRegister("CF",0);e.writeRegister("ZF",0);e.writeRegister("NF",0);e.writeRegister("VF",0);
  stepAt(ADD);
  return String.format("add D0,D0 D0in=%08x -> D0=%08x CF=%d VF=%d ZF=%d NF=%d",d0&0xffffffffL,r("D0"),r("CF"),r("VF"),r("ZF"),r("NF"));
 }
 int normalizeLoop(long d1,long d0,int bound)throws Exception{
  e.writeRegister("D1",d1&0xffffffffL);e.writeRegister("D0",d0&0xffffffffL);e.writeRegister("CF",0);
  for(int i=0;i<bound;i++){if((r("D1")&0x100000L)!=0)return i;stepAt(ADD);stepAt(ROL);}
  return -1;
 }
 public void run()throws Exception{
  Path o=Paths.get(getScriptArgs()[0]);
  if(!currentProgram.getMemory().contains(toAddr(ADD))){println("SKIP (not the main app): "+currentProgram.getName());return;}
  e=new EmulatorHelper(currentProgram);
  try{
   out.add("program="+currentProgram.getName()+" languageID="+currentProgram.getLanguageID());
   out.add("instr@"+Long.toHexString(ADD)+"="+getInstructionAt(toAddr(ADD)));
   out.add("instr@"+Long.toHexString(ROL)+"="+getInstructionAt(toAddr(ROL)));
   out.add(unit(0x80000000L)); // discriminator: CF and VF
   out.add(unit(0x40000000L)); // discriminator: VF
   out.add(unit(0xffffffffL)); // sanity: agrees before/after (CF=1 VF=0)
   out.add(unit(0x00000001L)); // sanity: agrees before/after (CF=0 VF=0)
   int r1=normalizeLoop(0,0x80000000L,64);
   out.add("normalize-loop seed D1=0 D0=80000000 bound=64 -> "+(r1<0?"DID NOT TERMINATE (bug: top bit lost)":("terminated at iteration "+r1)));
  }finally{e.dispose();}
  Files.createDirectories(o);Files.write(o.resolve("carry-test-result.txt"),out);for(String s:out)println(s);
 }
}
