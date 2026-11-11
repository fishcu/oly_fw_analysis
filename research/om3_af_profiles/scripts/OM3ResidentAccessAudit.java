// Read-only alignment / access audit of the resident feature as placed by OM3ResidentProof.prepareResident.
// Disassembles every placed block at its final address (packed code in the section-4 tail, mode block, wrappers) and
// the patched stock sites, from emulator memory after preparation. No image is written; the emulator copy is discarded.
// Checks per instruction: decodes (no udf); memory accesses by width (mov=32, movhu=16, movbu/bset/bclr/btst=8);
// absolute addresses aligned and classified (state via uncached alias, no cached-alias state access, no writes into
// code areas); register-relative accesses aligned when the base register holds a constant loaded earlier in the same
// straight-line run (best effort; reset at branches/labels); call/jump targets are stock function starts or placed code.
// Output: resident-access-audit.txt (all findings) and resident-access-summary.txt.
// @category OM3
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
public class OM3ResidentAccessAudit extends OM3ResidentProof {
 final List<String> rep=new ArrayList<>();final Map<String,Integer> count=new TreeMap<>();
 void f(String k,String s){count.merge(k,1,Integer::sum);rep.add(k+" "+s);}
 Set<Long> fnStarts=new HashSet<>();
 boolean inPlaced(long a){for(long[] b:blocks)if(a>=b[1]&&a<b[1]+b[2])return true;return a>=0x6031eb80L&&a<0x6031f000L||a>=0x607187a4L&&a<0x60718800L;}
 String region(long a){
  if(a>=0x6031e920L&&a<0x6031eb80L)return "STATE-CACHED";
  if(a>=0xa031e920L&&a<0xa031eb80L)return "STATE-UNCACHED";
  if(a>=0x6031eb80L&&a<0x6031f000L||a>=0x60a8f088L&&a<0x60a8f800L||a>=0x607187a4L&&a<0x60718800L)return "CODE-AREA";
  if(a>=0xa031eb80L&&a<0xa031f000L||a>=0xa0a8f088L&&a<0xa0a8f800L||a>=0xa07187a4L&&a<0xa0718800L)return "CODE-AREA-UNCACHED";
  if(a>=0x90000000L&&a<0xa0000000L)return "MMIO";
  if(a>=0xa0000000L&&a<0xb0000000L)return "STOCK-UNCACHED";
  if(a>=0x60000000L&&a<0x64000000L)return "STOCK-CACHED";
  return "OTHER";
 }
 void audit(String name,long start,int len)throws Exception{
  PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  Map<String,Long> konst=new HashMap<>();
  Pattern abs=Pattern.compile("\\(0x([0-9a-f]+)\\)"),rel=Pattern.compile("\\((?:(-?0x[0-9a-f]+|-?\\d+),)?(a[0-3]|sp)\\)");
  Pattern movImm=Pattern.compile("^mov 0x([0-9a-f]+),(a[0-3])$");Pattern tgt=Pattern.compile("^(call|calls|jmp|bra|b[a-z]+|l[a-z]+) 0x([0-9a-f]+)");
  rep.add(String.format("== %s %08x len=%d",name,start,len));
  for(long pc=start;pc<start+len;){
   byte[] b=e.readMemory(toAddr(pc),16);PseudoInstruction ins=dis.disassemble(toAddr(pc),b);
   if(ins==null){f("DECODE-FAIL",String.format("%08x",pc));pc++;konst.clear();continue;}
   String t=ins.toString().toLowerCase().replaceAll("\\s+"," ").trim();int n=ins.getLength();
   StringBuilder hx=new StringBuilder();for(int k=0;k<n;k++)hx.append(String.format("%02x",b[k]&255));
   rep.add(String.format("   %08x %-14s %s",pc,hx,t));
   if(pc+n>start+len)f("SPANS-BLOCK-END",String.format("%08x %s",pc,t));
   if(t.startsWith("udf"))f("UNDEFINED-OPCODE",String.format("%08x %s",pc,t));
   String mn=t.split(" ")[0];
   int width=mn.equals("mov")?4:mn.equals("movhu")||mn.equals("movh")?2:mn.matches("movbu|movb|bset|bclr|btst")?1:0;
   boolean store=t.matches("^mov[a-z]* [^,]+,\\(.*\\)$")||mn.matches("bset|bclr");
   Matcher m=abs.matcher(t);
   if(width>0&&m.find()){long a=Long.parseLong(m.group(1),16);String r=region(a);
    if(a%width!=0)f("MISALIGNED-ABS",String.format("%08x %s addr=%08x width=%d",pc,t,a,width));
    if(r.equals("STATE-CACHED"))f("STATE-VIA-CACHED-ALIAS",String.format("%08x %s",pc,t));
    if(r.startsWith("CODE-AREA")&&store)f("WRITE-INTO-CODE-AREA",String.format("%08x %s",pc,t));
    f("ACCESS-"+r+(store?"-W":"-R"),String.format("%08x %s",pc,t));}
   Matcher r2=rel.matcher(t);
   if(width>0&&r2.find()&&!m.find(0)){
    String reg=r2.group(2);long disp=r2.group(1)==null?0:Long.decode(r2.group(1).replace("-0x","-0x"));
    Long base=konst.get(reg);
    if(base!=null){long a=(base+disp)&0xffffffffL;String rg=region(a);
     if(a%width!=0)f("MISALIGNED-REL",String.format("%08x %s base=%08x addr=%08x width=%d",pc,t,base,a,width));
     if(rg.equals("STATE-CACHED"))f("STATE-VIA-CACHED-ALIAS",String.format("%08x %s addr=%08x",pc,t,a));
     if(rg.startsWith("CODE-AREA")&&store)f("WRITE-INTO-CODE-AREA",String.format("%08x %s addr=%08x",pc,t,a));
     f("REL-KNOWN-"+rg+(store?"-W":"-R"),String.format("%08x %s addr=%08x",pc,t,a));}
    else{if(!reg.equals("sp")&&disp%width!=0)f("REL-DISP-NOT-WIDTH-MULTIPLE",String.format("%08x %s",pc,t));f(reg.equals("sp")?"STACK-ACCESS":"REL-UNKNOWN-BASE",String.format("%08x %s",pc,t));}
   }
   Matcher mi=movImm.matcher(t);
   if(mi.find())konst.put(mi.group(2),Long.parseLong(mi.group(1),16));
   else{String[] ops=t.contains(" ")?t.substring(t.indexOf(' ')+1).split(","):new String[0];if(ops.length>0){String dst=ops[ops.length-1].trim();if(konst.containsKey(dst))konst.remove(dst);}}
   Matcher tm=tgt.matcher(t);
   if(tm.find()){long a=Long.parseLong(tm.group(2),16);String kind=tm.group(1);
    if(kind.equals("call")||kind.equals("jmp")){
     if(inPlaced(a))f("TARGET-PLACED",String.format("%08x %s",pc,t));
     else if(fnStarts.contains(a))f("TARGET-STOCK-FUNCTION",String.format("%08x %s",pc,t));
     else f("TARGET-NOT-FUNCTION-START",String.format("%08x %s",pc,t));}
    konst.clear();}
   if(mn.matches("ret|retf|rets|rti|jmp|bra|calls"))konst.clear();
   pc+=n;
  }
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);
  for(String l:Files.readAllLines(Paths.get("analysis/decompiled-main/all-functions.asm"),java.nio.charset.StandardCharsets.ISO_8859_1))
   if(l.startsWith("; Function "))fnStarts.add(Long.parseLong(l.split(" ")[2],16));
  int tx=currentProgram.startTransaction("Temporary audit mapping");
  try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_audit",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}
  finally{currentProgram.endTransaction(tx,true);}
  String result;
  try{
   profileInit(6,out);prepareResident(out);
   for(long[] b:blocks)audit(String.format("block %08x<-%08x",b[1],b[0]),b[1],(int)b[2]);
   audit("patched stock accessor",0x609b3bb2L,9);
   audit("patched stock entry",0x603cedfeL,5);
   for(long r:new long[]{0x6131bd50L,0x6131bd60L,0x6131c290L,0x6131c2a0L})rep.add(String.format("TABLE-REDIRECT record %08x handler-field %08x -> %08x (section 7, compressed)",r,r+12,u32(r+12)));
   result="AUDITED blocks="+blocks.size();
  }catch(Exception ex){result="BOUNDARY "+ex;}
  List<String> sum=new ArrayList<>();sum.add(result);for(var en:count.entrySet())sum.add(String.format("%-34s %d",en.getKey(),en.getValue()));
  Files.write(out.resolve("resident-access-audit.txt"),rep);Files.write(out.resolve("resident-access-summary.txt"),sum);println(String.join("\n",sum));
 }
}
