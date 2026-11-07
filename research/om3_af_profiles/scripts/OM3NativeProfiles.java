// Research-only native MN10300 profile controller injected into emulator RAM.
// No saved project, firmware file, or device is modified.
// @category OM3
import java.nio.file.*;
import java.util.*;
import java.io.ByteArrayOutputStream;
public class OM3NativeProfiles extends OM3NativeLifecycle {
 static final long CODE=0x700d0000L,S=0x700c1000L,WIDE=0x700c1100L,NARROW=0x700c1120L,SNAPSHOT=0x700c1200L;
 static final long HP=0x01000002L,HR=0x01000003L,AP=0x01050007L,AR=0x01050008L;
 long eventEntry(){return CODE;}
 static class Asm {
  ByteArrayOutputStream b=new ByteArrayOutputStream();Map<String,Integer> labels=new HashMap<>();List<Object[]> fix=new ArrayList<>();
  void x(int... bytes){for(int v:bytes)b.write(v&255);}void w(long v){for(int i=0;i<4;i++)x((int)(v>>>(8*i)));}
  void label(String s){labels.put(s,b.size());}void jump(String s){int p=b.size();x(0xdc);w(0);fix.add(new Object[]{p,s});}
  void eq(String s){x(0xc9,7);jump(s);}void ne(String s){x(0xc8,7);jump(s);}
  void imm(int r,long v){x(0xfc,0xcc+r);w(v);}void ptr(int r,long v){x(0xfc,0xdc+r);w(v);}
  void load8(long a){x(0xfc,0xa8);w(a);}void store8(long a){x(0xfc,0x82);w(a);}
  void call(long t,int mask,int frame){long pc=CODE+b.size();x(0xdd);w(t-pc);x(mask,frame);}
  byte[] finish()throws Exception{byte[] a=b.toByteArray();for(Object[] f:fix){int p=(int)f[0];if(!labels.containsKey((String)f[1]))throw new Exception("Missing label");int d=labels.get((String)f[1])-p;for(int i=0;i<4;i++)a[p+1+i]=(byte)(d>>>(8*i));}return a;}
 }
 byte[] controller()throws Exception{
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xa0); // save 16 bytes, allocate 96; ret restores 112.
  long[] events={HP,HR,AP,AR,0};String[] names={"hp","hr","ap","ar","resolve"};
  for(int i=0;i<events.length;i++){a.x(0xfc,0xc8);a.w(events[i]);a.eq(names[i]);}a.jump("done");
  for(int i=0;i<4;i++){a.label(names[i]);a.imm(0,i%2==0?1:0);a.store8(S+(i<2?0:1));a.jump("resolve");}
  a.label("resolve");a.load8(S+1);a.x(0xa0,0);a.ne("on");a.load8(S);a.x(0xa0,0);a.eq("idle");a.imm(2,1);a.jump("scp");
  a.label("idle");a.imm(2,0);
  a.label("scp");a.imm(0,0x1e71);a.imm(1,0);a.ptr(0,0);a.call(0x60063380L,0xc0,0xc);a.x(0x83);a.ptr(2,WIDE);a.jump("selected");
  a.label("on");a.imm(2,2);a.imm(3,0);a.ptr(2,NARROW);
  a.label("selected");a.load8(S+5);a.x(0xa0,0);a.ne("change");a.load8(S+4);a.x(0xa2);a.ne("change");a.load8(S+3);a.x(0xa3);a.eq("done");
  a.label("change");a.load8(0xa33ca314L);a.x(0xf8,0xe0,3,0xa0,3);a.ne("gated");a.x(0xfc,0xac);a.w(0xa33ca2b8L);a.x(0xfc,0xc8);a.w(0x3000);a.eq("gated");
  a.load8(0xa33a1d10L);a.x(0xa0,0);a.eq("stopped");a.imm(0,0);a.ptr(0,0);a.call(0x608402adL,0xa0,0xa0);a.load8(0xa33a1d10L);a.x(0xa0,0);a.ne("stopFailed");
  a.label("stopped");a.imm(0,0);a.call(0x603cedfeL,0xc0,0x10);a.x(0x98,0xfc,0x80);a.w(S+8);a.x(0x88);a.store8(S+4);
  a.imm(0,3);a.call(0x609029f1L,0xb0,0x14);a.ptr(0,SNAPSHOT);a.call(0x608ff478L,0x30,0x18);
  a.x(0x8c);a.call(0x603cedfeL,0xc0,0x10);a.x(0xaf,0);a.eq("save");a.x(0x8c);a.ptr(0,0);a.call(0x608401afL,0xe0,0xa4);a.load8(0xa33a1d10L);a.x(0xa0,1);a.ne("startFailed");a.load8(0xa33a1d14L);a.x(0xa3);a.ne("startFailed");
  a.label("save");a.x(0x8c);a.store8(S+3);a.imm(0,0);a.store8(S+5);a.jump("done");
  a.label("gated");a.imm(0,1);a.jump("error");a.label("stopFailed");a.imm(0,2);a.jump("error");a.label("startFailed");a.imm(0,3);a.label("error");a.store8(S+5);
  a.label("done");a.x(0xdf,0xf0,0x70);return a.finish();
 }
 void installModeGuard()throws Exception{
  long guard=CODE+0x800;Asm g=new Asm();g.x(0xfc,0xa9);g.w(S+1);g.x(0xa5,1);g.ne("original");g.x(0x00);g.label("original");
  // Relocate exactly mov D0,D3; movbu (0x62a6a0eb),D2. Both are position independent.
  g.x(0x83,0xfc,0xaa);g.w(0x62a6a0ebL);int p=g.b.size();g.x(0xdc);g.w(0x603cee05L-(guard+p));e.writeMemory(toAddr(guard),g.finish());
  Asm j=new Asm();j.x(0xdc);j.w(guard-0x603cedfeL);e.writeMemory(toAddr(0x603cedfeL),j.finish());
 }
 void targetSettings(int wide){setting(0x9a41,0,0);setting(0x1dd1,0,wide==1?27:1);setting(0x1dd1,1,wide==1?39:1);setting(0x84d1,0,3);setting(0x88b2,0,526);setting(0x1df1,0,0);setting(0x1e01,0,0);setting(0x85b1,0,0);setting(0x8551,0,0);setting(0x7e81,0,0);setting(0x7e91,0,0);}
 void profileInit(int scp,Path out)throws Exception{
  lifecycleInit();e.writeMemory(toAddr(0xa33f3600L),new byte[0x180]);e.writeMemoryValue(toAddr(0xa33f3618L),4,0x70091000L);e.writeMemoryValue(toAddr(0xa33f3644L),4,0x70092000L);e.writeMemory(toAddr(0xa32d3d30L),new byte[8]);
  byteAt(0xa33f2cb0L,1);e.writeMemoryValue(toAddr(0xa33f2cdaL),2,100);e.writeMemoryValue(toAddr(0xa33ca2b8L),2,0x1700);e.writeMemoryValue(toAddr(0xa33ca314L),2,3);byteAt(0x62a6a523L,1);
  for(int wide=0;wide<=1;wide++){targetSettings(wide);byteAt(0xa33f2ceaL,1);runNative(0x609b3bb2L,0,4);check(reg("A0")==0xa33f2ce0L,"Stock record accessor");e.writeMemory(toAddr(wide==1?WIDE:NARROW),e.readMemory(toAddr(reg("A0")),10));}
  // Native accessor redirect; preserves the caller's exact []/4 return convention.
  Asm h=new Asm();h.x(0xfc,0xa0);h.w(S+8);h.x(0xdf,0,4);e.writeMemory(toAddr(0x609b3bb2L),h.finish());
  byteAt(0x62a6a0ebL,0);byteAt(S+3,255);byteAt(S+4,255);e.writeMemoryValue(toAddr(S+8),4,WIDE);setting(0x1e71,0,scp);installModeGuard();
  byte[] code=controller();e.writeMemory(toAddr(CODE),code);decodeCache.clear();Files.write(out.resolve("native-controller.emulator-only.bin"),code);
 }
 void event(long event,int scp,boolean half,boolean on)throws Exception{
  e.writeRegister("D0",event);runNative(eventEntry(),0,0);int owner=on?2:half?1:0,mode=on?0:scp;
  check(u8(S+5)==0,"Native controller rejected transition status="+u8(S+5));check(u8(S)==(half?1:0)&&u8(S+1)==(on?1:0)&&u8(S+4)==owner,"Button ownership");
  check(u8(0x62a6a0ebL)==mode&&u8(S+3)==mode,"Effective detection mode");check(u8(0xa33a1d10L)==(mode==0?0:1),"Worker lifecycle");if(mode!=0)check(u8(0xa33a1d14L)==mode,"Worker subject class");
  check(settings.get(0x1e710000L)==scp,"Saved SCP selection changed");
  check(Arrays.equals(e.readMemory(toAddr(0xa33ca384L),10),e.readMemory(toAddr(on?NARROW:WIDE),10)),"Native active profile cache mismatch");
  int[] r=on?new int[]{295,345,213,267}:new int[]{0,639,0,479};for(int i=0;i<4;i++)check(u16(SNAPSHOT+0x18+i*2)==r[i],"Current search snapshot rectangle");
  check(callbacks.isEmpty()&&u32(0x62f757d0L)==0&&u8(0xa33a1c18L)==0,"Pending command after completed event");
  long frame=0x700e0000L,output=0x700e1000L;e.writeMemory(toAddr(frame),new byte[0x600]);e.writeMemoryValue(toAddr(frame+0x59c),2,1);e.writeMemoryValue(toAddr(frame+0x550),2,8);byteAt(0x62a6a0e4L,0);byteAt(0x62a6a0efL,0);
  e.writeRegister("A0",frame);e.writeRegister("A1",output);runNative(0x60703ddeL,0x30,0xc);check(reg("D0")== (mode==0?0:1),"Native eligible-frame subject-request decision");
  trace.add("PROFILE-EVENT:"+Long.toHexString(event)+":owner="+owner+":mode="+mode);
 }
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  int tx=currentProgram.startTransaction("Temporary emulator controller mapping; read-only project will discard");
  try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  try{for(int scp=0;scp<=6;scp++){profileInit(scp,out);try{
   event(0,scp,false,false);event(HP,scp,true,false);event(HP,scp,true,false);if(scp!=0){byteAt(0xa33a1d12L,1);e.writeMemoryValue(toAddr(0x9c180004L),4,0);}event(AP,scp,true,true);event(AP,scp,true,true);event(HR,scp,false,true);event(HP,scp,true,true);event(AR,scp,true,false);event(HR,scp,false,false);event(AP,scp,false,true);event(HP,scp,true,true);event(AR,scp,true,false);event(HR,scp,false,false);
   results.add("PASS native injected controller, SCP="+scp+": 13 events cover duplicate presses, both press orders, releasing half while AF-ON held, AF-ON release restoring held half, and idle restoration; native in-flight stop for non-Off classes; current cache, 50-byte snapshot and eligible-frame detection decision checked after every event");
   event(AP,scp,false,true);
   for(int requested=0;requested<=6;requested++){e.writeRegister("D0",requested);runNative(0x603cedfeL,0xc0,0x10);check(u8(0x62a6a0ebL)==0,"Stock refresh bypassed native Off guard");}
   // Force the stock dirty flag and poison its ordinary target RAM; the native accessor
   // redirect must keep the owned profile, even when another caller requests an update.
   byteAt(0xa33f2ceaL,1);e.writeMemory(toAddr(0xa33f2ce0L),new byte[10]);e.writeRegister("D0",3);runNative(0x609029f1L,0xb0,0x14);event(0,scp,false,true);
   results.add("PASS native mode guard rejects all seven stock mode refresh requests during AF-ON; owned target survives poisoned stock target RAM plus dirty refresh, initial SCP="+scp);
   event(AR,scp,false,false);event(HP,scp,true,false);event(AP,scp,true,true);
   for(int selected=0;selected<=6;selected++){setting(0x1e71,0,selected);event(0,selected,true,true);event(AR,selected,true,false);event(AP,selected,true,true);}
   event(AR,6,true,false);event(HR,6,false,false);
   results.add("PASS SCP changes Off and all six classes while AF-ON held remain bypassed; AF-ON release restores latest SCP class with half held, initial SCP="+scp);
   Random rng=new Random(800+scp);boolean half=false,on=false;for(int i=0;i<40;i++){int which=rng.nextInt(4);if(which==0)half=true;else if(which==1)half=false;else if(which==2)on=true;else on=false;event(new long[]{HP,HR,AP,AR}[which],6,half,on);}
   results.add("PASS 40 deterministic mixed press/release events, all four held states checked after each event, initial SCP="+scp);Files.write(out.resolve("native-profile-trace-"+scp+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("native-profile-results.txt"),results);println("NATIVE PROFILES: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("native-profile-results.txt"),results);Files.write(out.resolve("native-profile-last-trace.txt"),trace);Files.writeString(out.resolve("native-profile-failure.txt"),ex.toString());throw ex;}
 }
}
