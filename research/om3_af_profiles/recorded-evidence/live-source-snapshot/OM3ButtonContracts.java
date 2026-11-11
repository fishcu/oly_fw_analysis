// Bounded native-instruction contract tests. External calls are explicit models.
// No camera, inference engine, lens or complete button controller is emulated.
// Run headless -noanalysis -readOnly.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.io.*;
import java.util.*;

public class OM3ButtonContracts extends GhidraScript {
 interface CallModel {void call(EmulatorHelper e,long target) throws Exception;}
 private long reg(EmulatorHelper e,String s){return e.readRegister(s).longValue()&0xffffffffL;}
 private int execute(EmulatorHelper e,long start,CallModel model) throws Exception {
  e.writeRegister("PC",start);PseudoDisassembler dis=new PseudoDisassembler(currentProgram);
  for(int n=0;n<1000;n++) {
   long pc=e.getExecutionAddress().getOffset();PseudoInstruction ins=dis.disassemble(toAddr(pc));
   if(ins==null)throw new Exception("Decode failed "+Long.toHexString(pc));
   if(ins.getFlowType().isCall()) {
    if(ins.getFlows().length!=1)throw new Exception("Indirect call not modeled");
    model.call(e,ins.getFlows()[0].getOffset());
    // Model a completed external call; no call frame is executed or asserted.
    e.writeRegister("PC",pc+ins.getLength());
   } else if(ins.getFlowType().isTerminal())return n;
   else if(!e.step(monitor))throw new Exception("Emulation failed at "+Long.toHexString(pc)+": "+e.getLastError());
  }
  throw new Exception("Instruction bound exceeded");
 }
 private EmulatorHelper init() {
  EmulatorHelper e=new EmulatorHelper(currentProgram);
  for(String r:new String[]{"D0","D1","D2","D3","A0","A1","A2","A3","MDR"})e.writeRegister(r,0);
  e.writeRegister("SP",0x70010000L);e.writeMemory(toAddr(0x7000f000L),new byte[0x3000]);
  e.writeMemory(toAddr(0xa33f2c90L),new byte[0x80]);e.writeMemory(toAddr(0xa33ca300L),new byte[0x20]);
  return e;
 }
 private void require(boolean b,String msg) throws Exception {if(!b)throw new Exception(msg);}
 public void run() throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  try {
   // Distinct ten-byte patterns are synthetic test records, not identified AF modes.
   for(int profile=0;profile<2;profile++) {
    EmulatorHelper e=init();try {
     byte[] pattern=new byte[10];for(int i=0;i<10;i++)pattern[i]=(byte)(profile*64+i+1);
     e.writeMemory(toAddr(0xa33f2ce0L),pattern);byte[] guard=new byte[18];Arrays.fill(guard,(byte)0xa5);
     e.writeMemory(toAddr(0x70020000L),guard);e.writeRegister("A0",0x70020004L);
     int steps=execute(e,0x60903e55L,(emu,target)->{
      require(target==0x609b3bb2L,"Unexpected copy callee");emu.writeRegister("A0",0xa33f2ce0L);
     });
     byte[] observed=e.readMemory(toAddr(0x70020000L),18);
     require(Arrays.equals(pattern,Arrays.copyOfRange(observed,4,14)),"Copy did not preserve target record");
     for(int i:new int[]{0,1,2,3,14,15,16,17})require(observed[i]==(byte)0xa5,"Copy overwrote guard");
     results.add("PASS native geometry copy: synthetic profile "+profile+", 10 exact bytes; guards preserved; instructions="+steps);
    }finally{e.dispose();}
   }
   // Each priority path consults its own byte. They are A/B until button ownership is traced.
   for(int a=0;a<2;a++)for(int b=0;b<2;b++)for(int which=0;which<2;which++) {
    EmulatorHelper e=init();try {
     e.writeMemoryValue(toAddr(0xa33f2cacL),1,a);e.writeMemoryValue(toAddr(0xa33f2cadL),1,b);
     final int[] suppress={0};long start=which==0?0x60902452L:0x609024aaL;
     execute(e,start,(emu,target)->{
      if(target==0x609b3481L)emu.writeRegister("A0",0xa33f2c9cL);
      else if(target==0x609025aaL)suppress[0]++;
      else throw new Exception("Unexpected priority callee "+Long.toHexString(target));
     });
     boolean expected=(which==0?a:b)==0;
     require(suppress[0]==(expected?1:0),"Priority path consulted wrong state");
     results.add("PASS native priority branch: A="+a+", B="+b+", path="+which+", suppression calls="+suppress[0]);
    }finally{e.dispose();}
   }
   // The dirty accessor can refresh the shared structure; refresh itself is a recorded external model.
   for(int dirty=0;dirty<2;dirty++) {
    EmulatorHelper e=init();try {
     e.writeMemoryValue(toAddr(0xa33f2ceaL),1,dirty);final int[] refresh={0};
     execute(e,0x609b3bb2L,(emu,target)->{require(target==0x609b3c79L,"Unexpected accessor callee");refresh[0]++;});
     require(reg(e,"A0")==0xa33f2ce0L,"Accessor pointer mismatch");require(refresh[0]==dirty,"Dirty refresh mismatch");
     results.add("PASS native accessor: dirty="+dirty+", refresh calls="+refresh[0]);
    }finally{e.dispose();}
   }
   // Execute the refresh body with synthetic settings, including its normalization branches.
   for(int mode:new int[]{0,1,2,3,6}) {
    EmulatorHelper e=init();try {
     final int[] calls={0};
     int steps=execute(e,0x609b3c79L,(emu,target)->{
      if(target==0x609b3481L){emu.writeRegister("A0",0xa33f2c9cL);return;}
      require(target==0x60063380L,"Unexpected refresh callee "+Long.toHexString(target));
      long key=reg(emu,"D0"),idx=reg(emu,"D1");int value;
      if(key==0x9a41)value=7;
      else if(key==0x1dd1)value=idx==0?3:5;
      else if(key==0x84d1)value=mode;
      else if(key==0x88b2)value=0x123;
      else if(key==0x1df1)value=9;
      else if(key==0x1e01)value=11;
      else throw new Exception("Unexpected settings key "+Long.toHexString(key));
      emu.writeRegister("D0",value);calls[0]++;
     });
     byte[] expected={(byte)0x23,1,(byte)mode,7,3,0,5,0,9,11};
     if(mode==2){expected[0]=0x0e;expected[1]=2;}
     if(mode==0||mode==2||mode==3)expected[8]=0;
     require(calls[0]==7,"Refresh did not read seven settings values");
     require(Arrays.equals(expected,e.readMemory(toAddr(0xa33f2ce0L),10)),"Refresh field mapping/normalization mismatch for "+mode);
     results.add("PASS native target refresh: synthetic pattern value="+mode+", seven modeled setting reads, exact normalized 10-byte record; instructions="+steps);
    }finally{e.dispose();}
   }
   Files.write(out.resolve("native-contract-results.txt"),results);
   Files.writeString(out.resolve("native-contract-scope.txt"),results.size()+" bounded native instruction tests passed under the community MN10300 Sleigh model.\nExternal calls were modeled explicitly; call/return stack semantics and terminal returns were not tested.\nSynthetic target records/settings are not actual captured single-point/all-area configurations.\nRefresh tests cover context+0x22=0 only; orientation helper is not exercised.\nNo button event arbitration, UI, detector, AF timing, interrupts, lens or camera behavior was executed.\nThis validates selected data/control primitives, not a working firmware extension.\n");
   println("Bounded native contracts passed: "+results.size());
  }catch(Exception ex){Files.writeString(out.resolve("native-contract-failure.txt"),ex.toString()+"\n"+String.join("\n",results));throw ex;}
 }
}
