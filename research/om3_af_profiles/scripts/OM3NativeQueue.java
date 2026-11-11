// Native queue operations, GNU-referenced multiplication, explicit kernel lock model.
// @category OM3
import ghidra.app.util.PseudoInstruction;
import java.nio.file.*;
import java.util.*;
public class OM3NativeQueue extends OM3NativeFlow {
 long mulHigh;
 long u32(long p)throws Exception{byte[] b=e.readMemory(toAddr(p),4);return (b[0]&255L)|((b[1]&255L)<<8)|((b[2]&255L)<<16)|((b[3]&255L)<<24);}
 int u8(long p)throws Exception{return e.readMemory(toAddr(p),1)[0]&255;}
 @Override boolean instruction(PseudoInstruction ins)throws Exception{
  if(!ins.getMnemonicString().startsWith("udf"))return false;
  byte[] b=ins.getBytes();int op=b[0]&255,x=b[1]&255,n=x&3;long a,v;
  // GNU sim/mn10300/mn10300.igen: mulq/mulqu. Restricted to observed nonnegative inputs;
  // high result retained separately; reject instructions reading extension registers.
  boolean unsigned=ins.getMnemonicString().equals("udfu01")||ins.getMnemonicString().equals("udf01");
  boolean signed=ins.getMnemonicString().equals("udf00");
  check(unsigned||signed,"Unsupported extension "+ins);
  if(op==0xf6){a=reg("D"+((x>>2)&3));}
  else if(op==0xf9||op==0xfb||op==0xfd){a=0;for(int j=2;j<b.length;j++)a|=(b[j]&255L)<<((j-2)*8);if(signed){if(b.length==3)a=(byte)a;else if(b.length==4)a=(short)a;else a=(int)a;}}
  else throw new Exception("Unsupported multiplication encoding "+ins);
  v=reg("D"+n);if(signed)v=(int)v;
  check(a>=0&&v>=0&&a<=0x7fffffffL&&v<=0x7fffffffL,"Multiply scope exceeded");
  long product=a*v;mulHigh=product>>>32;long low=product&0xffffffffL;
  e.writeRegister("D"+n,low);e.writeRegister("ZF",low==0?1:0);e.writeRegister("NF",(low>>>31)&1);e.writeRegister("CF",0);e.writeRegister("VF",0);
  trace.add("GNU-multiply:"+ins.getAddress()+":"+a+"*"+v+"="+product);e.writeRegister("PC",ins.getAddress().getOffset()+ins.getLength());return true;
 }
 @Override boolean external(long t)throws Exception{
  if(t==0x60075f73L){trace.add("kernel-lock:"+reg("D0"));e.writeRegister("D0",0x1234);return true;}
  if(t==0x60075fbcL){trace.add("kernel-unlock");return true;}
  return super.external(t);
 }
 void queueInit()throws Exception{
  init();trace.clear();e.writeMemoryValue(toAddr(0xa337174cL),4,0);e.writeMemory(toAddr(0x62f757c8L),new byte[0x1010]);
  for(int cpu=0;cpu<2;cpu++){long header=0x62f757c8L+cpu*12,base=0x62f757e0L+cpu*0x7c0;e.writeMemoryValue(toAddr(header),4,base);e.writeMemoryValue(toAddr(header+4),4,base);}
 }
 void enqueue(int cpu,byte[] record)throws Exception{e.writeMemory(toAddr(0x700a0000L),record);e.writeRegister("A0",0x700a0000L);e.writeRegister("D0",cpu);e.writeRegister("D1",0);runNative(0x6084dc38L,0xf0,0x34);check(reg("D0")==0,"Enqueue status");}
 byte[] pop(int cpu)throws Exception{e.writeRegister("A0",0x700a1000L);e.writeRegister("D0",cpu);e.writeRegister("D1",0);runNative(0x6084e2acL,0xf0,0x34);check(reg("D0")==0,"Pop status");return e.readMemory(toAddr(0x700a1000L),124);}
 void consume(int cpu)throws Exception{e.writeRegister("D0",cpu);e.writeRegister("D1",0);runNative(0x6084df70L,0xf0,0x38);check(reg("D0")==0,"Consume status");}
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  try{
   for(int cpu=0;cpu<2;cpu++){queueInit();try{
    for(int round=0;round<3;round++){
     List<byte[]> records=new ArrayList<>();for(int i=0;i<16;i++){byte[] b=new byte[124];new Random(1000+round*16+i).nextBytes(b);b[0]=(byte)(1+i%3);records.add(b);enqueue(cpu,b);check(u32(0x62f757d0L+12*cpu)==i+1,"Queue count after enqueue");}
     for(int i=0;i<16;i++){check(Arrays.equals(pop(cpu),records.get(i)),"Queue record corruption/order");consume(cpu);check(u32(0x62f757d0L+12*cpu)==15-i,"Queue count after consume");}
     results.add("PASS native 16-entry FIFO and pointer wrap, queue="+cpu+", round="+round+"; full 124-byte payloads verified");
    }
    Files.write(out.resolve("native-queue-trace-"+cpu+".txt"),trace);
   }finally{e.dispose();}}
   Files.write(out.resolve("native-queue-results.txt"),results);println("NATIVE QUEUE: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("native-queue-results.txt"),results);Files.write(out.resolve("native-queue-last-trace.txt"),trace);Files.writeString(out.resolve("native-queue-failure.txt"),ex.toString());throw ex;}
 }
}
