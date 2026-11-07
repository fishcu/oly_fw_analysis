// Resident prototype integration of disabled/idle stock fallbacks.
// Research only: enable/configuration source is supplied, not a camera UI adapter.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
public class OM3GuardedResident extends OM3GuardedAccessor {
 @Override byte[] absoluteData(byte[] bytes,long origin)throws Exception {
  // The accessor patch is one relative jump followed by unreachable stock
  // instruction fragments. It contains no extension-data absolute operand.
  if(origin==0x609b3bb2L){check(bytes.length==9&&(bytes[0]&255)==0xdc,"Accessor jump patch");return bytes.clone();}
  return super.absoluteData(bytes,origin);
 }
 byte[] gatedReconcile()throws Exception {
  Asm gate=new Asm();gate.x(0xfc,0xa9);gate.w(S+6);gate.x(0xa5,1);gate.eq("enabled");gate.x(0xdf,0,0);gate.label("enabled");
  byte[] prefix=gate.finish(),body=reconcile();
  // Internal branches retain their relative displacement. Calls keep their old
  // absolute target when the body moves by prefix.length.
  PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  for(int i=0;i<body.length;){PseudoInstruction ins=dis.disassemble(toAddr(RECONCILE+i),Arrays.copyOfRange(body,i,Math.min(i+16,body.length)));check(ins!=null,"Gate body decode");if((body[i]&255)==0xdd){long delta=0;for(int k=0;k<4;k++)delta|=(body[i+1+k]&255L)<<(8*k);put(body,i+1,(int)delta-prefix.length);}i+=ins.getLength();}
  byte[] result=Arrays.copyOf(prefix,prefix.length+body.length);System.arraycopy(body,0,result,prefix.length,body.length);return result;
 }
 @Override void profileInit(int scp,Path out)throws Exception {super.profileInit(scp,out);installGuarded(out);byteAt(S+6,0);}
 @Override void pack(Path out)throws Exception {
  List<byte[]> code=new ArrayList<>();List<Long> origins=new ArrayList<>();
  origins.add(CODE);code.add(controller());origins.add(RECONCILE);code.add(gatedReconcile());origins.add(CAPTURE);code.add(capture());origins.add(CODE+0x800);code.add(guardedMode());origins.add(ACCESSOR);code.add(guardedAccessor());
  for(int i=0;i<4;i++){long a=CODE+0x900+128*i;origins.add(a);code.add(wrapper(a,new long[]{HP,HR,AP,AR}[i],new long[]{0x610b9197L,0x610b96f0L,0x610b962aL,0x610b9653L}[i]));}
  blocks.clear();long p=DEST;for(int i=0;i<code.size();i++){blocks.add(new long[]{origins.get(i),p,code.get(i).length});p+=code.get(i).length;}packedSize=(int)(p-DEST);check(p<=0x60a8f800L,"Guarded code exceeds inspected extent: "+packedSize);
  byte[] original=new byte[packedSize];currentProgram.getMemory().getBytes(toAddr(DEST),original);for(byte v:original)check((v&255)==255,"Changed stock padding");
  for(int i=0;i<code.size();i++){long[] block=blocks.get(i);e.writeMemory(toAddr(block[1]),relocate(code.get(i),block[0],block[1]));}
  packedEntry=translated(RECONCILE);packedCapture=translated(CAPTURE);
  for(long[] hook:new long[][]{{0x603cedfeL,translated(CODE+0x800)},{0x609b3bb2L,translated(ACCESSOR)}}){Asm j=new Asm();j.x(0xdc);j.w(hook[1]-hook[0]);e.writeMemory(toAddr(hook[0]),j.finish());}
  decodeCache.clear();Files.write(out.resolve("guarded-packed-code.emulator-only.bin"),e.readMemory(toAddr(DEST),packedSize));
  List<String> map=new ArrayList<>();for(long[] block:blocks)map.add(String.format("%08x -> %08x length=%d",block[0],block[1],block[2]));Files.write(out.resolve("guarded-relocation-map.txt"),map);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary guarded resident mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  for(int scp=0;scp<=6;scp++){profileInit(scp,out);try{prepareResident(out);load(1,0xa5);load(4,0x55);
   byte[] state=e.readMemory(toAddr(DATA),24);e.writeRegister("D0",AP);runNative(packedEntry,0,0);check(Arrays.equals(state,e.readMemory(toAddr(DATA),24)),"Disabled reconcile mutated state");
   targetSettings(0);setting(0x88b2,0,100);byteAt(0xa33f2ceaL,1);runNative(0x609b3bb2L,0,4);check(reg("A0")==0xa33f2ce0L&&u16(reg("A0"))==100,"Disabled stock builder");
   byteAt(DATA+6,1);residentEvent(HP,scp,true,false);residentEvent(AP,scp,true,true);residentEvent(AR,scp,true,false);
   // Return idle to current stock configuration, not the synthetic held bank.
   e.writeRegister("D0",HR);runNative(packedEntry,0,0);check(u8(DATA+4)==0&&u16(0xa33ca384L)==100&&u8(0x62a6a0ebL)==scp,"Idle stock restoration");
   runNative(0x609b3bb2L,0,4);check(reg("A0")==0xa33f2ce0L,"Idle accessor ownership");
   results.add("PASS guarded resident SCP="+scp+": full native section reload, disabled event leaves state intact, stock dirty rebuild, three owned transitions, release to current stock frame 100; packed "+packedSize+" bytes; enable/orientation/configuration supplied");
   Files.write(out.resolve("guarded-resident-trace-"+scp+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("guarded-resident-results.txt"),results);println("GUARDED RESIDENT: "+results.size()+" PASS");
 }
}
