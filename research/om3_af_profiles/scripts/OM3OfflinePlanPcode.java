// Read-only p-code inspection of instructions implicated by the reset probe.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import ghidra.program.model.pcode.PcodeOp;
import java.nio.file.*;
import java.util.*;
public class OM3OfflinePlanPcode extends GhidraScript {
 public void run() throws Exception {
  List<String> out=new ArrayList<>();
  PseudoDisassembler d=new PseudoDisassembler(currentProgram);
  out.add("Language: "+currentProgram.getLanguageID());
  for(long pc:new long[]{0x6004c268L,0x6004c278L,0x6004c27bL,0x6004c27eL,0x6004c286L,0x6004c28cL,0x6004c28dL,0x601e8224L}){
   PseudoInstruction i=d.disassemble(toAddr(pc));out.add(String.format("%08x %s",pc,i));
   for(PcodeOp op:i.getPcode())out.add("  "+op);
  }
  Files.write(Paths.get(getScriptArgs()[0]),out);
 }
}
