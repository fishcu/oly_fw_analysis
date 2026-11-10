// Native calls and returns, with only enumerated external service hooks.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;
public class OM3NativeFlow extends GhidraScript {
 EmulatorHelper e; List<String> trace=new ArrayList<>();Map<Long,Integer> settings=new HashMap<>();
 long stackTop=0x70080000L;
 Set<Long> breakpoints=new HashSet<>();long hitBreakpoint=0;
 Map<Long,PseudoInstruction> decodeCache=new HashMap<>();
 long observedStackLow=0xffffffffL;
 long callTarget(PseudoInstruction ins)throws Exception{
  if(ins.getFlows().length==1)return ins.getFlows()[0].getOffset();
  Object[] op=ins.getOpObjects(0);
  for(Object x:op)if(x instanceof ghidra.program.model.lang.Register){long t=reg(((ghidra.program.model.lang.Register)x).getName());check(t!=0&&currentProgram.getMemory().contains(toAddr(t)),"Unresolved indirect target "+ins.getAddress()+" "+ins+" -> "+Long.toHexString(t));return t;}
  throw new Exception("Unresolved indirect call "+ins.getAddress()+" "+ins);
 }
 boolean instruction(PseudoInstruction ins)throws Exception{return false;}
 long reg(String r){return e.readRegister(r).longValue()&0xffffffffL;}
 void check(boolean b,String s)throws Exception{if(!b)throw new Exception(s);}
 int u16(long p)throws Exception{byte[] b=e.readMemory(toAddr(p),2);return (b[0]&255)|((b[1]&255)<<8);}
 void byteAt(long p,int v){e.writeMemoryValue(toAddr(p),1,v);}
 void setting(int k,int i,int v){settings.put(((long)k<<16)|i,v);}
 void init(){decodeCache.clear();e=new EmulatorHelper(currentProgram);for(String r:new String[]{"D0","D1","D2","D3","A0","A1","A2","A3","MDR","PSW"})e.writeRegister(r,0);e.writeMemory(toAddr(0x70000000L),new byte[0x100000]);e.writeMemory(toAddr(0xa33ca200L),new byte[0x600]);e.writeMemory(toAddr(0xa33f2c90L),new byte[0x100]);e.writeMemory(toAddr(0xa33f3770L),new byte[0x150]);e.writeMemoryValue(toAddr(0x8050L),4,0);}
 boolean external(long t)throws Exception{
  if(t==0x60063380L){long k=(reg("D0")<<16)|reg("D1");check(settings.containsKey(k),"Unprovided setting "+Long.toHexString(reg("D0"))+"["+reg("D1")+"]");e.writeRegister("D0",settings.get(k));trace.add("setting:"+Long.toHexString(k));return true;}
  if(t==0x60068a54L||t==0x609dcdddL)throw new Exception("Diagnostic path "+Long.toHexString(t)+" code="+Long.toHexString(reg("D0")));
  return false;
 }
 void runNative(long entry,int mask,int frame)throws Exception{
  long top=stackTop,stop=0x70fff000L,p=top;e.writeMemoryValue(toAddr(top),4,stop);
  String[] rs={"D2","D3","A2","A3"};int[] bits={128,64,32,16};
  for(int i=0;i<4;i++)if((mask&bits[i])!=0){p-=4;e.writeMemoryValue(toAddr(p),4,reg(rs[i]));}
  e.writeRegister("SP",top-frame);e.writeRegister("MDR",stop);e.writeRegister("PC",entry);
  PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  for(int i=0;i<200000;i++){
   long pc=e.getExecutionAddress().getOffset();observedStackLow=Math.min(observedStackLow,reg("SP"));if(pc==stop){check(reg("SP")==top,"Root stack did not restore");return;}if(breakpoints.contains(pc)){hitBreakpoint=pc;return;}
   PseudoInstruction ins=decodeCache.get(pc);if(ins==null){ins=dis.disassemble(toAddr(pc),e.readMemory(toAddr(pc),16));check(ins!=null,"Decode "+Long.toHexString(pc)+" bytes="+java.util.HexFormat.of().formatHex(e.readMemory(toAddr(pc),16)));decodeCache.put(pc,ins);}
   if(instruction(ins))continue;
   if(ins.getMnemonicString().startsWith("udf"))throw new Exception("Opaque instruction "+Long.toHexString(pc)+" "+ins);
   if(ins.getFlowType().isCall()){
    long t=callTarget(ins);
    if(external(t)){e.writeRegister("MDR",pc+ins.getLength());e.writeRegister("PC",pc+ins.getLength());continue;}
    trace.add("native-call:"+Long.toHexString(t));
   }
   check(e.step(monitor),"Native failure "+Long.toHexString(pc)+": "+e.getLastError());
  }throw new Exception("Native bound exceeded");
 }
 public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  try{
   for(int wide=0;wide<=1;wide++){
    init();try{
     settings.clear();trace.clear();setting(0x9a41,0,0);setting(0x1dd1,0,wide==1?27:1);setting(0x1dd1,1,wide==1?39:1);setting(0x84d1,0,3);setting(0x88b2,0,526);setting(0x1df1,0,0);setting(0x1e01,0,0);setting(0x85b1,0,0);setting(0x8551,0,0);setting(0x7e81,0,0);setting(0x7e91,0,0);
     byteAt(0xa33f2ceaL,1);byteAt(0xa33f2cb0L,1);e.writeMemoryValue(toAddr(0xa33f2cdaL),2,100);e.writeMemoryValue(toAddr(0xa33ca2b8L),2,0x1700);e.writeMemoryValue(toAddr(0xa33ca314L),2,3);
     e.writeRegister("D0",3);runNative(0x609029f1L,0xb0,0x14);
     check(u16(0xa33ca384L)==526&&u16(0xa33ca388L)==(wide==1?27:1)&&u16(0xa33ca38aL)==(wide==1?39:1),"Native profile refresh/copy");
     long p=0x70090000L;e.writeRegister("A0",p);e.writeRegister("A1",p+2);e.writeRegister("D0",p+4);e.writeRegister("D1",p+6);runNative(0x609dc311L,0xf0,0x2c);
     results.add("PASS native call/return pipeline: target refresh -> active copy -> geometry -> finalizer -> grid rectangle: wide="+wide+", rectangle="+u16(p)+","+u16(p+2)+","+u16(p+4)+","+u16(p+6));
     e.writeMemory(toAddr(0xa33f3600L),new byte[0x180]);e.writeMemoryValue(toAddr(0xa33f3618L),4,0x70091000L);e.writeMemoryValue(toAddr(0xa33f3644L),4,0x70092000L);e.writeMemory(toAddr(0xa32d3d30L),new byte[8]);
     e.writeRegister("A0",p+0x100);runNative(0x608ff478L,0x30,0x18);
     check(u16(p+0x118)==u16(p)&&u16(p+0x11a)==u16(p+4)&&u16(p+0x11c)==u16(p+2)&&u16(p+0x11e)==u16(p+6),"Snapshot target rectangle");
     results.add("PASS complete 50-byte subject snapshot uses current native target rectangle: wide="+wide);
     Files.write(out.resolve("native-flow-trace-"+wide+".txt"),trace);
    }finally{e.dispose();}
   }
   Files.write(out.resolve("native-flow-results.txt"),results);println("NATIVE FLOW: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("native-flow-results.txt"),results);Files.write(out.resolve("native-flow-last-trace.txt"),trace);Files.writeString(out.resolve("native-flow-failure.txt"),ex.toString());throw ex;}
 }
}

