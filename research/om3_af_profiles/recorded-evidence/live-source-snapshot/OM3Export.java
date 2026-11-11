// Export all functions identified by Ghidra, with decompiler uncertainty recorded.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

public class OM3Export extends GhidraScript {
    String clean(String s){return s==null?"":s.replace('\t',' ').replace('\n',' ').replace('\r',' ');}
    public void run() throws Exception {
        Path out=Paths.get(getScriptArgs()[0]);
        if(getScriptArgs().length>1 && getScriptArgs()[1].equals("batch"))out=out.resolve(currentProgram.getName().replaceAll("[^a-zA-Z0-9_.-]","_"));
        Files.createDirectories(out.resolve("functions"));
        if(currentProgram.getLanguageID().toString().startsWith("mn10300")){
            long[] addresses={0x60021020L,0x60405804L,0x60518381L,0x60518573L,0x604a3e73L,
                0x603f34ecL,0x604037f9L,0x6040391aL,0x60403a3bL,0x60403b5cL,0x60045e6cL,0x60045ed5L,0x601e75baL};
            String[] labels={"om3_application_entry","om3_defaults_accessor","om3_color_builder","om3_color_selector",
                "om3_color_register_writer","om3_settings_getter","om3_color1_settings","om3_color2_settings",
                "om3_color3_settings","om3_color4_settings","om3_section_end_selector","om3_section_loader","om3_external_flash_parser"};
            for(int i=0;i<addresses.length;i++){
                Function f=getFunctionAt(toAddr(addresses[i]));
                if(f!=null)f.setName(labels[i],SourceType.USER_DEFINED);
            }
        }
        DecompInterface decomp=new DecompInterface();
        if(!decomp.openProgram(currentProgram))throw new IOException("Cannot initialize decompiler");
        long total=0,ok=0,failed=0,warned=0,bodyBytes=0;
        try(PrintWriter index=new PrintWriter(Files.newBufferedWriter(out.resolve("functions.tsv"),StandardCharsets.UTF_8));
            PrintWriter all=new PrintWriter(Files.newBufferedWriter(out.resolve("all-functions.c"),StandardCharsets.UTF_8));
            PrintWriter asm=new PrintWriter(Files.newBufferedWriter(out.resolve("all-functions.asm"),StandardCharsets.UTF_8));
            PrintWriter calls=new PrintWriter(Files.newBufferedWriter(out.resolve("calls.tsv"),StandardCharsets.UTF_8))) {
            index.println("address\tname\tbody_bytes\tdecompiled\twarning_markers\tfile\tdiagnostic");
            calls.println("caller_entry\tcall_address\ttarget");
            all.println("/* OM-3 1.1 component: "+currentProgram.getName()+". Ghidra-generated pseudocode, not original or buildable source.\n"+
                " * Unverified function boundaries; camera-specific ABI and specialized opcode semantics may be incomplete.\n"+
                " * Full per-function status is in functions.tsv. */");
            FunctionIterator funcs=currentProgram.getFunctionManager().getFunctions(true);
            while(funcs.hasNext()&&!monitor.isCancelled()){
                Function f=funcs.next();
                if(f.isExternal())continue;
                total++;bodyBytes+=f.getBody().getNumAddresses();
                String address=f.getEntryPoint().toString();
                String filename="functions/"+address+".c";
                String text="",error=""; boolean success=false;int warnings=0;
                try{
                    DecompileResults result=decomp.decompileFunction(f,10,monitor);
                    success=result.decompileCompleted()&&result.getDecompiledFunction()!=null;
                    error=clean(result.getErrorMessage());
                    if(success){
                        text=result.getDecompiledFunction().getC();
                        warnings=text.split("WARNING",-1).length-1;
                        if(warnings>0||!error.isEmpty())warned++;
                    }
                }catch(Exception e){error=clean(e.toString());}
                if(success)ok++;else failed++;
                String header="/* Address "+address+"; "+clean(f.getName())+"; body bytes "+f.getBody().getNumAddresses()+
                    "; decompile completed="+success+" */\n";
                String exported=header+(success?text:"/* Decompiler failed: "+error.replace("*/","* /")+" */\n");
                Files.writeString(out.resolve(filename),exported,StandardCharsets.UTF_8);
                all.println(exported);
                index.println(address+"\t"+clean(f.getName())+"\t"+f.getBody().getNumAddresses()+"\t"+success+"\t"+warnings+"\t"+filename+"\t"+error);
                asm.println("\n; Function "+address+" "+f.getName());
                InstructionIterator instructions=currentProgram.getListing().getInstructions(f.getBody(),true);
                while(instructions.hasNext()){
                    Instruction ins=instructions.next();
                    StringBuilder hex=new StringBuilder();
                    for(byte b:ins.getBytes()){
                        hex.append(Character.forDigit((b>>>4)&15,16));
                        hex.append(Character.forDigit(b&15,16));
                    }
                    asm.println(ins.getAddress()+"\t"+hex+"\t"+ins);
                    if(ins.getFlowType().isCall())for(var target:ins.getFlows())
                        calls.println(address+"\t"+ins.getAddress()+"\t"+target);
                }
                if(total%100==0){index.flush();all.flush();asm.flush();calls.flush();println("Exported "+total+" functions; completed="+ok+", failed="+failed);}
            }
        }finally{decomp.dispose();}
        long instructionCount=0,instructionBytes=0;
        InstructionIterator ins=currentProgram.getListing().getInstructions(true);
        while(ins.hasNext()){Instruction i=ins.next();instructionCount++;instructionBytes+=i.getLength();}
        try(PrintWriter bookmarks=new PrintWriter(Files.newBufferedWriter(out.resolve("bookmarks.tsv"),StandardCharsets.UTF_8))){
            bookmarks.println("address\ttype\tcategory\tcomment");
            var it=currentProgram.getBookmarkManager().getBookmarksIterator();
            while(it.hasNext()){var b=it.next();bookmarks.println(b.getAddress()+"\t"+clean(b.getTypeString())+"\t"+clean(b.getCategory())+"\t"+clean(b.getComment()));}
        }
        String summary="{\n  \"language\": \""+currentProgram.getLanguageID()+"\",\n"+
            "  \"functions\": "+total+",\n  \"decompiled\": "+ok+",\n  \"failed\": "+failed+",\n"+
            "  \"functions_with_warnings_or_diagnostics\": "+warned+",\n  \"function_body_bytes_sum\": "+bodyBytes+",\n"+
            "  \"instruction_count\": "+instructionCount+",\n  \"instruction_bytes\": "+instructionBytes+",\n"+
            "  \"cancelled\": "+monitor.isCancelled()+",\n  \"program\": \""+clean(currentProgram.getName())+"\",\n  \"scope\": \"Heuristically recovered functions in this program; camera-specific ABI and special opcode semantics may be incomplete\"\n}\n";
        Files.writeString(out.resolve("summary.json"),summary);
        println(summary);
    }
}
