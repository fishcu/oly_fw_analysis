// Retry only the native-decompiler interruptions, using the original 10-second budget.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;
public class OM3RetryInterrupted extends GhidraScript {
    String clean(String s){return s==null?"":s.replace('\t',' ').replace('\n',' ').replace('\r',' ');}
    public void run() throws Exception {
        Path out=Paths.get(getScriptArgs()[0]);
        List<String> lines=Files.readAllLines(out.resolve("functions.tsv"));
        Map<String,String> replacements=new LinkedHashMap<>();
        int retried=0;
        try(PrintWriter history=new PrintWriter(Files.newBufferedWriter(out.resolve("interrupted-retries.tsv")))){
            history.println("address\tprevious_diagnostic\tcompleted\tdiagnostic");
            for(int i=1;i<lines.size();i++){
                String[] row=lines.get(i).split("\t",-1);
                if(!row[3].equals("false") || !row[6].contains("Decompiler process died"))continue;
                var fn=getFunctionAt(toAddr(Long.parseUnsignedLong(row[0],16)));
                if(fn==null)throw new IOException("Missing indexed function "+row[0]);
                DecompInterface decomp=new DecompInterface();
                try{
                    if(!decomp.openProgram(currentProgram))throw new IOException("Cannot open program");
                    var result=decomp.decompileFunction(fn,10,monitor);
                    boolean completed=result.decompileCompleted()&&result.getDecompiledFunction()!=null;
                    String diagnostic=clean(result.getErrorMessage());
                    history.println(row[0]+"\t"+row[6]+"\t"+completed+"\t"+diagnostic);
                    String code=completed?result.getDecompiledFunction().getC():"/* Decompiler failed: "+diagnostic.replace("*/","* /")+" */\n";
                    String replacement="/* Address "+row[0]+"; "+row[1]+"; body bytes "+row[2]+"; decompile completed="+completed+" */\n"+code;
                    Files.writeString(out.resolve(row[5]),replacement);
                    replacements.put(row[0],replacement);
                    row[3]=Boolean.toString(completed);
                    row[4]=Integer.toString(completed?code.split("WARNING",-1).length-1:0);
                    row[6]=diagnostic;
                    lines.set(i,String.join("\t",row));retried++;
                    history.flush();
                    println("Retried "+row[0]+"; completed="+completed+"; "+diagnostic);
                }finally{decomp.dispose();}
            }
        }
        Files.write(out.resolve("functions.tsv"),lines);
        int ok=0,failed=0,warned=0;
        for(int i=1;i<lines.size();i++){
            String[] row=lines.get(i).split("\t",-1);
            if(row[3].equals("true")){ok++;if(!row[4].equals("0")||!row[6].isEmpty())warned++;}else failed++;
        }
        String combined=Files.readString(out.resolve("all-functions.c"));
        for(var replacement:replacements.entrySet()){
            int first=combined.indexOf("/* Address "+replacement.getKey()+";");
            if(first<0)throw new IOException("Missing combined function marker");
            int end=combined.indexOf("\n/* Address ",first+1);
            if(end<0)end=combined.length();
            combined=combined.substring(0,first)+replacement.getValue()+combined.substring(end);
        }
        Files.writeString(out.resolve("all-functions.c"),combined);
        Path summaryPath=out.resolve("summary.json");
        String summary=Files.readString(summaryPath);
        summary=summary.replaceAll("\"decompiled\": \\d+","\"decompiled\": "+ok)
            .replaceAll("\"failed\": \\d+","\"failed\": "+failed)
            .replaceAll("\"functions_with_warnings_or_diagnostics\": \\d+","\"functions_with_warnings_or_diagnostics\": "+warned);
        summary=summary.replaceFirst("\\{","{\n  \"interrupted_functions_retried\": "+retried+",\n  \"retry_timeout_seconds\": 10,");
        Files.writeString(summaryPath,summary);
        println("Retried "+retried+" interrupted functions with fresh decompiler processes.");
    }
}
