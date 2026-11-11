// Temporary in-memory repair of one proven false CALL_RETURN override.
// Run with -readOnly; do not save the original project.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import java.nio.file.*;
import java.io.*;
public class OM3HumanRepairView extends GhidraScript {
 public void run() throws Exception {
  Path dir=Paths.get(getScriptArgs()[0]);
  Instruction site=getInstructionAt(toAddr(0x6086b627L));
  String old=site.getFlowOverride().toString();site.setFlowOverride(FlowOverride.NONE);
  Function getter=getFunctionAt(toAddr(0x60063380L));
  if(getter!=null)getter.setNoReturn(false);
  AddressSet window=new AddressSet(toAddr(0x6086b5b9L),toAddr(0x6086b8bcL));
  DisassembleCommand cmd=new DisassembleCommand(toAddr(0x6086b62eL),window,true);
  cmd.enableCodeAnalysis(false);cmd.applyTo(currentProgram,monitor);
  Function fn=getFunctionAt(toAddr(0x6086b5b9L));fn.setBody(window);
  DecompInterface dec=new DecompInterface();dec.openProgram(currentProgram);
  try {
   DecompileResults res=dec.decompileFunction(fn,30,monitor);
   if(res.decompileCompleted())Files.writeString(dir.resolve("result-read-repaired.c"),"/* Temporary analysis-only repair; camera ABI remains provisional. */\n"+res.getDecompiledFunction().getC());
   Files.writeString(dir.resolve("result-read-repair.txt"),"Original override at 6086b627: "+old+"\nCleared in memory only. Getter 60063380 contains return paths.\nBounded body extended through ret at 6086b8ba.\nDecompiler completed: "+res.decompileCompleted()+"\nError: "+res.getErrorMessage()+"\nNo project changes saved.\n");
  }finally{dec.dispose();}
 }
}
