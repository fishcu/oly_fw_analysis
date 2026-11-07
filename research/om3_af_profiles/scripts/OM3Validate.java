// Bounded, offline MN10300 validation against pinned OM-3 landmarks.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.SourceType;
import java.io.*;
import java.nio.file.*;

public class OM3Validate extends GhidraScript {
    public void run() throws Exception {
        Path output = Paths.get(getScriptArgs()[0]);
        Files.createDirectories(output);
        String[] names = {"defaults_accessor", "color_builder", "color_selector"};
        long[] starts = {0x60405804L, 0x60518381L, 0x60518573L};
        long[] stops = {0x6040580dL, 0x60518560L, 0x6051869eL};
        DecompInterface decompiler = new DecompInterface();
        if (!decompiler.openProgram(currentProgram)) throw new Exception("Decompiler initialization failed");
        try (PrintWriter report = new PrintWriter(output.resolve("validation.txt").toFile())) {
            report.println("Language: " + currentProgram.getLanguageID());
            report.println("Scope: bounded disassembly and provisional decompilation; no hardware execution");
            report.println("Default compiler ABI is unverified for camera code.");
            for (int n=0; n<names.length; n++) {
                Address first = toAddr(starts[n]), last = toAddr(stops[n]-1);
                AddressSet body = new AddressSet(first,last);
                DisassembleCommand cmd = new DisassembleCommand(first,body,true);
                cmd.enableCodeAnalysis(false);
                if (!cmd.applyTo(currentProgram,monitor)) throw new Exception("Disassembly failed: "+names[n]);
                long covered=0;
                try (PrintWriter asm = new PrintWriter(output.resolve(names[n]+".asm").toFile())) {
                    InstructionIterator instructions = currentProgram.getListing().getInstructions(body,true);
                    while (instructions.hasNext()) {
                        Instruction ins = instructions.next();
                        covered += ins.getLength();
                        StringBuilder bytes = new StringBuilder();
                        for (byte b: ins.getBytes()) bytes.append(String.format("%02x ",b & 255));
                        asm.println(ins.getAddress()+"  "+bytes+" "+ins);
                    }
                }
                report.println(names[n]+": "+covered+" decoded bytes / "+(stops[n]-starts[n])+" window bytes");
                if (n==0) {
                    Instruction mov = getInstructionAt(first);
                    Instruction ret = getInstructionAt(first.add(6));
                    if (mov==null || mov.getLength()!=6 || !mov.getMnemonicString().equalsIgnoreCase("mov") ||
                        ret==null || !ret.getMnemonicString().equalsIgnoreCase("retf"))
                        throw new Exception("Known accessor decode mismatch");
                    report.println("Accessor instruction boundary check: PASS; inspect operand in defaults_accessor.asm");
                    if (mov.getScalar(0)==null || mov.getScalar(0).getUnsignedValue()!=0x605f6d90L)
                        throw new Exception("Accessor operand mismatch");
                }
                if (n==2) {
                    Instruction tableLoad = getInstructionAt(toAddr(0x6051860aL));
                    Instruction builderCall = getInstructionAt(toAddr(0x60518615L));
                    if (tableLoad==null || tableLoad.getScalar(0)==null ||
                        tableLoad.getScalar(0).getUnsignedValue()!=0x606ba608L ||
                        builderCall==null || builderCall.getFlows().length!=1 ||
                        builderCall.getFlows()[0].getOffset()!=0x60518381L)
                        throw new Exception("Known table-load / builder-call landmark mismatch");
                    report.println("COLOR table operand and builder call target: PASS");
                }
                Function fn = getFunctionAt(first);
                if (fn==null) fn = currentProgram.getFunctionManager().createFunction("om3_"+names[n],first,body,SourceType.USER_DEFINED);
                DecompileResults result = decompiler.decompileFunction(fn,30,monitor);
                report.println(names[n]+" decompile completed: "+result.decompileCompleted());
                if (result.decompileCompleted()) Files.writeString(output.resolve(names[n]+".c"),
                    "/* Provisional output; camera ABI and specialized instruction semantics unverified. */\n"+
                    result.getDecompiledFunction().getC());
                else report.println(result.getErrorMessage());
            }
        } finally {decompiler.dispose();}
        println("OM3 bounded validation finished: "+output);
    }
}
