// Bounded native comparisons of Subject Detect Off and selection suppression.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;

public class OM3LifecycleContracts extends GhidraScript {
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
  for(int mode=0;mode<=6;mode++){
   EmulatorHelper e=init();try{
    e.writeRegister("D0",mode);final int[] commands={0},waits={0},errors={0};final int value=mode;
    execute(e,0x608401afL,Set.of(),(em,t)->{
     if(t==0x60841102L){long p=reg(em,"A0");check(byteAt(em,p)==1&&byteAt(em,p+12)==value,"Start command fields");commands[0]++;}
     else if(t==0x60890a0dL){check(reg(em,"D1")==8,"Start wait mask");waits[0]++;}
     else if(t==0x60068a54L){check(value==0,"Unexpected start error");errors[0]++;}
     else throw new Exception("Unexpected start call "+Long.toHexString(t));
    });
    check(commands[0]==(mode==0?0:1)&&waits[0]==commands[0]&&errors[0]==(mode==0?1:0),"Start acceptance");
    check(reg(e,"D0")== (mode==0?4:0),"Start return status");
    results.add("PASS native detector start class="+mode+", commands="+commands[0]+", wait mask=8 when valid; submit/wait/error modeled");
   }finally{e.dispose();}
  }
  for(int flag=0;flag<=1;flag++){
   final int value=flag;EmulatorHelper e=init();try{
    e.writeRegister("D0",flag);final List<String> order=new ArrayList<>();
    execute(e,0x608402adL,Set.of(),(em,t)->{
     if(t==0x60841102L){long p=reg(em,"A0");check(byteAt(em,p)==2&&byteAt(em,p+12)==value,"Stop command fields");order.add("submit");}
     else if(t==0x60890a0dL){check(reg(em,"D1")==16,"Stop wait mask");order.add("wait");}
     else throw new Exception("Unexpected stop call");
    });check(order.equals(Arrays.asList("submit","wait")),"Stop order");
    results.add("PASS native stop wrapper flag="+flag+": command kind 2 then wait mask 16; external services modeled");
   }finally{e.dispose();}
  }
  for(int gate=0;gate<=1;gate++)for(int auxiliary=0;auxiliary<4;auxiliary++){
   final int g=gate,a=auxiliary;EmulatorHelper e=init();try{
    long p=0x70020000L;e.writeMemory(toAddr(p),new byte[8]);e.writeMemoryValue(toAddr(p+4),2,gate);e.writeRegister("A0",p);
    byteAt(e,0x62a6a523L,1);byteAt(e,0x62a6a0f0L,auxiliary>>1);byteAt(e,0x62a6a0efL,auxiliary&1);
    final List<String> order=new ArrayList<>();
    execute(e,0x603ce960L,Set.of(),(em,t)->{
     if(t==0x6004d35eL)order.add("guard");
     else if(t==0x608402adL){check(byteAt(em,0x62a6a523L)==0,"Active flag not cleared first");check(reg(em,"D0")== (a==2?1:0),"Stop flag policy");order.add("stop");}
     else if(t==0x6004d43fL)order.add("release");
     else throw new Exception("Unexpected stop policy call");
    });check(order.equals(g==1?Arrays.asList("guard","stop","release"):Collections.emptyList()),"Stop gate/order");
    check(byteAt(e,0x62a6a523L)==(gate==1?0:1),"Stop active state");
    results.add("PASS native stock stop policy: eligibility="+gate+", auxiliary="+auxiliary+", order="+order+"; services modeled");
   }finally{e.dispose();}
  }
  for(int oldMode=0;oldMode<=6;oldMode++)for(int newMode=0;newMode<=6;newMode++){
   final int oldValue=oldMode,newValue=newMode;EmulatorHelper e=init();try{
    byteAt(e,0x62a6a0ebL,newMode);byteAt(e,0x62a6a523L,1);e.writeRegister("D0",oldMode);final int[] calls={0};
    execute(e,0x603cee28L,Set.of(),(em,t)->{check(t==0x6084036fL&&reg(em,"D0")==newValue,"Change class argument");calls[0]++;});
    check(calls[0]==(oldMode!=0&&newMode!=0&&oldMode!=newMode?1:0),"Class change gate");
    results.add("PASS native active class transition "+oldValue+" -> "+newValue+", change notifications="+calls[0]+"; notification body modeled");
   }finally{e.dispose();}
  }
  // Stock type conversion outputs four bytes; these are descriptor bytes,
  // not a demonstrated complete ten-byte active target profile.
  int[] types={2,0,3,3,0,3,7,7,7,7,3};
  for(int type=0;type<=10;type++){
   EmulatorHelper e=init();try{
    long p=0x70030000L;e.writeMemory(toAddr(p),new byte[]{(byte)0xa5,0,0,0,0,(byte)0xa5});e.writeRegister("A0",p+1);e.writeRegister("D0",type);
    execute(e,0x609b3ecdL,Set.of(),(em,t)->{
     check(t==0x60063380L,"Unexpected type conversion callee");long key=reg(em,"D0"),index=reg(em,"D1");
     check(key==0x1dd1||key==0x1df1,"Unexpected type conversion key");em.writeRegister("D0",key==0x1dd1?10+index:1);
    });
    byte[] b=e.readMemory(toAddr(p),6);check((b[0]&255)==0xa5&&(b[5]&255)==0xa5,"Descriptor guard overwritten");
    check((b[1]&255)==types[type],"Converted internal descriptor kind");
    int v=type>=6&&type<=9?10+2*(type-5):1,h=type>=6&&type<=9?v+1:1,c=(type==3||type==5||type>=6)?1:0;
    check((b[2]&255)==v&&(b[3]&255)==h&&(b[4]&255)==c,"Converted dimensions/priority");
    results.add("PASS native stock target enum="+type+" -> descriptor="+(b[1]&255)+","+v+","+h+","+c+"; custom dimensions/priority accessor values modeled");
   }finally{e.dispose();}
  }
  for(int kind=1;kind<=3;kind++){
   EmulatorHelper e=init();try{
    byteAt(e,0x7001001cL,kind);e.writeRegister("A2",0x7001001cL);final List<Long> calls=new ArrayList<>();
    execute(e,0x60841af4L,Set.of(0x60841b76L),(em,t)->{check(reg(em,"A0")==0x7001001cL,"Dispatcher pointer");calls.add(t);});
    long expected=kind==1?0x60841bd1L:kind==2?0x60841ce6L:0x60841e24L;
    check(calls.equals(Arrays.asList(expected)),"Command dispatch mismatch");
    results.add("PASS native worker switch kind="+kind+" -> "+Long.toHexString(expected)+"; handler modeled, queue processing excluded");
   }finally{e.dispose();}
  }
  for(int mode=1;mode<=6;mode++){
   EmulatorHelper e=init();try{
    long p=0x70040000L;e.writeMemory(toAddr(p),new byte[16]);byteAt(e,p+12,mode);e.writeRegister("A0",p);byteAt(e,0xa33a1d10L,0);
    final List<String> order=new ArrayList<>();final int value=mode;
    execute(e,0x60841bd1L,Set.of(),(em,t)->{
     if(t==0x6084177fL)order.add("initialize");
     else if(t==0x6087144eL){check(byteAt(em,0xa33a1d10L)==1&&byteAt(em,0xa33a1d14L)==value,"Worker start state/class");order.add("reset");}
     else if(t==0x608909a5L)order.add("signal:"+reg(em,"D1"));
     else throw new Exception("Unexpected start worker call "+Long.toHexString(t));
    });check(order.equals(Arrays.asList("initialize","reset","signal:8","signal:2")),"Worker start sequence");
    results.add("PASS native start worker class="+mode+": stores requested class, state=1, reset then completion signals 8/2; callees modeled");
   }finally{e.dispose();}
  }
  for(int flag=0;flag<=1;flag++){
   EmulatorHelper e=init();try{
    long p=0x70040000L;e.writeMemory(toAddr(p),new byte[16]);byteAt(e,p+12,flag);e.writeRegister("A0",p);byteAt(e,0xa33a1d10L,1);
    final List<String> order=new ArrayList<>();final int value=flag;
    execute(e,0x60841ce6L,Set.of(),(em,t)->{
     if(t==0x60842965L)order.add("drain");
     else if(t==0x6084e7b8L){check(byteAt(em,0xa33a1d10L)==0,"Worker state not cleared");order.add("cleanup");}
     else if(t==0x608714e9L){check(reg(em,"D0")==value,"Worker reset option");order.add("reset");}
     else if(t==0x608909a5L){check(reg(em,"D1")==16,"Worker stop signal");order.add("signal");}
     else throw new Exception("Unexpected stop worker call "+Long.toHexString(t));
    });check(order.equals(Arrays.asList("drain","cleanup","reset","signal")),"Worker stop sequence");
    results.add("PASS native stop worker option="+flag+": drain call, state=0, cleanup/reset, completion signal 16; drain/cleanup/reset/signal implementations modeled");
   }finally{e.dispose();}
  }
  Files.write(out.resolve("lifecycle-results.txt"),results);
  Files.writeString(out.resolve("lifecycle-scope.txt"),"Original instruction fragments under community MN10300 Sleigh. Terminal returns and call frames excluded. Command submit, completion waits, synchronization and errors modeled. Stock stop policy, command wrappers, worker switch and worker handlers tested separately, not one end-to-end lifecycle. Worker initialization/stop-related/cleanup/reset/signal callees modeled; their completion and full invalidation are not established. Class-change notification body modeled. Target conversion tests use fixture custom dimensions/priority and prove a four-byte descriptor, not complete target activation or stock display names. No ownership controller, camera, DNN, lens, C-AF, bursts or firmware installation executed.\n");
  println("LIFECYCLE CONTRACTS: "+results.size()+" PASS");
 }catch(Exception ex){Files.write(out.resolve("lifecycle-results.txt"),results);Files.writeString(out.resolve("lifecycle-failure.txt"),ex.toString());throw ex;}
 }
}
