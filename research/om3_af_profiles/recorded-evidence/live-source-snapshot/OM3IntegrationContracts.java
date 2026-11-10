// Bounded native comparisons of Subject Detect Off and selection suppression.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;

public class OM3IntegrationContracts extends GhidraScript {
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
  else throw new Exception("Unmodeled stop-chain callee "+Long.toHexString(t));
 }
 public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>(),traces=new ArrayList<>();
  long[][] buffers={{0xa33a3010L,0x3fc},{0x62f8d800L,0x3c2},{0xa33a3550L,0xa4},{0xa33a3648L,0x10},{0xa33a3670L,0x52},{0xa33a36c2L,0xa2},
   {0xa33a7de0L,0x164},{0xa33a7f44L,0x164},{0xa33ac394L,0xf6},{0xa33a7408L,0x878},{0xa33a6b64L,0x878}};
  try{
   for(int mode=1;mode<=6;mode++)for(int option=0;option<=1;option++)for(int inflight=0;inflight<=1;inflight++){
    EmulatorHelper e=init();try{
     trace=new ArrayList<>();signals=0;
     e.writeMemoryValue(toAddr(0x9c180004L),4,0);
     for(long[] b:buffers){byte[] seed=new byte[(int)b[1]];Arrays.fill(seed,(byte)0x6b);e.writeMemory(toAddr(b[0]),seed);}
     byteAt(e,0xa33a1d10L,1);byteAt(e,0xa33a1d12L,inflight);byteAt(e,0xa33a1d14L,mode);
     byteAt(e,0xa33ac4d8L,1);byteAt(e,0xa33ac4e1L,1);byteAt(e,0xa33ac4e4L,3);
     e.writeMemoryValue(toAddr(0xa33a5a84L),2,400);e.writeMemoryValue(toAddr(0xa33a5a86L),2,120);
     e.writeMemory(toAddr(0xa33ac4f8L),new byte[12]);
     long p=0x70050000L;e.writeMemory(toAddr(p),new byte[16]);byteAt(e,p+12,option);e.writeRegister("A0",p);
     execute(e,0x60841ce6L,Set.of(),this::model);
     check(signals==1,"Completion signal missing");
     for(long[] b:buffers)for(byte v:e.readMemory(toAddr(b[0]),(int)b[1]))check(v==0,"Uncleared seeded buffer "+Long.toHexString(b[0]));
     check(byteAt(e,0xa33a1d12L)==0,"Inflight state remains");
     check(byteAt(e,0xa33ac4f8L)==option&&byteAt(e,0xa33ac4f9L)==option,"Selection snapshot option mismatch");
     check(Arrays.equals(e.readMemory(toAddr(0xa33ac4faL),4),option==1?new byte[]{(byte)0x90,1,120,0}:new byte[4]),"Selection coordinates retention mismatch");
     check(trace.contains("native:6082ba97")== (inflight==1),"Device stop gate mismatch");
     if(inflight==1)check(Arrays.equals(e.readMemory(toAddr(0x9c180000L),4),new byte[]{3,0,0,0}),"Device stop MMIO fixture");
     results.add("PASS nested native stop: SCP class="+mode+", option="+option+", inflight="+inflight+"; 11 seeded buffers clear, reset state before completion, selection snapshot="+(option==1?"retained":"cleared")+"; models and MMIO RAM fixture apply");
     traces.add("class="+mode+" option="+option+" inflight="+inflight+" "+trace);
    }finally{e.dispose();}
   }
   for(int state:new int[]{0x1700,0x3000})for(int allowed:new int[]{0,3}){
    EmulatorHelper e=init();try{
     trace=new ArrayList<>();long statep=0x70061000L;
     e.writeMemoryValue(toAddr(statep),2,state);e.writeMemoryValue(toAddr(0xa33ca314L),2,allowed);
     byte[] record={14,2,3,0,1,0,1,0,0,0};e.writeMemory(toAddr(profileSource),record);e.writeMemory(toAddr(0xa33ca384L),new byte[10]);
     e.writeRegister("D0",3);final List<String> order=new ArrayList<>();
     execute(e,0x609029f1L,Set.of(),(em,t)->{
      if(t==0x608fe2e3L)em.writeRegister("A0",statep);
      else if(t==0x609b3481L)em.writeRegister("A0",0xa33f2c9cL);
      else if(t==0x60903e55L){check(reg(em,"A0")==0xa33ca384L,"Update destination");nativeCall(em,t);order.add("copy");}
      else if(t==0x60903e88L){check(Arrays.equals(em.readMemory(toAddr(0xa33ca384L),10),record),"Geometry called before profile copy");order.add("geometry");}
      else if(t==0x6090419dL)order.add("finish");
      else throw new Exception("Unexpected target update call "+Long.toHexString(t));
     });
     List<String> expected=state==0x3000?Collections.emptyList():allowed==0?Arrays.asList("finish"):Arrays.asList("copy","geometry","finish");
     check(order.equals(expected),"Target update gates/order");
     results.add("PASS native active target update state="+Integer.toHexString(state)+", allowed mask="+allowed+", order="+order+"; copy native, accessor/geometry/finalizer modeled");
    }finally{e.dispose();}
   }
   Files.write(out.resolve("integration-results.txt"),results);Files.write(out.resolve("stop-chain-traces.txt"),traces);
   Files.writeString(out.resolve("integration-scope.txt"),"Nested bounded original instructions under community MN10300 Sleigh. Saved callee registers and stack frames explicitly modeled at every nested call. Memset import, device dispatcher callback delivery, delay/critical services, secondary reset helpers and completion signal services modeled. MMIO addresses are emulator RAM, not physical device behavior. Top-level queue delivery, concurrent producers, memory ordering and later result repopulation excluded. Eleven named seeded buffer ranges verified; not every camera result store. Stop option 1 retains selection snapshot. Four active-target-update fixtures execute update gates and native ten-byte copy, with source accessor, geometry and finalizer modeled; synthetic target record, not complete stock zone activation. No physical camera, firmware patch or complete AF controller.\n");
   println("INTEGRATION CONTRACTS: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("integration-results.txt"),results);Files.writeString(out.resolve("integration-failure.txt"),ex.toString());throw ex;}
 }
}
