// Execute a compact relocated copy in emulator memory over original FF padding.
// Padding is NOT established to be available at camera runtime. No file writes.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
public class OM3PackedRelocation extends OM3RevisionCoverage {
 static final long DEST=0x60a8f088L;List<long[]> blocks=new ArrayList<>();long packedEntry,packedCapture;int packedSize;
 long translated(long p){for(long[] b:blocks)if(p>=b[0]&&p<b[0]+b[2])return b[1]+p-b[0];return p;}
 byte[] relocate(byte[] src,long from,long to)throws Exception{
  byte[] result=src.clone();PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  for(int offset=0;offset<src.length;){PseudoInstruction ins=dis.disassemble(toAddr(from+offset),Arrays.copyOfRange(src,offset,Math.min(src.length,offset+16)));check(ins!=null,"Relocation decode");
   if((src[offset]&255)==0xdd||(src[offset]&255)==0xdc){long delta=0;for(int i=0;i<4;i++)delta|=(long)(src[offset+1+i]&255)<<(8*i);long target=(from+offset+(int)delta)&0xffffffffL;long next=translated(target)-(to+offset);for(int i=0;i<4;i++)result[offset+1+i]=(byte)(next>>>(8*i));}
   offset+=ins.getLength();check(offset<=src.length,"Relocation split instruction");}
  return result;
 }
 void pack(Path out)throws Exception{
  List<byte[]> code=new ArrayList<>();List<Long> origins=new ArrayList<>();origins.add(CODE);code.add(controller());origins.add(RECONCILE);code.add(reconcile());origins.add(CAPTURE);code.add(capture());origins.add(CODE+0x800);code.add(e.readMemory(toAddr(CODE+0x800),28));
  for(int i=0;i<4;i++){long a=CODE+0x900+128*i;origins.add(a);code.add(wrapper(a,new long[]{HP,HR,AP,AR}[i],new long[]{0x610b9197L,0x610b96f0L,0x610b962aL,0x610b9653L}[i]));}
  blocks.clear();long p=DEST;for(int i=0;i<code.size();i++){blocks.add(new long[]{origins.get(i),p,code.get(i).length});p+=code.get(i).length;}packedSize=(int)(p-DEST);check(p<=0x60a8f800L,"Packed code exceeds examined padding");byte[] original=new byte[packedSize];currentProgram.getMemory().getBytes(toAddr(DEST),original);for(byte v:original)check((v&255)==255,"Destination is not original FF padding");
  for(int i=0;i<code.size();i++){long[] b=blocks.get(i);e.writeMemory(toAddr(b[1]),relocate(code.get(i),b[0],b[1]));}
  packedEntry=translated(RECONCILE);packedCapture=translated(CAPTURE);long guard=translated(CODE+0x800);byte[] jump=new byte[5];jump[0]=(byte)0xdc;long delta=guard-0x603cedfeL;for(int i=0;i<4;i++)jump[1+i]=(byte)(delta>>>(8*i));e.writeMemory(toAddr(0x603cedfeL),jump);decodeCache.clear();
  Files.write(out.resolve("packed-code.emulator-only.bin"),e.readMemory(toAddr(DEST),packedSize));List<String> map=new ArrayList<>();for(long[] b:blocks)map.add(String.format("%08x -> %08x length=%d",b[0],b[1],b[2]));Files.write(out.resolve("packed-relocation-map.txt"),map);
 }
 @Override long eventEntry(){return packedEntry;}
 @Override void revisedEvent(long ev)throws Exception{e.writeRegister("D0",ev);runNative(packedEntry,0,0);}
 @Override void captureStock(int button,int orientation)throws Exception{e.writeRegister("D0",button);e.writeRegister("D1",orientation);runNative(packedCapture,0,0);check(reg("D0")==0,"Packed capture");}
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary relocation source mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  for(int mode=0;mode<=6;mode++){profileInit(mode,out);try{pack(out);event(HP,mode,true,false);event(AP,mode,true,true);for(int requested=0;requested<=6;requested++){e.writeRegister("D0",requested);runNative(0x603cedfeL,0xc0,0x10);check(u8(0x62a6a0ebL)==0,"Packed guard");}event(AR,mode,true,false);event(HR,mode,false,false);
   targetSettings(0);setting(0x88b2,0,100);captureStock(0,2);byteAt(S+16,2);revisedEvent(HP);check(u16(0xa33ca384L)==100&&u8(S+5)==0,"Packed orientation capture/activation");
   results.add("PASS relocated compact controller/reconcile/capture/guard, class="+mode+", native lifecycle, bypass/restoration and moved orientation bank; packed code="+packedSize+" bytes in emulator-only FF-padding overlay");
   Files.write(out.resolve("packed-trace-"+mode+".txt"),trace);
  }finally{e.dispose();}}
  profileInit(6,out);try{pack(out);revisedEvent(0);String[] regs={"D0","D1","D2","D3","A0","A1","A2","A3"};long[] originals={0x610b9197L,0x610b96f0L,0x610b962aL,0x610b9653L};for(int i=0;i<4;i++){
   for(int j=0;j<regs.length;j++)e.writeRegister(regs[j],0x71000000L+j*0x101);breakpoints.add(originals[i]);hitBreakpoint=0;try{runNative(translated(CODE+0x900+128*i),0,0);}finally{breakpoints.clear();}check(hitBreakpoint==originals[i]&&reg("SP")==stackTop,"Packed wrapper continuation");for(int j=0;j<regs.length;j++)check(reg(regs[j])==0x71000000L+j*0x101,"Packed wrapper register restoration");results.add("PASS relocated wrapper="+i+" reaches original handler with all eight general registers and SP restored; original handler body excluded");
  }}finally{e.dispose();}
  Files.write(out.resolve("packed-relocation-results.txt"),results);println("PACKED RELOCATION: "+results.size()+" PASS");
 }
}
