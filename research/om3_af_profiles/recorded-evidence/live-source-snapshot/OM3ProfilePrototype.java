// Offline integration prototype. Synthetic geometry profiles; no firmware patch.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;

public class OM3ProfilePrototype extends GhidraScript {
 interface Model {void call(EmulatorHelper e,long target)throws Exception;}
 void check(boolean b,String s)throws Exception{if(!b)throw new Exception(s);}
 long reg(EmulatorHelper e,String r){return e.readRegister(r).longValue()&0xffffffffL;}
 EmulatorHelper init(){
  EmulatorHelper e=new EmulatorHelper(currentProgram);
  for(String r:new String[]{"D0","D1","D2","D3","A0","A1","A2","A3","MDR","PSW"})e.writeRegister(r,0);
  e.writeRegister("SP",0x70010000L);e.writeMemory(toAddr(0x7000f000L),new byte[0x3000]);return e;
 }
 Model noCalls=(e,t)->{throw new Exception("Unexpected call "+Long.toHexString(t));};
 void execute(EmulatorHelper e,long entry,Set<Long> stops,Model model)throws Exception{
  e.writeRegister("PC",entry);PseudoDisassembler dis=new PseudoDisassembler(currentProgram);
  for(int i=0;i<2000;i++){
   long pc=e.getExecutionAddress().getOffset();if(stops.contains(pc))return;
   PseudoInstruction ins=dis.disassemble(toAddr(pc));check(ins!=null,"Decode failure");
   if(ins.getFlowType().isCall()){
    check(ins.getFlows().length==1,"Indirect call requires a model");model.call(e,ins.getFlows()[0].getOffset());
    e.writeRegister("PC",pc+ins.getLength());
   }else if(ins.getFlowType().isTerminal())return;
   else check(e.step(monitor),"Native instruction failure at "+Long.toHexString(pc)+": "+e.getLastError());
  }throw new Exception("Instruction limit");
 }
 void half(EmulatorHelper e,long a,int value){e.writeMemoryValue(toAddr(a),2,value);}
 int half(EmulatorHelper e,long a)throws Exception{byte[] b=e.readMemory(toAddr(a),2);return (b[0]&255)|((b[1]&255)<<8);}
 public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();List<String> trace=new ArrayList<>();
  try{
   int[] ids={40,85,163,1657,1658,1675,1683,1712,1803,2154,2155,2156,2157};
   int[] keys={0x84d1,0x88b2,0x99a1,0x1dd1,0x1dd1,0x1df1,0x1e01,0x1e71,0x9a41,0x90a1,0x90a1,0x90b1,0x90b1};
   int[] indexes={0,0,0,0,1,0,0,0,0,0,1,0,1};
   for(int i=0;i<ids.length;i++){
    EmulatorHelper e=init();try{
     e.writeMemoryValue(toAddr(0x8050),4,0);e.writeMemoryValue(toAddr(0xa31f4d28L),4,0);
     e.writeMemoryValue(toAddr(0xa31f203cL+4L*ids[i]),4,0);e.writeMemory(toAddr(0x70020000L),new byte[4]);
     e.writeRegister("A0",0x70020000L);e.writeRegister("D0",ids[i]);execute(e,0x60419446L,Set.of(),noCalls);
     check(reg(e,"D0")==keys[i],"GUI key map mismatch for "+ids[i]);
     e.writeRegister("D0",ids[i]);execute(e,0x60419696L,Set.of(),noCalls);
     check(reg(e,"D0")==indexes[i],"GUI array index mismatch");
     results.add("PASS native GUI mapping: id="+ids[i]+", key="+Integer.toHexString(keys[i])+", index="+indexes[i]+"; lazy cache population disabled");
    }finally{e.dispose();}
   }
   for(int assigned:new int[]{0,1}){
    EmulatorHelper e=init();try{
     e.writeMemoryValue(toAddr(0x6036ee34L),4,0);e.writeRegister("A1",0x70040000L);
     final int[] starts={0};List<String> order=new ArrayList<>();
     execute(e,0x610b962aL,Set.of(),(em,t)->{
      if(t==0x610b9828L){check(reg(em,"D0")==1,"Press held flag");execute(em,t,Set.of(),noCalls);order.add("held=1");}
      else if(t==0x6108ad0aL){check(reg(em,"D0")==11,"Assignment query");em.writeRegister("D0",assigned);order.add("assignment query");}
      else if(t==0x610a5620L){check(half(em,0x6036ee34L)==1,"Start ran before held update");starts[0]++;order.add("AF start policy");}
      else throw new Exception("Unexpected press callee "+Long.toHexString(t));
     });
     check(starts[0]==assigned,"Assignment gate ignored");results.add("PASS native shooting AF-ON press: assignment result="+assigned+", start calls="+starts[0]);trace.add("Press: "+order);
    }finally{e.dispose();}
   }
   EmulatorHelper e=init();try{
    e.writeMemoryValue(toAddr(0x6036ee34L),4,1);e.writeMemory(toAddr(0x70040000L),new byte[0x140]);
    e.writeRegister("A1",0x70040000L);List<String> order=new ArrayList<>();
    execute(e,0x610b9653L,Set.of(),(em,t)->{
     if(t==0x610a58c7L){check(half(em,0x6036ee34L)==1,"Release policy expected old held flag");order.add("AF release policy while held=1");}
     else if(t==0x610b9828L){check(reg(em,"D0")==0,"Release flag");execute(em,t,Set.of(),noCalls);order.add("held=0");}
     else if(t==0x61090e0aL){check(half(em,0x6036ee34L)==0,"Post-release order");order.add("state event 9");}
     else throw new Exception("Unexpected release callee "+Long.toHexString(t));
    });check(order.size()==3,"Release sequence incomplete");results.add("PASS native AF-ON release: release policy precedes held-flag clear, then state event 9");trace.add("Release: "+order);
   }finally{e.dispose();}
   // Integration: native target copy -> native grid rectangle -> native first candidate gate.
   // Profile choice and accessor return pointer are explicit test inputs, not button hooks.
   for(int wide:new int[]{0,1}){
    e=init();try{
     long source=0x70050000L,cache=0xa33ca384L,p=0x70060000L;
     e.writeMemory(toAddr(source),new byte[10]);half(e,source,526);
     e.writeMemoryValue(toAddr(source+2),1,3);half(e,source+4,wide==1?27:1);half(e,source+6,wide==1?39:1);
     e.writeMemory(toAddr(cache),new byte[10]);e.writeRegister("A0",cache);
     execute(e,0x60903e55L,Set.of(),(em,t)->{check(t==0x609b3bb2L,"Copy accessor");em.writeRegister("A0",source);});
     check(Arrays.equals(e.readMemory(toAddr(source),10),e.readMemory(toAddr(cache),10)),"Integration copy mismatch");
     e.writeMemory(toAddr(p),new byte[8]);e.writeRegister("A0",p);e.writeRegister("A1",p+2);e.writeRegister("D0",p+4);e.writeRegister("D1",p+6);
     execute(e,0x609dc311L,Set.of(),(em,t)->{check(t==0x60902c64L,"Grid accessor");em.writeRegister("A0",cache);});
     int x0=half(e,p),y0=half(e,p+2),x1=half(e,p+4),y1=half(e,p+6);
     if(wide==1)check(x0==0&&y0==0&&x1==639&&y1==479,"Wide rectangle bounds");
     else check(x0>0&&y0>0&&x1<500&&y1>120,"Narrow rectangle bounds");
     half(e,0xa33ac494L,x0);half(e,0xa33ac496L,y0);half(e,0xa33ac498L,x1);half(e,0xa33ac49aL,y1);
     half(e,0x70010052L,520);half(e,0x70010054L,500);half(e,0x70010050L,100);
     e.writeMemoryValue(toAddr(0x7001001cL),4,255);e.writeRegister("D1",120);
     execute(e,0x6086c089L,Set.of(0x6086c0ffL,0x6086c31aL),noCalls);
     check(e.getExecutionAddress().getOffset()==(wide==1?0x6086c0ffL:0x6086c31aL),"Integration candidate gate");
     results.add("PASS native profile integration: "+(wide==1?"wide":"narrow")+" synthetic geometry -> cache -> rectangle ["+x0+","+y0+","+x1+","+y1+"] -> off-center candidate first gate "+(wide==1?"passes":"fails"));
    }finally{e.dispose();}
   }
   Files.write(out.resolve("profile-prototype-results.txt"),results);Files.write(out.resolve("shooting-event-order.txt"),trace);
   Files.writeString(out.resolve("profile-prototype-scope.txt"),"Offline integration prototype only. Community MN10300 Sleigh; external calls modeled; terminal returns and call/return stack semantics excluded.\nGUI key/index mapping executes natively with lazy cache initialization disabled. Labels are associated separately through the resource name inventory.\nShooting tests execute press/release handlers with assignment and AF operation callees modeled; special release UI state 0x900002b excluded.\nWide/narrow records are synthetic grid fixtures, not captured stock All/Single configurations. Selection-rectangle publication between geometry output and candidate gate is modeled.\nNo physical button-to-worker sequence, full subject selection, concurrent snapshot publication, lens, camera, installation or firmware patch is implemented.\n");
   Files.deleteIfExists(out.resolve("profile-prototype-failure.txt"));println("Profile prototype tests passed: "+results.size());
  }catch(Exception ex){Files.writeString(out.resolve("profile-prototype-failure.txt"),ex+"\n"+String.join("\n",results));throw ex;}
 }
}
