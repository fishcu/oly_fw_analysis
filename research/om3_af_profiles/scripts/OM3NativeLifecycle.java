// Original submit/callback/FIFO/worker paths with a deterministic kernel scheduler model.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.program.model.lang.Register;
public class OM3NativeLifecycle extends OM3NativeQueue {
 List<long[]> callbacks=new ArrayList<>();Map<Long,Long> events=new HashMap<>();boolean worker=false;int depth=0;
 static class Yield extends Exception {}
 void child(long entry,long a0)throws Exception{
  Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();for(Register r:currentProgram.getLanguage().getRegisters())if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
  long oldTop=stackTop;stackTop=0x70060000L-depth*0x10000;depth++;
  try{e.writeRegister("A0",a0);runNative(entry,0,0);}catch(Yield y){check(worker,"Unexpected yield");}
  finally{depth--;stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
 }
 void drain()throws Exception{
  while(!callbacks.isEmpty()){long[] c=callbacks.remove(0);check(c[0]==0x608418feL,"Unexpected callback");trace.add("scheduler-deliver:"+Long.toHexString(c[0]));child(c[0],c[1]);}
  worker=true;try{child(0x60841a6bL,0);}finally{worker=false;}
 }
 @Override boolean external(long t)throws Exception{
  if(t==0x50002a15L){int n=(int)reg("D1");check(n>=0&&n<=0x10000,"Memset bound");byte[] b=new byte[n];Arrays.fill(b,(byte)reg("D0"));e.writeMemory(toAddr(reg("A0")),b);e.writeRegister("A0",reg("A0"));return true;}
  if(t==0x60023c05L){e.writeRegister("D0",100);return true;}
  if(t==0x60072c53L){check(reg("A0")==0x6082e204L,"Unexpected device callback");trace.add("device-dispatch-model:6082e204");child(0x6082e204L,0);return true;}
  if(t==0x60081d1dL||t==0x60081d27L||t==0x6007f883L){trace.add("device-critical-or-delay-model:"+Long.toHexString(t));return true;}
  if(t==0x60056edeL){callbacks.add(new long[]{reg("A0"),reg("A1")});trace.add("scheduler-queue:"+Long.toHexString(reg("A0")));e.writeRegister("D0",0);return true;}
  if(t==0x608909a5L){long id=reg("D0"),bits=reg("D1");events.put(id,events.getOrDefault(id,0L)|bits);trace.add("signal:"+id+":"+bits+":workerState="+u8(0xa33a1d10L));return true;}
  if(t==0x60890a0dL){long id=reg("D0"),bits=reg("D1"),p=reg("A0");if(!worker)drain();long got=events.getOrDefault(id,0L)&bits;if(got==0&&worker&&bits==1&&u32(0x62f757d0L)==0)throw new Yield();check(got!=0,"Completion wait without signal id="+id+" bits="+bits);events.put(id,events.getOrDefault(id,0L)&~got);if(p!=0)e.writeMemoryValue(toAddr(p),4,got);e.writeRegister("D0",0);trace.add("wait-satisfied:"+id+":"+got);return true;}
  if(t==0x60063356L){check(reg("D0")==0x194,"Unexpected setting metadata");e.writeRegister("A0",0x700b0000L);return true;}
  return super.external(t);
 }
 void lifecycleInit()throws Exception{
  queueInit();callbacks.clear();events.clear();worker=false;depth=0;
  e.writeMemory(toAddr(0xa33a1c00L),new byte[0xb000]);e.writeMemoryValue(toAddr(0xa33a2d5cL),4,0x20201222);e.writeMemory(toAddr(0x62f76760L),new byte[0x5100]);
  for(int i=0;i<5;i++)setting(0x194,i,0);
 }
 void start(int mode)throws Exception{e.writeRegister("D0",mode);e.writeRegister("A0",0);runNative(0x608401afL,0xe0,0xa4);check(u8(0xa33a1d10L)==1&&u8(0xa33a1d14L)==mode,"Native start state/class");}
 void stop()throws Exception{e.writeRegister("D0",0);e.writeRegister("A0",0);runNative(0x608402adL,0xa0,0xa0);check(u8(0xa33a1d10L)==0,"Native stop state");}
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  try{for(int mode=1;mode<=6;mode++){lifecycleInit();try{
   start(mode);stop();start(mode);
   long[][] buffers={{0xa33a3010L,0x3fc},{0x62f8d800L,0x3c2},{0xa33a3550L,0xa4},{0xa33a3648L,0x10},{0xa33a3670L,0x52},{0xa33a36c2L,0xa2},{0xa33a7de0L,0x164},{0xa33a7f44L,0x164},{0xa33ac394L,0xf6},{0xa33a7408L,0x878},{0xa33a6b64L,0x878}};
   for(long[] b:buffers){byte[] seed=new byte[(int)b[1]];Arrays.fill(seed,(byte)0x6b);e.writeMemory(toAddr(b[0]),seed);}
   byteAt(0xa33a1d12L,1);e.writeMemoryValue(toAddr(0x9c180004L),4,0);stop();check(u8(0xa33a1d12L)==0&&u32(0x9c180000L)==3,"Native device stop command");
   for(long[] b:buffers)for(byte v:e.readMemory(toAddr(b[0]),(int)b[1]))check(v==0,"Seeded result survived completed stop "+Long.toHexString(b[0]));
   check(callbacks.isEmpty()&&u32(0x62f757d0L)==0,"Undrained command");
   results.add("PASS original synchronous start -> stop -> restart -> in-flight stop, class="+mode+"; submit, callback, FIFO, worker, device-stop instructions and all selection reset helpers native; 11 seeded result buffers clear; kernel services, device dispatch and MMIO hardware completion modeled");Files.write(out.resolve("native-lifecycle-trace-"+mode+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("native-lifecycle-results.txt"),results);println("NATIVE LIFECYCLE: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("native-lifecycle-results.txt"),results);Files.write(out.resolve("native-lifecycle-last-trace.txt"),trace);Files.writeString(out.resolve("native-lifecycle-failure.txt"),ex.toString());throw ex;}
 }
}
