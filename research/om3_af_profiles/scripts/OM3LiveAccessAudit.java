// Read-only alignment / access audit of the LIVE variant with the consolidated first-use installer
// (OM3LiveProfiles data mapping: feature state through the uncached alias 0xa031e920; OM3ConsolidatedInstallerProof layout).
// Runs the consolidated-installer chain unchanged and, immediately after redirect() has installed the hook, the
// installer and its table, disassembles every placed block from emulator memory at its final address:
//   live packed blocks (section-4 tail, wrappers at 0x6031eb80.., mode block at 0x607187a4), the installer in the freed
//   section-1 gap, the 5-byte hook at 0x6017a5fc, the patched accessor 0x609b3bb2 and entry 0x603cedfe; plus the
//   installer's {field, stock, wrapper} table in section 2.
// Differences from OM3ResidentAccessAudit (which audited the cached OM3ResidentProof variant):
//   - signed immediates (the disassembler prints 0xa031e920 as -0x5fce16e0) are resolved;
//   - register constants propagate through register-to-register moves;
//   - a callee-saved register (d2,d3,a2,a3) written exactly once in a block, by an immediate move, stays known for the
//     rest of that block (it survives branches and calls under the MN10300 ABI); every other constant is dropped at
//     branches, calls and returns as before;
//   - state classification is the owned range only (DATA..DATA+0x1b0); the freed gap and the table are classified
//     separately.
// The emulator copy is discarded; no image is written. The run then continues to the 28-edge matrix as usual.
// Output (in the run directory): live-access-audit.txt (all findings) and live-access-summary.txt.
// @category OM3
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
public class OM3LiveAccessAudit extends OM3ConsolidatedInstallerProof {
 final List<String> rep=new ArrayList<>();final Map<String,Integer> count=new TreeMap<>();
 void f(String k,String s){count.merge(k,1,Integer::sum);rep.add(k+" "+s);}
 final Set<Long> fnStarts=new HashSet<>();String auditResult="NOT-RUN";boolean audited=false;
 static final long STATE_END=0x6031ead0L,SEC7_LO=0x6103f000L,SEC7_HI=0x6164b000L;
 static final long[] TABLE_FIELDS={0x6131bd5cL,0x6131bd6cL,0x6131c29cL,0x6131c2acL};
 boolean inPlaced(long a){for(long[] b:blocks)if(a>=b[1]&&a<b[1]+b[2])return true;return a>=GAP&&a<GAP+installerSize;}
 String region(long a){
  if(a>=DATA&&a<STATE_END)return "STATE-CACHED";
  if(a>=DATA+0x40000000L&&a<STATE_END+0x40000000L)return "STATE-UNCACHED";
  if(a>=TABLE2&&a<TABLE2+48)return "INSTALLER-TABLE";
  if(a>=TABLE2+0x40000000L&&a<TABLE2+48+0x40000000L)return "INSTALLER-TABLE-UNCACHED";
  if(a==LOADED)return "LOADED-BITS-UNCACHED";
  for(long t:TABLE_FIELDS)if(a==t)return "SECTION7-HANDLER-FIELD";
  if(inPlaced(a)||a>=GAP&&a<GAP_END)return "CODE-AREA";
  if(inPlaced(a-0x40000000L)||a>=GAP+0x40000000L&&a<GAP_END+0x40000000L)return "CODE-AREA-UNCACHED";
  if(a>=0x90000000L&&a<0xa0000000L)return "MMIO";
  if(a>=0xa0000000L&&a<0xb0000000L)return "STOCK-UNCACHED";
  if(a>=0x60000000L&&a<0x64000000L)return "STOCK-CACHED";
  return "OTHER";
 }
 static long imm(String s){return Long.decode(s)&0xffffffffL;}
 static final Set<String> CALLEE=Set.of("d2","d3","a2","a3");
 static String dest(String t){if(!t.contains(" "))return "";String[] ops=t.substring(t.indexOf(' ')+1).split(",");return ops[ops.length-1].trim();}
 void audit(String name,long start,int len)throws Exception{
  PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  Pattern abs=Pattern.compile("\\((-?0x[0-9a-f]+)\\)"),rel=Pattern.compile("\\((?:(-?0x[0-9a-f]+|-?\\d+),)?(a[0-3]|sp)\\)");
  Pattern movImm=Pattern.compile("^mov (-?0x[0-9a-f]+|-?\\d+),([ad][0-3])$"),movReg=Pattern.compile("^mov ([ad][0-3]),([ad][0-3])$");
  Pattern tgt=Pattern.compile("^(call|calls|jmp|bra|b[a-z]+|l[a-z]+) (0x[0-9a-f]+)");
  // pass 1: decode, find pinned callee-saved registers (exactly one write, an immediate move)
  List<long[]> pcs=new ArrayList<>();List<String> txt=new ArrayList<>();Map<String,Integer> writes=new HashMap<>();Map<String,Long> pinVal=new HashMap<>();Map<String,Long> pinAt=new HashMap<>();
  for(long pc=start;pc<start+len;){
   byte[] b=e.readMemory(toAddr(pc),16);PseudoInstruction ins=dis.disassemble(toAddr(pc),b);
   if(ins==null){pcs.add(new long[]{pc,1});txt.add(null);pc++;continue;}
   String t=ins.toString().toLowerCase().replaceAll("\\s+"," ").trim();int n=ins.getLength();pcs.add(new long[]{pc,n});txt.add(t);
   String d=dest(t);if(CALLEE.contains(d)){writes.merge(d,1,Integer::sum);Matcher mi=movImm.matcher(t);if(mi.find()){pinVal.put(d,imm(mi.group(1)));pinAt.put(d,pc);}}
   pc+=n;
  }
  Set<String> pinned=new HashSet<>();for(String r:pinVal.keySet())if(writes.get(r)==1)pinned.add(r);
  rep.add(String.format("== %s %08x len=%d pinned=%s",name,start,len,pinned.isEmpty()?"-":pinned.stream().sorted().map(r->String.format("%s=%08x@%08x",r,pinVal.get(r),pinAt.get(r))).reduce((x,y)->x+" "+y).get()));
  Map<String,Long> konst=new HashMap<>();
  for(int i=0;i<pcs.size();i++){
   long pc=pcs.get(i)[0];int n=(int)pcs.get(i)[1];String t=txt.get(i);
   if(t==null){f("DECODE-FAIL",String.format("%08x",pc));keepPinned(konst,pinned);continue;}
   byte[] b=e.readMemory(toAddr(pc),n);StringBuilder hx=new StringBuilder();for(byte v:b)hx.append(String.format("%02x",v&255));
   rep.add(String.format("   %08x %-14s %s",pc,hx,t));
   if(pc+n>start+len)f("SPANS-BLOCK-END",String.format("%08x %s",pc,t));
   if(t.startsWith("udf"))f("UNDEFINED-OPCODE",String.format("%08x %s",pc,t));
   String mn=t.split(" ")[0];
   int width=mn.equals("mov")?4:mn.equals("movhu")||mn.equals("movh")?2:mn.matches("movbu|movb|bset|bclr|btst")?1:0;
   boolean store=t.matches("^mov[a-z]* [^,]+,\\(.*\\)$")||mn.matches("bset|bclr");
   Matcher m=abs.matcher(t);boolean isAbs=width>0&&m.find();
   if(isAbs){long a=imm(m.group(1));String r=region(a);
    if(a%width!=0)f("MISALIGNED-ABS",String.format("%08x %s addr=%08x width=%d",pc,t,a,width));
    if(r.equals("STATE-CACHED"))f("STATE-VIA-CACHED-ALIAS",String.format("%08x %s",pc,t));
    if(r.startsWith("CODE-AREA")&&store)f("WRITE-INTO-CODE-AREA",String.format("%08x %s",pc,t));
    f("ACCESS-"+r+(store?"-W":"-R"),String.format("%08x %s addr=%08x",pc,t,a));}
   Matcher r2=rel.matcher(t);
   if(width>0&&!isAbs&&r2.find()){
    String reg=r2.group(2);long disp=r2.group(1)==null?0:Long.decode(r2.group(1));
    Long base=konst.get(reg);
    if(base!=null){long a=(base+disp)&0xffffffffL;String rg=region(a);
     if(a%width!=0)f("MISALIGNED-REL",String.format("%08x %s base=%08x addr=%08x width=%d",pc,t,base,a,width));
     if(rg.equals("STATE-CACHED"))f("STATE-VIA-CACHED-ALIAS",String.format("%08x %s addr=%08x",pc,t,a));
     if(rg.startsWith("CODE-AREA")&&store)f("WRITE-INTO-CODE-AREA",String.format("%08x %s addr=%08x",pc,t,a));
     f("REL-KNOWN-"+rg+(store?"-W":"-R"),String.format("%08x %s addr=%08x",pc,t,a));}
    else{if(!reg.equals("sp")&&disp%width!=0)f("REL-DISP-NOT-WIDTH-MULTIPLE",String.format("%08x %s",pc,t));f(reg.equals("sp")?"STACK-ACCESS":"REL-UNKNOWN-BASE",String.format("%08x %s",pc,t));}
   }
   Matcher mi=movImm.matcher(t),mr=movReg.matcher(t);String d=dest(t);
   if(mi.find())konst.put(mi.group(2),imm(mi.group(1)));
   else if(mr.find()){Long v=konst.get(mr.group(1));if(v!=null)konst.put(mr.group(2),v);else konst.remove(mr.group(2));}
   else if(!d.isEmpty()&&!pinned.contains(d))konst.remove(d);
   Matcher tm=tgt.matcher(t);
   if(tm.find()){long a=imm(tm.group(2));String kind=tm.group(1);
    if(kind.equals("call")||kind.equals("jmp")){
     if(inPlaced(a))f("TARGET-PLACED",String.format("%08x %s",pc,t));
     else if(fnStarts.contains(a))f("TARGET-STOCK-FUNCTION",String.format("%08x %s",pc,t));
     else if(a==RESUME)f("TARGET-HOOK-RESUME",String.format("%08x %s",pc,t));
     else f("TARGET-NOT-FUNCTION-START",String.format("%08x %s",pc,t));}
    keepPinned(konst,pinned);}
   if(mn.matches("ret|retf|rets|rti|jmp|bra|calls"))keepPinned(konst,pinned);
  }
 }
 static void keepPinned(Map<String,Long> konst,Set<String> pinned){konst.keySet().retainAll(pinned);}
 void auditAll()throws Exception{
  for(long[] b:blocks)audit(String.format("live block %08x<-%08x",b[1],b[0]),b[1],(int)b[2]);
  audit("consolidated installer (freed section-1 gap)",GAP,installerSize);
  audit("hook (key-port callback prologue)",HOOK,5);
  audit("patched stock accessor",0x609b3bb2L,9);
  audit("patched stock entry",0x603cedfeL,5);
  rep.add(String.format("== installer table %08x (section 2, read-only data, 48 B)",TABLE2));
  if(TABLE2%4!=0)f("MISALIGNED-TABLE",String.format("%08x",TABLE2));
  for(int i=0;i<4;i++){long fld=u32(TABLE2+12*i),stock=u32(TABLE2+12*i+4),wrap=u32(TABLE2+12*i+8);
   rep.add(String.format("   entry %d field=%08x stock=%08x wrapper=%08x current=%08x",i,fld,stock,wrap,u32(fld)));
   if(fld%4!=0)f("MISALIGNED-TABLE-FIELD",String.format("entry %d %08x",i,fld));
   if(fld<SEC7_LO||fld>=SEC7_HI)f("TABLE-FIELD-OUTSIDE-SECTION7",String.format("entry %d %08x",i,fld));
   else f("TABLE-FIELD-SECTION7-CACHED-W",String.format("entry %d %08x (installer store mov D2,(A0))",i,fld));
   if(!inPlaced(wrap))f("TABLE-WRAPPER-NOT-PLACED",String.format("entry %d %08x",i,wrap));
   if(stock!=RECORDS[i][2])f("TABLE-STOCK-MISMATCH",String.format("entry %d %08x",i,stock));}
  auditResult="AUDITED live blocks="+blocks.size()+" + installer("+installerSize+" B) + hook + 2 patched sites + table";
 }
 @Override void redirect()throws Exception {
  super.redirect();
  if(audited)return;audited=true;   // redirect() is re-entered before every edge (fast path); audit the installed state once
  try{auditAll();}catch(Exception ex){auditResult="BOUNDARY "+ex;}
  writeAudit();
 }
 void writeAudit()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> sum=new ArrayList<>();sum.add(auditResult);
  for(var en:count.entrySet())sum.add(String.format("%-34s %d",en.getKey(),en.getValue()));
  Files.write(out.resolve("live-access-audit.txt"),rep);Files.write(out.resolve("live-access-summary.txt"),sum);println(String.join("\n",sum));
 }
 @Override public void run()throws Exception {
  for(String l:Files.readAllLines(Paths.get("analysis/decompiled-main/all-functions.asm"),java.nio.charset.StandardCharsets.ISO_8859_1))
   if(l.startsWith("; Function "))fnStarts.add(Long.parseLong(l.split(" ")[2],16));
  super.run();
 }
}
