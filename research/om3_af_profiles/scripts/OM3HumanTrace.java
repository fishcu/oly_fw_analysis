// Read-only reference inventory for the OM-3 human-detection investigation.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.nio.file.*;
import java.io.*;

public class OM3HumanTrace extends GhidraScript {
 public void run() throws Exception {
  Path dir=Paths.get(getScriptArgs()[0]);
  try(PrintWriter out=new PrintWriter(dir.resolve("ghidra-string-xrefs.tsv").toFile())) {
   out.println("string_address\tfrom_address\tref_type\tfunction\tfunction_name\tstring");
   for(String line:Files.readAllLines(dir.resolve("xref-input.tsv"))) {
    int sep=line.indexOf('\t');
    Address a=toAddr(line.substring(0,sep));
    ReferenceIterator refs=currentProgram.getReferenceManager().getReferencesTo(a);
    while(refs.hasNext()) {
     Reference ref=refs.next(); Function f=getFunctionContaining(ref.getFromAddress());
     out.println(a+"\t"+ref.getFromAddress()+"\t"+ref.getReferenceType()+"\t"+(f==null?"":f.getEntryPoint())+"\t"+(f==null?"":f.getName())+"\t"+line.substring(sep+1));
    }
   }
  }
  println("Human-detection xrefs exported without program changes.");
 }
}
