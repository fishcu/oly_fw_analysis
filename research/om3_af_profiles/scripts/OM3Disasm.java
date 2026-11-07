// Read-only linear disassembly of an address range: args <start-hex> <count> <out-file>.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;
public class OM3Disasm extends GhidraScript {
 @Override public void run()throws Exception {
  String[] a=getScriptArgs();long pc=Long.parseLong(a[0],16);int n=Integer.parseInt(a[1]);
  PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  List<String> out=new ArrayList<>();
  for(int i=0;i<n;i++){
   byte[] b=getBytes(toAddr(pc),16);PseudoInstruction ins=dis.disassemble(toAddr(pc),b);
   if(ins==null){out.add(String.format("%08x\t??",pc));pc++;continue;}
   StringBuilder h=new StringBuilder();for(int k=0;k<ins.getLength();k++)h.append(String.format("%02x",b[k]&0xff));
   out.add(String.format("%08x\t%s\t%s",pc,h,ins));pc+=ins.getLength();
  }
  Files.write(Paths.get(a[2]),out);
 }
}
