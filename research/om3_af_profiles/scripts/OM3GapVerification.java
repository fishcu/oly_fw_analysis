// Bounded native comparisons of Subject Detect Off and selection suppression.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;

public class OM3GapVerification extends GhidraScript {
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

 List<String> trace; int signals; long profileSource=0x70060000L;
 void nativeCall(EmulatorHelper e,long target)throws Exception{
  String[] saved={"D2","D3","A2","A3","SP"};long[] v=new long[5];for(int i=0;i<5;i++)v[i]=reg(e,saved[i]);
  e.writeRegister("SP",v[4]-0x400);e.writeMemory(toAddr(v[4]-0x400),new byte[0x300]);
  execute(e,target,Set.of(),this::model);
  for(int i=0;i<5;i++)e.writeRegister(saved[i],v[i]);
 }
 void model(EmulatorHelper e,long t)throws Exception{
  if(t==0x50002a15L){long p=reg(e,"A0");int n=(int)reg(e,"D1");check(n>=0&&n<0x2000,"Memset size");byte[] b=new byte[n];Arrays.fill(b,(byte)reg(e,"D0"));e.writeMemory(toAddr(p),b);trace.add("memset:"+Long.toHexString(p)+":"+n);}
  else if(Set.of(0x60842965L,0x6082e1d4L,0x6082ba97L,0x6084e7b8L,0x608714e9L,0x608717b9L,0x60872150L).contains(t)){trace.add("native:"+Long.toHexString(t));nativeCall(e,t);}
  else if(t==0x609b3bb2L){e.writeRegister("A0",profileSource);}
  else if(t==0x60072c53L){check(reg(e,"A0")==0x6082e204L,"Device callback selection");trace.add("dispatcher:model");nativeCall(e,0x6082e204L);}
  else if(t==0x608909a5L){check(reg(e,"D1")==16,"Stop completion mask");check(byteAt(e,0xa33a1d10L)==0&&byteAt(e,0xa33ac4d8L)==0,"Completion before state reset");signals++;trace.add("completion:model");}
  else if(Set.of(0x60081d1dL,0x60081d27L,0x6007f883L,0x6070d6eaL,0x60875b3fL,0x60871393L,0x6086cd5eL).contains(t)){trace.add("external-model:"+Long.toHexString(t));}
  else if(t==0x60068a54L){check(reg(e,"D0")==0x31060009L,"Unexpected reset diagnostic");trace.add("reset-ineligible:error-service-modeled-as-returning");}
  else throw new Exception("Unmodeled stop-chain callee "+Long.toHexString(t));
 }
 public void run()throws Exception{
 Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>(),notes=new ArrayList<>();
 long[][] buffers={{0xa33a3010L,0x3fc},{0x62f8d800L,0x3c2},{0xa33a3550L,0xa4},{0xa33a3648L,0x10},{0xa33a3670L,0x52},{0xa33a36c2L,0xa2},
 {0xa33a7de0L,0x164},{0xa33a7f44L,0x164},{0xa33ac394L,0xf6},{0xa33a7408L,0x878},{0xa33a6b64L,0x878}};
 try{
  for(int eligible=0;eligible<=1;eligible++){
   EmulatorHelper e=init();try{
    trace=new ArrayList<>();signals=0;
    for(long[] b:buffers){byte[] seed=new byte[(int)b[1]];Arrays.fill(seed,(byte)0x6b);e.writeMemory(toAddr(b[0]),seed);}
    byteAt(e,0xa33a1d10L,1);byteAt(e,0xa33a1d12L,0);byteAt(e,0xa33ac4d8L,eligible);byteAt(e,0xa33ac4e1L,1);
    byte[] snapshot=new byte[12];Arrays.fill(snapshot,(byte)0x7b);e.writeMemory(toAddr(0xa33ac4f8L),snapshot);
    long p=0x70050000L;e.writeMemory(toAddr(p),new byte[16]);e.writeRegister("A0",p);
    execute(e,0x60841ce6L,Set.of(),this::model);check(signals==1,"Missing completion service call");
    for(int i=0;i<buffers.length;i++)for(byte v:e.readMemory(toAddr(buffers[i][0]),(int)buffers[i][1]))check(v==(i<6||eligible==1?0:(byte)0x6b),"Eligibility/reset buffer result");
    for(byte v:e.readMemory(toAddr(0xa33ac4f8L),12))check(v==(eligible==1?0:(byte)0x7b),"Eligibility/snapshot result");
    results.add("PASS eligibility audit: reset flag="+eligible+", first six buffers clear, remaining five "+(eligible==1?"clear":"retain seeded bytes")+", completion service called; ineligible diagnostic modeled as returning");notes.add("eligibility="+eligible+" "+trace);
   }finally{e.dispose();}
  }
  EmulatorHelper e=init();try{
   e.writeMemory(toAddr(0xa33a1c18L),new byte[0x100]);final List<String> scheduled=new ArrayList<>();
   for(int kind:new int[]{5,2,1}){
    long p=0x70050000L;byte[] command=new byte[124];Arrays.fill(command,(byte)(0x40+kind));command[0]=(byte)kind;e.writeMemory(toAddr(p),command);e.writeRegister("A0",p);
    execute(e,0x60841102L,Set.of(),(em,t)->{
     if(t==0x60075f73L){check(reg(em,"D0")==5,"Submission guard");em.writeRegister("D0",0x1234);}
     else if(t==0x60075fbcL){check(reg(em,"D0")==0x1234,"Submission release token");}
     else if(t==0x60023c05L)em.writeRegister("D0",123);
     else if(t==0x60056edeL){check(reg(em,"A0")==0x608418feL,"First callback");scheduled.add("first");}
     else if(t==0x600760f9L){check(reg(em,"A0")==0x608412c5L,"Deferred callback");scheduled.add("replace");}
     else throw new Exception("Unexpected submit callee "+Long.toHexString(t));
    });
    check(byteAt(e,0xa33a1c18L)==5,"In-progress command kind changed");
    if(kind!=5)check(Arrays.equals(e.readMemory(toAddr(0xa33a1c94L),124),command),"Deferred command copy");
   }
   check(scheduled.equals(Arrays.asList("first","replace","replace")),"Deferred submission order");
   results.add("PASS deferred submission audit: with callbacks held by model, kinds 5 -> 2 -> 1 leave current kind 5 and replacement slot kind 1; latest 124-byte deferred copy replaces prior stop record");notes.add("Submission callbacks explicitly withheld: "+scheduled);
  }finally{e.dispose();}
  for(int stopped=0;stopped<=1;stopped++){
   e=init();try{
    byte[] source=new byte[356];Arrays.fill(source,(byte)0x5a);e.writeMemory(toAddr(0xa33a7de0L),source);e.writeMemory(toAddr(0xa33a7f44L),new byte[356]);
    byteAt(e,0xa33a1d10L,stopped==1?0:1);byteAt(e,0xa33ac4d8L,stopped==1?0:1);
    execute(e,0x608719e7L,Set.of(0x608719fcL),noCalls);
    check(Arrays.equals(e.readMemory(toAddr(0xa33a7f44L),356),source),"Result copy mismatch");
    results.add("PASS bounded result-copy audit: worker stopped="+stopped+", 356-byte source copied to working buffer; entry reachability after stop not established");
   }finally{e.dispose();}
  }
  Files.write(out.resolve("gap-verification-results.txt"),results);Files.write(out.resolve("gap-verification-traces.txt"),notes);
  Files.writeString(out.resolve("gap-verification-scope.txt"),"Original bounded instructions; imported memset, callback scheduling/delivery, synchronization, other reset helpers and completion services modeled. Reset diagnostic explicitly modeled as returning. Deferred submission test withholds callbacks and calls raw submit, not synchronous stock stop/restart wrappers. Result-copy test starts within function and does not prove post-stop reachability or a real race. Terminal returns and nested callee registers/stack frames modeled. No camera or complete extension.\n");
  println("GAP VERIFICATION: "+results.size()+" PASS");
 }catch(Exception ex){Files.write(out.resolve("gap-verification-results.txt"),results);Files.writeString(out.resolve("gap-verification-failure.txt"),ex.toString());throw ex;}
 }
}
