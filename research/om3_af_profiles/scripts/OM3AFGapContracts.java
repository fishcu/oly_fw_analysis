// Native instruction fragments with explicit external models; no camera access.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.app.emulator.EmulatorHelper;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;

public class OM3AFGapContracts extends GhidraScript {
 interface Model {void call(EmulatorHelper e,long target) throws Exception;}
 long reg(EmulatorHelper e,String name){return e.readRegister(name).longValue()&0xffffffffL;}
 void check(boolean yes,String message)throws Exception{if(!yes)throw new Exception(message);}
 EmulatorHelper init(){
  EmulatorHelper e=new EmulatorHelper(currentProgram);
  for(String r:new String[]{"D0","D1","D2","D3","A0","A1","A2","A3","MDR","PSW"})e.writeRegister(r,0);
  e.writeRegister("SP",0x70010000L);e.writeMemory(toAddr(0x7000f000L),new byte[0x3000]);return e;
 }
 int runNative(EmulatorHelper e,long entry,Set<Long> stops,Model model)throws Exception{
  e.writeRegister("PC",entry);PseudoDisassembler dis=new PseudoDisassembler(currentProgram);
  for(int n=0;n<2000;n++){
   long pc=e.getExecutionAddress().getOffset();if(stops.contains(pc))return n;
   PseudoInstruction ins=dis.disassemble(toAddr(pc));check(ins!=null,"Decode failed");
   if(ins.getFlowType().isCall()){
    check(ins.getFlows().length==1,"Unmodeled indirect call");model.call(e,ins.getFlows()[0].getOffset());
    e.writeRegister("PC",pc+ins.getLength());
   }else if(ins.getFlowType().isTerminal())return n;
   else check(e.step(monitor),"Native instruction failed at "+Long.toHexString(pc)+": "+e.getLastError());
  }throw new Exception("Instruction limit");
 }
 Model noCalls=(e,t)->{throw new Exception("Unexpected call "+Long.toHexString(t));};
 void word(EmulatorHelper e,long a,int value){e.writeMemoryValue(toAddr(a),2,value);}
 int half(EmulatorHelper e,long a)throws Exception{byte[] b=e.readMemory(toAddr(a),2);return (b[0]&255)|((b[1]&255)<<8);}
 public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  try{
   // Actual no-call full-frame builder: output pointers occupy A0,A1,D0,D1.
   EmulatorHelper e=init();try{
    long p=0x70020000L;e.writeMemory(toAddr(p),new byte[8]);
    e.writeRegister("A0",p);e.writeRegister("A1",p+2);e.writeRegister("D0",p+4);e.writeRegister("D1",p+6);
    runNative(e,0x609dc2eaL,Set.of(),noCalls);
    check(half(e,p)==0&&half(e,p+2)==0&&half(e,p+4)==639&&half(e,p+6)==479,"Full-frame bounds mismatch");
    results.add("PASS full-frame builder: native table values produce xmin=0,ymin=0,xmax=639,ymax=479");
   }finally{e.dispose();}
   for(int aspect:new int[]{0,5}){
    e=init();try{
     long p=0x70020000L;e.writeMemory(toAddr(p),new byte[8]);e.writeRegister("A0",p);
     runNative(e,0x609dc3c3L,Set.of(),(em,t)->{check(t==0x60063380L&&reg(em,"D0")==0x85b1,"Aspect getter mismatch");em.writeRegister("D0",aspect);});
     check(half(e,p)==0&&half(e,p+2)==639&&half(e,p+4)==(aspect==5?36:0)&&half(e,p+6)==(aspect==5?443:479),"Aspect rectangle mismatch");
     results.add("PASS aspect rectangle: modeled setting 0x85b1="+aspect+", native rectangle values verified");
    }finally{e.dispose();}
   }
   // First candidate/selection rectangle overlap gate only, not complete acquisition.
   for(int fixture=0;fixture<3;fixture++){
    e=init();try{
     long p=0xa33ac494L;int[] rect=fixture==0?new int[]{0,0,639,479}:new int[]{300,200,340,240};
     for(int i=0;i<4;i++)word(e,p+2*i,rect[i]);
     int x=fixture==2?310:500,y=fixture==2?210:100;
     word(e,0x70010052L,x+20);word(e,0x70010054L,x);word(e,0x70010050L,y);
     e.writeRegister("D1",y+20);e.writeMemoryValue(toAddr(0x7001001cL),4,255);
     runNative(e,0x6086c089L,Set.of(0x6086c0ffL,0x6086c31aL),noCalls);
     boolean pass=fixture!=1;check(e.getExecutionAddress().getOffset()==(pass?0x6086c0ffL:0x6086c31aL),"Candidate rectangle gate mismatch");
     results.add("PASS candidate rectangle gate: fixture="+fixture+", pass first region gate="+pass+"; later selection gates excluded");
    }finally{e.dispose();}
   }
   // A real UI helper maps a Boolean to two command identifiers.
   for(int flag:new int[]{0,1}){
    e=init();try{
     final int[] calls={0};e.writeRegister("D0",flag);
     runNative(e,0x60b19a24L,Set.of(),(em,t)->{
      check(t==0x60421572L,"Unexpected UI callee");
      check(reg(em,"D0")== (flag==0?0x41b0038L:0x41b0062L),"UI command mapping mismatch");
      check(reg(em,"D1")==0xffffffffL&&reg(em,"A0")==0,"UI command argument mismatch");calls[0]++;
     });check(calls[0]==1,"UI dispatch count");results.add("PASS native UI helper: flag="+flag+", command="+(flag==0?"0x41b0038":"0x41b0062"));
    }finally{e.dispose();}
   }
   // Execute the native 50-byte configuration latch, including its hardware loop.
   e=init();try{
    byte[] record=new byte[50];for(int i=0;i<50;i++)record[i]=(byte)(i+21);
    e.writeMemory(toAddr(0x7001001cL),record);byte[] guard=new byte[58];Arrays.fill(guard,(byte)0xa5);
    e.writeMemory(toAddr(0xa33ac49aL),guard);
    runNative(e,0x60871b50L,Set.of(0x60871b66L),noCalls);
    byte[] actual=e.readMemory(toAddr(0xa33ac49aL),58);
    check(Arrays.equals(record,Arrays.copyOfRange(actual,4,54)),"Configuration latch content mismatch");
    for(int i:new int[]{0,1,2,3,54,55,56,57})check(actual[i]==(byte)0xa5,"Configuration latch guard changed");
    results.add("PASS native configuration latch: 50 bytes copied exactly to 0xa33ac49e; surrounding guards intact");
   }finally{e.dispose();}
   int[] messages={0x100,0x101,0x300,0x301};long[] entries={0x609df95bL,0x609df9c1L,0x609dfa0eL,0x609dfa29L};
   Set<Long> dispatcherStops=Set.of(entries[0],entries[1],entries[2],entries[3]);
   for(int i=0;i<messages.length;i++){
    e=init();try{
     e.writeMemoryValue(toAddr(0x7001000cL),4,messages[i]);e.writeRegister("A3",0x60a83454L);
     runNative(e,0x609df899L,dispatcherStops,noCalls);
     check(e.getExecutionAddress().getOffset()==entries[i],"Worker dispatcher mismatch");
     results.add("PASS native worker lookup: message="+Integer.toHexString(messages[i])+", dispatch="+Long.toHexString(entries[i]));
    }finally{e.dispose();}
   }
   int[] ids={1,4,9};long[] starts={0x60134000L,0x60828000L,0x61809000L},ends={0x6031f000L,0x60a8f800L,0x619a9800L};
   for(int i=0;i<ids.length;i++){
    int sid=ids[i];long start=starts[i],end=ends[i];
    e=init();try{
     e.writeRegister("D0",sid);runNative(e,0x60045e6cL,Set.of(),noCalls);
     check(reg(e,"D0")==end,"Section end mismatch");results.add("PASS native section end selector: section="+sid+", end="+Long.toHexString(end));
    }finally{e.dispose();}
    e=init();try{
     byte[] content=new byte[(int)(end-start)];currentProgram.getMemory().getBytes(toAddr(start),content);
     for(int j=0;j<16;j++){check(content[content.length-16+j]==(byte)255,"Tail not FF");content[content.length-16+j]=(byte)(0x30+j);}
     final int[] reads={0};e.writeMemoryValue(toAddr(0xa32de590L),4,0);
     e.writeRegister("A2",(sid-1)*12);e.writeRegister("A3",sid);e.writeRegister("D3",sid-1);e.writeRegister("D2",end);
     // Enter after the opaque descriptor-index UDF. Index and end are explicit fixtures.
     runNative(e,0x60045ee7L,Set.of(),(em,t)->{
      if(t==0x60070fd4L){check(reg(em,"D0")==start,"Alias input");em.writeRegister("D0",start+0x40000000L);}
      else if(t==0x600232d1L){
       check(reg(em,"A0")==start+0x40000000L&&reg(em,"A1")==start-0x10021000L,"Load addresses");
       check(reg(em,"D0")==content.length&&reg(em,"D1")==0x10200,"Load length/flags");
       em.writeMemory(toAddr(start+0x40000000L),content);em.writeRegister("D0",0);reads[0]++;
      }else throw new Exception("Unexpected loader callee "+Long.toHexString(t));
     });
     check(reads[0]==1,"Expected one storage request");
     check(Arrays.equals(Arrays.copyOfRange(content,content.length-16,content.length),e.readMemory(toAddr(end+0x40000000L-16),16)),"Tail marker lost");
     byte[] bits=e.readMemory(toAddr(0xa32de590L),4);long mask=0;for(int j=0;j<4;j++)mask|=(long)(bits[j]&255)<<(8*j);
     check(mask==(1L<<(sid-1)),"Loaded bit mismatch");
     results.add("PASS partial native section loader: section="+sid+", exact request, modeled successful storage preserves changed tail and sets loaded bit");
    }finally{e.dispose();}
   }
   for(int fixture=0;fixture<5;fixture++){
    e=init();try{
     long p=0x70030000L,desc=0x70031000L;byte[] image=new byte[80],header=new byte[32];
     try(java.io.InputStream input=Files.newInputStream(out.resolve("../../firmware/catalog/OLY_E_147_1100_0000_0000.BIN").normalize())){header=input.readNBytes(32);}
     System.arraycopy(header,0,image,0,32);image[12]=16;image[13]=image[14]=image[15]=0;
     System.arraycopy(image,0,image,48,32);for(int i=0;i<16;i++)image[32+i]=(byte)i;
     if(fixture==1)image[32]^=1; // Changed contents with a newly repaired checksum.
     long sum=0;for(int i=0;i<80;i+=4)for(int j=0;j<4;j++)sum+=(long)(image[i+j]&255)<<(8*j);
     long checksum=(-sum)&0xffffffffL;for(int j=0;j<4;j++)image[76+j]=(byte)(checksum>>(8*j));
     if(fixture==2)image[32]^=1; // Same edit without checksum repair.
     if(fixture==3)image[48]^=1; // Header/trailer mismatch.
     e.writeMemory(toAddr(p),image);e.writeMemory(toAddr(desc),new byte[32]);
     e.writeMemoryValue(toAddr(desc+4),4,p);e.writeMemoryValue(toAddr(desc+16),4,fixture==4?2:1);
     e.writeRegister("A0",desc);e.writeRegister("D0",0);
     runNative(e,0x6106b712L,Set.of(),(em,t)->{
      if(t==0x6015584eL||t==0x60155827L)runNative(em,t,Set.of(),noCalls);
      else if(t==0x60155816L){long savedD2=reg(em,"D2");runNative(em,t,Set.of(),noCalls);em.writeRegister("D2",savedD2);}
      else check(t==0x60023f59L,"Unexpected validator callee "+Long.toHexString(t)); // Diagnostic output only.
     });
     long expected=new long[]{0,0,0x3211,0x3202,0x3204}[fixture];
     check(reg(e,"D0")==expected,"Validator fixture "+fixture+" returned "+Long.toHexString(reg(e,"D0")));
     results.add("PASS native application component validator + native additive checksum: fixture="+fixture+", result="+Long.toHexString(expected));
    }finally{e.dispose();}
   }
   for(int size:new int[]{80,64,79}){
    e=init();try{
     long p=0x70030000L;byte[] input=new byte[80];for(int i=0;i<80;i++)input[i]=(byte)i;
     e.writeMemory(toAddr(p),input);e.writeRegister("A0",p);e.writeRegister("D0",size);
     runNative(e,0x6106b7dbL,Set.of(),noCalls);
     if(size==80){
      int[] order={1,3,0,2,6,4,7,5,11,10,9,8,13,14,12,15};byte[] actual=e.readMemory(toAddr(p),80);
      for(int i=0;i<80;i++)check(actual[i]==(i>=32&&i<48?(byte)~input[32+order[i-32]]:input[i]),"Native descrambler mismatch");
      check(reg(e,"D0")==0,"Descrambler status");
     }else{check(reg(e,"D0")==0x3201,"Malformed size accepted");check(Arrays.equals(input,e.readMemory(toAddr(p),80)),"Malformed size wrote memory");}
     results.add("PASS native update descrambler: size="+size+", "+(size==80?"exact permutation/inversion; header/trailer preserved":"rejected without buffer changes"));
    }finally{e.dispose();}
   }
   Files.write(out.resolve("gap-native-results.txt"),results);
   Files.deleteIfExists(out.resolve("gap-native-failure.txt"));
   Files.writeString(out.resolve("gap-native-scope.txt"),"Native fragments executed with community MN10300 Sleigh. External callees modeled and terminal returns excluded.\nCandidate tests stop after the first rectangle overlap gate, before later candidate policy.\nUI helper/dispatcher tests do not establish physical button ownership or worker scheduling.\nSection loader tests enter after opaque descriptor-index UDF with explicit index/end fixtures; alias and successful storage read are modeled.\nApplication validator tests use an 80-byte synthetic component and descriptor mode 1, plus invalid mode 2. Checksum and header helpers execute natively; diagnostic output is modeled. Saved D2 postcondition is explicit, not an executed call/return frame.\nDescrambler tests use an 80-byte fixture and two malformed sizes. No whole update chain, flash writer, boot authentication, recovery, cache coherence, real AF, lens, interrupts, orientation helper or camera was executed.\n");
   println("AF gap native tests passed: "+results.size());
  }catch(Exception ex){Files.writeString(out.resolve("gap-native-failure.txt"),ex+"\n"+String.join("\n",results));throw ex;}
 }
}
