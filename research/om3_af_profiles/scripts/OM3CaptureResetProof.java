// STOCK-RESET SCENARIO (explicitly labelled; not a normal boot). Extends OM3CaptureTimeoutProof.
// Before the event-114 connection, run the stock UI settings reset natively:
//   full scenario  : stock wrapper 0x604048c3 (-> 0x604047d9), called as UI init 0x603f0de3 calls it;
//   narrow fallback: native default reader 0x60404f35(UI 24) then native UI setter 0x60419368(UI 24, value).
// Then read setting 0xc011[0] back through native 0x60063380. No value is hardcoded. The template-only run
// (OM3CaptureTimeoutProof, capture-timeout/) is the baseline. SCPU is still modelled as silent.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CaptureResetProof extends OM3CaptureTimeoutProof {
 String resetScenario="none";int infoReports;
 // Stock reporter 0x60068a54 records a report and returns. Severity-1 (D1==1) reports are recorded and allowed
 // to return; severity >= 2 keeps the harness's stop-on-diagnostic policy. Capped at 50 as a guard.
 // Full 32x32->64 semantics for the mulq/mulqu extension (GNU sim/mn10300 mn10300.igen) when an operand is
 // outside the base harness's nonnegative scope. In-scope cases still use the shared OM3NativeQueue model.
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception{
  String m=ins.getMnemonicString();
  if(m.equals("udf00")||m.equals("udf01")||m.equals("udfu01")){
   byte[] b=ins.getBytes();int op=b[0]&255,x=b[1]&255,n=x&3;boolean signed=m.equals("udf00");long a;
   if(op==0xf6)a=reg("D"+((x>>2)&3));
   else if(op==0xf9||op==0xfb||op==0xfd){a=0;for(int j=2;j<b.length;j++)a|=(b[j]&255L)<<((j-2)*8);if(signed){if(b.length==3)a=(byte)a;else if(b.length==4)a=(short)a;else a=(int)a;}}
   else return super.instruction(ins);
   long v=reg("D"+n);
   boolean inScope=(signed?((int)v)>=0:true)&&a>=0&&a<=0x7fffffffL&&(signed?(int)v:v)>=0&&(signed?(long)(int)v:v)<=0x7fffffffL;
   if(!inScope){
    long low,high;
    if(signed){long sa=(int)a,sv=(int)v;long p=sa*sv;low=p&0xffffffffL;high=(p>>32)&0xffffffffL;}
    else{long ua=a&0xffffffffL,uv=v&0xffffffffL;java.math.BigInteger p=java.math.BigInteger.valueOf(ua).multiply(java.math.BigInteger.valueOf(uv));low=p.longValue()&0xffffffffL;high=p.shiftRight(32).longValue()&0xffffffffL;}
    mulHigh=high;e.writeRegister("D"+n,low);e.writeRegister("ZF",low==0?1:0);e.writeRegister("NF",(low>>>31)&1);e.writeRegister("CF",0);e.writeRegister("VF",0);
    trace.add(String.format("GNU-multiply-full:%s:%s:%x*%x=low %x high %x",ins.getAddress(),signed?"signed":"unsigned",a,v,low,high));
    e.writeRegister("PC",ins.getAddress().getOffset()+ins.getLength());return true;}
  }
  return super.instruction(ins);
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x60031027L){
   // del_flg-shaped service (same +0x3c+0xa limit as wait 60038ea5; releases waiters with -51). No waiters exist
   // in this single-context model, so only existence is checked.
   long id=reg("D0")&0xffff;check(eventFlags.containsKey(id),"Delete of unknown event flag "+id);
   eventFlags.remove(id);e.writeRegister("D0",0);trace.add("MODEL:event-flag-delete:"+id);return true;}
  if(t==0x60068a54L&&reg("D1")==1){infoReports++;check(infoReports<=50,"More than 50 severity-1 diagnostic reports");
   trace.add(String.format("AF-DIAGNOSTIC-SEVERITY1:code=%08x line=%x pc=%08x (recorded, returned)",reg("D0"),u32(reg("SP")+8),e.getExecutionAddress().getOffset()));return true;}
  return super.external(t);
 }
 long nested(long entry,int mask,int frame,long d0,long d1)throws Exception {
  Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(ghidra.program.model.lang.Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
  long oldTop=stackTop;stackTop=0x70068000L;
  try{e.writeRegister("D0",d0);e.writeRegister("D1",d1);runNative(entry,mask,frame);return reg("D0");}
  finally{stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
 }
 @Override void beforeOriginal()throws Exception {
  int oldLimit=nativeInstructionLimit;
  try{
   dispatching=true;trace.add("RESET-SCENARIO:full stock reset 604048c3 (call form of 603f0de3), instruction cap raised to 200M for this call only");
   nativeInstructionLimit=200000000;
   try{nested(0x604048c3L,0xf0,0x1c,0,0);}finally{nativeInstructionLimit=oldLimit;}
   resetScenario="full-stock-reset";
  }catch(Exception ex){
   trace.add("RESET-SCENARIO:full reset boundary: "+ex);
   long dflt=nested(0x60404f35L,0x80,0x4,24,0);trace.add(String.format("RESET-SCENARIO:native default reader 60404f35(UI 24)=%x",dflt));
   nested(0x60419368L,0xc0,0xc,24,dflt);resetScenario="narrow-ui24-reset (full reset hit a boundary)";
  }finally{dispatching=false;}
  trace.add("RESET-SCENARIO:"+resetScenario+" applied; the native consumer's observed value is logged as AF-RAW-MODE-CODE");
  Files.writeString(Paths.get(getScriptArgs()[0]).resolve("reset-scenario.txt"),"scenario="+resetScenario+"; check value: AF-RAW-MODE-CODE line in timeout-trace.txt (native getter 6031c0eb output)\n");
  super.beforeOriginal();
 }
}
