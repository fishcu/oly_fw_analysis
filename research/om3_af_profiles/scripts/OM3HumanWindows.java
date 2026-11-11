// Linear decoding of bounded research windows; does not change the saved program.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import java.nio.file.*;
import java.io.*;
public class OM3HumanWindows extends GhidraScript {
 public void run() throws Exception {
  Path dir=Paths.get(getScriptArgs()[0]);
  PseudoDisassembler dis=new PseudoDisassembler(currentProgram);
  for(String line:Files.readAllLines(dir.resolve("windows.tsv"))) {
   String[] f=line.split("\t");Address a=toAddr(f[0]),end=toAddr(f[1]);
   try(PrintWriter out=new PrintWriter(dir.resolve(f[2]+".asm").toFile())) {
    out.println("; Bounded linear decode, not proof all bytes are reachable code.");
    while(a.compareTo(end)<0) {
     try {
      PseudoInstruction ins=dis.disassemble(a);
      if(ins==null)throw new Exception("No instruction");
      StringBuilder bytes=new StringBuilder();for(byte b:ins.getBytes())bytes.append(String.format("%02x",b&255));
      Instruction saved=getInstructionAt(a);
      out.println(a+"\t"+bytes+"\t"+ins+(saved!=null?"\t[saved-flow="+saved.getFlowType()+"; override="+saved.getFlowOverride()+"]":""));
      a=a.add(ins.getLength());
     } catch(Exception e) {out.println(a+"\tDECODE_FAILURE\t"+e);a=a.add(1);}
    }
   }
  }
 }
}
