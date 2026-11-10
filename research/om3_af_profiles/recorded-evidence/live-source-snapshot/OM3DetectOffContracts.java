// Bounded native comparisons of Subject Detect Off and selection suppression.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;

public class OM3DetectOffContracts extends GhidraScript {
 interface Model {void call(EmulatorHelper e,long target)throws Exception;}
 long reg(EmulatorHelper e,String r){return e.readRegister(r).longValue()&0xffffffffL;}
 void check(boolean b,String s)throws Exception{if(!b)throw new Exception(s);}
 void byteAt(EmulatorHelper e,long a,int v){e.writeMemoryValue(toAddr(a),1,v);}
 int byteAt(EmulatorHelper e,long a)throws Exception{return e.readMemory(toAddr(a),1)[0]&255;}
 EmulatorHelper init(){
  EmulatorHelper e=new EmulatorHelper(currentProgram);
  for(String r:new String[]{"D0","D1","D2","D3","A0","A1","A2","A3","MDR","PSW"})e.writeRegister(r,0);
  e.writeRegister("SP",0x70010000L);e.writeMemory(toAddr(0x7000f000L),new byte[0x3000]);
  e.writeMemoryValue(toAddr(0xa337174cL),4,0);return e;
 }
 Model noCalls=(e,t)->{throw new Exception("Unexpected call "+Long.toHexString(t));};
 long execute(EmulatorHelper e,long entry,Set<Long> stops,Model model)throws Exception{
  e.writeRegister("PC",entry);PseudoDisassembler dis=new PseudoDisassembler(currentProgram);
  for(int i=0;i<1500;i++){
   long pc=e.getExecutionAddress().getOffset();if(stops.contains(pc))return pc;
   PseudoInstruction ins=dis.disassemble(toAddr(pc));check(ins!=null,"Decode failure");
   if(ins.getFlowType().isCall()){
    check(ins.getFlows().length==1,"Indirect call requires model");model.call(e,ins.getFlows()[0].getOffset());
    e.writeRegister("PC",pc+ins.getLength());
   }else if(ins.getFlowType().isTerminal())return pc;
   else check(e.step(monitor),"Instruction failure "+Long.toHexString(pc)+": "+e.getLastError());
  }throw new Exception("Instruction bound");
 }
 public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  try{
   // Exact stock setting -> configuration byte, getter explicitly modeled.
   for(int mode=0;mode<=6;mode++){
    final int input=mode;EmulatorHelper e=init();try{
     long p=0x70020000L;e.writeMemory(toAddr(p),new byte[0x100]);e.writeRegister("A2",p);
     execute(e,0x603c6454L,Set.of(0x603c6465L),(em,t)->{
      check(t==0x60063380L&&reg(em,"D0")==0x1e71&&reg(em,"D1")==0,"Wrong setting query");
      em.writeRegister("D0",input);
     });check(byteAt(e,p+0xce)==mode,"SCP mode copy mismatch");
     results.add("PASS native setting-to-config copy: Subject Detect="+mode+" -> config+0xce; setting accessor modeled");
    }finally{e.dispose();}
   }
   // Mode changes have a separate lifecycle notification gate.
   for(int active:new int[]{0,1})for(int[] pair:new int[][]{{6,0},{0,6},{6,4},{6,6}}){
    EmulatorHelper e=init();try{
     byteAt(e,0x62a6a0ebL,pair[1]);byteAt(e,0x62a6a523L,active);e.writeRegister("D0",pair[0]);final int[] calls={0};
     execute(e,0x603cee28L,Set.of(),(em,t)->{check(t==0x6084036fL,"Unexpected notification");check(reg(em,"D0")==pair[1],"Notification mode");calls[0]++;});
     int expected=active==1&&pair[0]!=pair[1]&&pair[0]!=0&&pair[1]!=0?1:0;
     check(calls[0]==expected,"Mode lifecycle gate mismatch");
     results.add("PASS native mode-change notification: active="+active+", "+pair[0]+" -> "+pair[1]+", class-change calls="+calls[0]);
    }finally{e.dispose();}
   }
   // Runtime setter can change effective mode without a settings setter call.
   for(int mode:new int[]{0,6}){
    EmulatorHelper e=init();try{
     byteAt(e,0x62a6a0ebL,mode==0?6:0);byteAt(e,0x62a6a523L,1);e.writeRegister("D0",mode);
     final int[] locks={0},notifies={0};
     execute(e,0x603cedfeL,Set.of(),(em,t)->{
      if(t==0x60075f73L){check(reg(em,"D0")==2,"Lock identifier");em.writeRegister("D0",0x1234);locks[0]++;}
      else if(t==0x60075fbcL){check(reg(em,"D0")==0x1234,"Unlock token");locks[0]++;}
      else if(t==0x603cee28L){check(reg(em,"D0")== (mode==0?6:0),"Old mode lost");execute(em,t,Set.of(),noCalls);notifies[0]++;}
      else throw new Exception("Unexpected setter callee "+Long.toHexString(t));
     });check(byteAt(e,0x62a6a0ebL)==mode&&locks[0]==2&&notifies[0]==1,"Runtime setter contract");
     results.add("PASS native effective-mode setter: mode="+mode+"; lock services modeled, notification gate native; no settings setter called");
    }finally{e.dispose();}
   }
   // A real stock decision consults effective mode, independently of suppression.
   for(int mode:new int[]{0,6})for(int suppressed:new int[]{0,1}){
    EmulatorHelper e=init();try{
     long p=0x70030000L,q=0x70031000L;e.writeMemory(toAddr(p),new byte[0x600]);byteAt(e,q,0xaa);
     e.writeMemoryValue(toAddr(p+0x59c),2,1);byteAt(e,0x62a6a0ebL,mode);byteAt(e,0x62a6a0e4L,0);byteAt(e,0xa33ac4f4L,suppressed);
     e.writeRegister("A0",p);e.writeRegister("A1",q);
     long pc=execute(e,0x60703ddeL,Set.of(0x60703e3cL,0x60703e55L),noCalls);
     check(pc==(mode==0?0x60703e55L:0x60703e3cL),"Effective mode decision mismatch");
     check(byteAt(e,q)==0,"Output initialization");
     results.add("PASS native detection decision: mode="+mode+", suppression="+suppressed+" -> "+(mode==0?"early Off exit":"continues to cadence calculation")+"; stops before cadence calculation");
    }finally{e.dispose();}
   }
   // Native decision -> native caller branch -> native request flag construction.
   // Allocator and one request field helper are modeled; saved registers restored
   // explicitly where terminal return/call frame execution is excluded.
   for(int mode:new int[]{0,6})for(int suppressed:new int[]{0,1}){
    EmulatorHelper em=init();try{
     long p=0x70040000L,q=0x70041000L,b=0x70042000L;
     em.writeMemory(toAddr(p),new byte[0x600]);em.writeMemory(toAddr(q),new byte[0x100]);em.writeMemory(toAddr(b),new byte[0x100]);
     em.writeMemoryValue(toAddr(p+0x59c),2,1);em.writeMemoryValue(toAddr(p+0x550),2,8);
     byteAt(em,0x62a6a0ebL,mode);byteAt(em,0x62a6a0e4L,0);byteAt(em,0x62a6a0efL,0);
     byteAt(em,0xa33ac4f4L,suppressed);em.writeRegister("A2",p);em.writeRegister("A3",q);em.writeRegister("D2",0);
     final int[] allocations={0};
     execute(em,0x607039b2L,Set.of(0x607039c8L),(e,t)->{
      String[] saved=t==0x60703ddeL?new String[]{"A2","A3"}:new String[]{"D2","D3","A2","A3"};
      long[] vals=new long[saved.length];for(int i=0;i<saved.length;i++)vals[i]=reg(e,saved[i]);
      if(t==0x60703ddeL){execute(e,t,Set.of(),(ee,tt)->{check(tt==0x60703dcbL,"Cadence callee");execute(ee,tt,Set.of(),noCalls);});}
      else if(t==0x607045b1L){execute(e,t,Set.of(),(ee,tt)->{
       if(tt==0x60707730L){allocations[0]++;ee.writeRegister("A0",b);}
       else if(tt==0x60701b5dL){ee.writeRegister("D0",0x1234);}
       else throw new Exception("Unexpected request field callee "+Long.toHexString(tt));
      });}else throw new Exception("Unexpected caller callee "+Long.toHexString(t));
      for(int i=0;i<saved.length;i++)e.writeRegister(saved[i],vals[i]);
     });
     byte[] flags=em.readMemory(toAddr(q+0xc),4);long f=0;for(int i=0;i<4;i++)f|=(long)(flags[i]&255)<<(8*i);
     check(allocations[0]==(mode==0?0:1),"Native request branch mismatch");
     check(((f&0x800)!=0)==(mode==6),"Native request flag mismatch");
     results.add("PASS native decision/caller/request integration: mode="+mode+", suppression="+suppressed+", allocations="+allocations[0]+", request bit 0x800="+((f&0x800)!=0)+"; allocator/field helper and saved registers modeled");
    }finally{em.dispose();}
   }
   // Selection disable writes its flag but leaves effective detector mode intact.
   EmulatorHelper e=init();try{
    byteAt(e,0x62a6a0ebL,6);byteAt(e,0xa33ac4f4L,0);final List<Long> calls=new ArrayList<>();
    execute(e,0x60873e6dL,Set.of(),(em,t)->{
     check(Set.of(0x60875b3fL,0x60872b14L,0x608909a5L).contains(t),"Unexpected suppression callee");calls.add(t);
    });check(byteAt(e,0xa33ac4f4L)==1&&byteAt(e,0x62a6a0ebL)==6,"Suppression/mode separation");
    check(calls.equals(Arrays.asList(0x60875b3fL,0x60872b14L,0x608909a5L)),"Suppression reset sequence");
    results.add("PASS native disable-exec: selection flag=1, effective mode remains Human; reset/publication callees modeled and order checked");
   }finally{e.dispose();}
   Files.write(out.resolve("detect-off-results.txt"),results);
   Files.writeString(out.resolve("detect-off-scope.txt"),"Bounded original MN10300 instructions under community Sleigh. No camera, lens, inference or complete AF request executed. Settings getter, lock services and selection-reset/publication callees modeled. Terminal returns/call frames excluded. Four decision-only tests stop before cadence calculation; four integration fixtures include the native divisibility helper, caller branch and request flag construction, with allocator, one request field helper and saved registers explicitly modeled. Runtime setter tests do not prove detector start/stop, result invalidation, display, C-AF or saved SCP preservation across later refreshes.\n");
   println("DETECT OFF CONTRACTS: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("detect-off-results.txt"),results);Files.writeString(out.resolve("detect-off-failure.txt"),ex.toString());throw ex;}
 }
}
