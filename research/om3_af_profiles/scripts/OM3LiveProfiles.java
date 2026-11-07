// Live stock/Home configuration with inactive records and uncached owned state.
// Physical AF orientation producer and complete camera behavior remain untested.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3LiveProfiles extends OM3CoreRAMSettingsProof {
 static final long OWN=DATA+0x40000000L,HOME=CODE+0xe00,MODE=CODE+0x1200,MODE_DEST=0x607187a4L,SECONDARY=0x6031eb80L;
 boolean modelButtonBodies=false,observePublication=false;int buttonCalls=0,publicationChecks=0;long observedPointer=-1;byte[] observedRecord;
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  if(observePublication&&u8(OWN+6)==1&&(u8(OWN+4)==1||u8(OWN+4)==2)){
   long p=u32(OWN+8);byte[] bytes=e.readMemory(toAddr(p),10);
   if(p==observedPointer){check(Arrays.equals(bytes,observedRecord),"Published profile was overwritten before pointer switch");publicationChecks++;}
   else {observedPointer=p;observedRecord=bytes;}
  }else observedPointer=-1;
  return super.instruction(ins);
 }
 @Override long dataAddress(long a){long mapped=super.dataAddress(a);return mapped!=a?mapped+0x40000000L:a;}
 @Override byte[] initializer()throws Exception {
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0);a.load8(S+17);a.x(0xa0,1);a.eq("done");
  a.imm(0,0);a.x(0x42,4,0x42,8);a.imm(0,2);a.x(0xf8,0x92,4,0x3c,0x50);callAt(a,INIT,0x60030659L,0xa0,0x10);
  a.x(0xa0,0,0xc2,7);a.jump("failure");a.x(0xa0,0);a.eq("failure");store32(a,S+20);a.imm(0,1);a.store8(S+17);a.jump("done");
  a.label("failure");a.imm(0,0);a.store8(S+6);store32(a,S+20);a.imm(0,2);a.store8(S+17);
  a.label("done");a.x(0xdf,0xf0,0x30);return a.finish();
 }
 void readSetting(Asm a,long origin,int key,int index){a.imm(0,key);a.imm(1,index);a.ptr(0,0);callAt(a,origin,0x60063380L,0xc0,0xc);}
 @Override byte[] controller()throws Exception {
  byte[] code=super.controller();int replaced=0;
  for(int i=0;i+6<=code.length;i++)if((code[i]&255)==0xfc&&(code[i+1]&255)==0xde){long p=0;for(int k=0;k<4;k++)p|=(code[i+2+k]&255L)<<(8*k);if(p==WIDE||p==NARROW){code[i+1]=(byte)0xa2;put(code,i+2,p+12);replaced++;}}
  check(replaced==2,"Controller candidate-pointer sites");return code;
 }
 byte[] liveHomeBuilder()throws Exception {return new IndependentHomeBuilder().homeBuilder();}
 static class IndependentHomeBuilder extends OM3HomeProfileSource {
  // Extension ABI: D0 is area orientation; D3 is position orientation. The
  // builder and its native callees preserve D3 until the position getter.
  @Override void getter(Asm a,int key,boolean orientation){a.imm(0,key);if(orientation)a.x(key==0x99d2?0x8d:0x89);else a.imm(1,0);a.ptr(0,0);callAt(a,HOME,0x60063380L,0xc0,0xc);}
 }
 @Override byte[] guardedMode()throws Exception {
  Asm a=new Asm();a.x(0xfc,0xa9);a.w(S+6);a.x(0xa5,1);a.ne("original");a.x(0xfc,0xa9);a.w(S+1);a.x(0xa5,1);a.ne("original");a.x(0x00);a.label("original");a.x(0x83,0xfc,0xaa);a.w(0x62a6a0ebL);int p=a.b.size();a.x(0xdc);a.w(0x603cee05L-(MODE+p));return a.finish();
 }
 void chooseStage(Asm a,String label,long first,long destination){load32(a,S+8);a.x(0xfc,0xc8);a.w(first);a.eq(label+"alternate");a.ptr(1,first);a.jump(label+"chosen");a.label(label+"alternate");a.ptr(1,first+16);a.label(label+"chosen");a.x(0xf1,0xd4);store32(a,destination);}
 @Override byte[] reconcile()throws Exception {
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0,0x82);a.load8(S+7);a.x(0xa0,0);a.ne("busy");
  for(int i=0;i<4;i++){a.x(0x88,0xfc,0xc8);a.w(new long[]{HP,HR,AP,AR}[i]);a.eq("edge"+i);}a.x(0x88,0xa0,0);a.eq("admit");a.jump("done");
  for(int i=0;i<4;i++){a.label("edge"+i);a.imm(0,i%2==0?1:0);a.store8(S+(i<2?0:1));a.jump("admit");}
  a.label("admit");a.load8(S+5);a.x(0xa0,0);a.eq("build");a.x(0xa0,1);a.eq("build");a.x(0xa0,5);a.eq("build");a.load8(0xa33a1c18L);a.x(0xa0,0);a.ne("pending");load32(a,0x62f757d0L);a.x(0xa0,0);a.ne("pending");
  a.label("build");a.imm(0,1);a.store8(S+7);
  callAt(a,RECONCILE,0x609b3c79L,0xe0,0x20);chooseStage(a,"half",BANKS+0x40,WIDE+12);a.ptr(0,0xa33f2ce0L);copy10(a);
  // UI MODE_AF_ORIENTATION is a candidate mapping to e91[3]. Codes 4/5
  // select the same CCW/CW banks as the stock AF Home editor. Hardware producer
  // equivalence is deliberately not asserted by the supplied-value probes.
  readSetting(a,RECONCILE,0xe91,3);a.x(0x42,8);a.imm(2,0);a.imm(3,0);
  readSetting(a,RECONCILE,0x1db1,0);a.x(0xa0,1);a.ne("position");a.x(0x58,8,0xa0,4);a.eq("areaCCW");a.x(0xa0,5);a.ne("position");a.imm(2,2);a.jump("position");a.label("areaCCW");a.imm(2,1);
  a.label("position");readSetting(a,RECONCILE,0x1dc1,0);a.x(0xa0,1);a.ne("home");a.x(0x58,8,0xa0,4);a.eq("frameCCW");a.x(0xa0,5);a.ne("home");a.imm(3,2);a.jump("home");a.label("frameCCW");a.imm(3,1);
  a.label("home");a.x(0x88,0x8d);callAt(a,RECONCILE,HOME,0,0);a.x(0xa0,0);a.ne("invalid");chooseStage(a,"on",BANKS+0x60,NARROW+12);a.ptr(0,BANKS+0x100);a.x(0x88,0xf8,0xc0,4,0xf1,0x60);copy10(a);
  a.load8(S+1);a.x(0xa0,0);a.eq("halfCompare");load32(a,NARROW+12);a.jump("compare");a.label("halfCompare");load32(a,WIDE+12);a.label("compare");a.x(0xf1,0xe0);a.ptr(1,0xa33ca384L);
  for(int i=0;i<5;i++){a.x(0xf0,0x60,0xf0,0x65,0xa4);a.ne("changed");a.x(0x20,2,0x21,2);}
  a.load8(S+3);a.x(0x83,0xa0,0);a.eq("offHealth");a.load8(0xa33a1d10L);a.x(0xa0,1);a.ne("changed");a.load8(0xa33a1d14L);a.x(0xa3);a.ne("changed");a.jump("run");a.label("offHealth");a.load8(0xa33a1d10L);a.x(0xa0,0);a.ne("changed");a.jump("run");
  a.label("changed");a.imm(0,5);a.store8(S+5);a.label("run");a.imm(0,0);callAt(a,RECONCILE,CODE,0,0);a.imm(0,0);a.store8(S+7);a.jump("done");
  a.label("invalid");a.imm(0,0);a.store8(S+7);a.imm(0,7);a.jump("error");a.label("pending");a.imm(0,4);a.jump("error");a.label("busy");a.imm(0,6);a.label("error");a.store8(S+5);a.label("done");a.x(0xdf,0xf0,0x30);return a.finish();
 }
 @Override byte[] guardedAccessor()throws Exception {
  Asm a=new Asm();a.load8(S+6);a.x(0xa0,1);a.ne("stock");a.load8(S+4);a.x(0xa0,1);a.eq("pointer");a.x(0xa0,2);a.ne("stock");a.label("pointer");load32(a,S+8);
  for(long p:new long[]{BANKS+0x40,BANKS+0x50,BANKS+0x60,BANKS+0x70}){a.x(0xfc,0xc8);a.w(p);a.eq("owned");}
  a.label("stock");a.load8(0xa33f2ceaL);int p=a.b.size();a.x(0xdc);a.w(0x609b3bb8L-(ACCESSOR+p));a.label("owned");a.x(0xf1,0xe0,0xdf,0,4);return a.finish();
 }
 @Override void profileInit(int scp,Path out)throws Exception {
  lifecycleInit();timers.clear();timerDeliveries=0;failedMask=0;dataMap[1][2]=16;dataMap[2][2]=16;
  e.writeMemory(toAddr(0xa33f3600L),new byte[0x180]);e.writeMemoryValue(toAddr(0xa33f3618L),4,0x70091000L);e.writeMemoryValue(toAddr(0xa33f3644L),4,0x70092000L);e.writeMemory(toAddr(0xa32d3d30L),new byte[8]);byteAt(0xa33f2cb0L,1);e.writeMemoryValue(toAddr(0xa33f2cdaL),2,100);e.writeMemoryValue(toAddr(0xa33ca2b8L),2,0x1700);e.writeMemoryValue(toAddr(0xa33ca314L),2,3);byteAt(0x62a6a523L,1);byteAt(0x62a6a0ebL,0);byteAt(S+3,255);byteAt(S+4,255);byteAt(S+6,1);e.writeMemoryValue(toAddr(S+8),4,WIDE);setting(0x1e71,0,scp);targetSettings(1);
  for(long[] id:new long[][]{{0x60043124L,101},{0x60043126L,102},{0x6004367aL,103},{0x6004367cL,104}})e.writeMemoryValue(toAddr(id[0]),2,id[1]);
 }
 @Override void pack(Path out)throws Exception {
  int tx=currentProgram.startTransaction("Live profile source mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE+0x1000))==null)currentProgram.getMemory().createInitializedBlock("live_profile_sources",toAddr(CODE+0x1000),0x3000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  List<Long> origins=new ArrayList<>(Arrays.asList(CODE,RECONCILE,MODE,ACCESSOR,HOME));List<byte[]> code=new ArrayList<>(Arrays.asList(controller(),gatedReconcile(),guardedMode(),guardedAccessor(),liveHomeBuilder()));
  for(int i=0;i<4;i++){long source=SOURCES+512*i;origins.add(source);code.add(wrapper(source,new long[]{HP,HR,AP,AR}[i],new long[]{0x610b9197L,0x610b96f0L,0x610b962aL,0x610b9653L}[i]));}
  blocks.clear();long p=DEST,primaryEnd=DEST;boolean second=false;
  for(int i=0;i<code.size();i++){int n=code.get(i).length;long destination;
   if(origins.get(i)==MODE){destination=MODE_DEST;check(destination+n<=0x60718800L,"Mode guard must remain in section 2");}
   else {if(!second&&p+n>0x60a8f800L){primaryEnd=p;p=SECONDARY;second=true;}check(p+n<=(second?0x6031f000L:0x60a8f800L),"Live profile code capacity");destination=p;p+=n;}
   blocks.add(new long[]{origins.get(i),destination,n});byte[] stock=new byte[n];currentProgram.getMemory().getBytes(toAddr(destination),stock);for(byte v:stock)check((v&255)==255,"Live code placement fingerprint");}
  if(!second)primaryEnd=p;packedSize=(int)(primaryEnd-DEST);for(int i=0;i<code.size();i++){long[] block=blocks.get(i);e.writeMemory(toAddr(block[1]),relocate(code.get(i),block[0],block[1]));}packedEntry=translated(RECONCILE);packedCapture=0;
  for(long[] hook:new long[][]{{0x603cedfeL,translated(MODE)},{0x609b3bb2L,translated(ACCESSOR)}}){Asm j=new Asm();j.x(0xdc);j.w(hook[1]-hook[0]);e.writeMemory(toAddr(hook[0]),j.finish());}decodeCache.clear();List<String> map=new ArrayList<>();for(long[] block:blocks)map.add(String.format("%08x -> %08x length=%d",block[0],block[1],block[2]));Files.write(out.resolve("live-profile-relocation-map.txt"),map);
 }
 @Override boolean external(long t)throws Exception {
  if(t==0x600232d1L&&reg("A0")==0xa03ba800L){long src=reg("A1"),n=reg("D0");check(src==0x50399800L&&n==0x35e000L&&reg("D1")==0x10200,"Unexpected section 2 storage request");byte[] bytes=Arrays.copyOfRange(image,(int)(src-0x50000020L),(int)(src-0x50000020L+n));e.writeMemory(toAddr(0xa03ba800L),bytes);e.writeMemory(toAddr(0x603ba800L),bytes);storageReads++;decodeCache.clear();trace.add("MODEL:section-2-storage-and-cache-alias");e.writeRegister("D0",0);return true;}
  if(modelButtonBodies&&(t==0x610b9197L||t==0x610b96f0L||t==0x610b962aL||t==0x610b9653L)){check(u8(OWN+6)!=1||Boolean.TRUE.equals(mutexes.get(u32(OWN+20))),"Live original ABI boundary outside mutex");buttonCalls++;return true;}
  return super.external(t);
 }
 @Override void load(int section,int fill)throws Exception {
  if(section==2){long lo=0x603ba800L,hi=0x60718800L;byte[] poison=new byte[(int)(hi-lo)];Arrays.fill(poison,(byte)fill);e.writeMemory(toAddr(lo),poison);decodeCache.clear();e.writeRegister("D0",2);runNative(0x60045ed5L,0xf0,0x14);check((u32(0xa32de590L)&2)!=0&&Arrays.equals(e.readMemory(toAddr(lo),(int)(hi-lo)),Arrays.copyOfRange(image,(int)(lo-0x60021020L),(int)(hi-0x60021020L))),"Whole section 2 native load differs");return;}
  if(section==4&&(u32(0xa32de590L)&2)==0)load(2,0xcc);
  super.load(section,fill);
 }
 void writeSetting(int key,int index,int value)throws Exception {e.writeRegister("D0",key);e.writeRegister("D1",index);e.writeRegister("A0",0);e.writeRegister("A1",value);runNative(0x60063431L,0xf0,0x28);}
 byte[] expectedHome(int type,int frame)throws Exception {
  long p=0x700b7000L;e.writeRegister("D0",type);e.writeRegister("A0",p);runNative(0x609b3ecdL,0xe0,0x14);
  int kind=u8(p),rows=u8(p+1),cols=u8(p+2),priority=u8(p+3);if(kind==0||kind==2||(kind==3&&rows==3))priority=0;
  byte[] b=new byte[10];int f=kind==2?526:frame;b[0]=(byte)f;b[1]=(byte)(f>>8);b[2]=(byte)kind;b[3]=1;b[4]=(byte)rows;b[6]=(byte)cols;b[8]=(byte)priority;return b;
 }
 void expandedTests(List<String> results)throws Exception {
  observePublication=true;
  for(int focus:new int[]{0,2}){
   writeSetting(0xc021,0,focus);byteAt(0xa33f2c9dL,focus);
   for(int type=0;type<=10;type++)for(int pose:new int[]{0,4,5})for(int flags=0;flags<4;flags++){
    writeSetting(0xe91,3,pose);writeSetting(0x1db1,0,flags&1);writeSetting(0x1dc1,0,(flags>>1)&1);
    for(int i=0;i<3;i++){writeSetting(0x9fa1,i,(type+i)%11);writeSetting(0x99d2,i,100+100*i);}
    int ori=pose==4?1:pose==5?2:0,area=(flags&1)!=0?ori:0,position=(flags&2)!=0?ori:0;
    byte[] expected=expectedHome((type+area)%11,100+100*position);
    liveButton(2);check(Arrays.equals(expected,e.readMemory(toAddr(0xa33ca384L),10)),"Live independent Home area/position or stock enum mismatch");
    liveButton(0);check(u8(OWN+4)==2&&u8(0x62a6a0ebL)==0,"AF-ON lost precedence when half pressed second");
    liveButton(1);check(u8(OWN+4)==2,"Half release disturbed held AF-ON");liveButton(3);
    check(u8(OWN+4)==0&&u8(0xa33f2c9dL)==focus,"Idle/shared focus altered");
   }
   results.add("PASS integrated native RAM Home configuration: all 11 enum values x three supplied pose codes x four independent area/position enable combinations, shared focus="+focus+"; native converter oracle, AF-ON precedence and release ordering");
  }
  writeSetting(0x1db1,0,0);writeSetting(0x1dc1,0,0);writeSetting(0x9fa1,0,1);
  for(int subject=0;subject<=6;subject++){
   writeSetting(0x1e71,0,subject);boolean half=false,on=false;Random rng=new Random(1700+subject);
   for(int n=0;n<40;n++){int b=rng.nextInt(4);if(b==0)half=true;else if(b==1)half=false;else if(b==2)on=true;else on=false;liveButton(b);check(u8(OWN+4)==(on?2:half?1:0)&&u8(0x62a6a0ebL)==(on?0:subject),"Live mixed event ownership/SCP mismatch");}
   liveButton(3);liveButton(1);
  }
  results.add("PASS 280 deterministic mixed button events across SCP Off and all six subject classes, latest SCP retained, both held orders and duplicate edges");
  check(publicationChecks>10000,"Publication observation did not execute");results.add("PASS instruction-boundary observation: "+publicationChecks+" checks find current published ten-byte record unchanged until pointer replacement; does not prove cross-CPU cache ordering or lifetime of retained old pointers");observePublication=false;
  liveButton(0);long prior=u32(OWN+8);e.writeMemoryValue(toAddr(OWN+8),4,0xdeadbeefL);runNative(0x609b3bb2L,0,4);check(reg("A0")==0xa33f2ce0L,"Invalid owned pointer did not fall back to stock");e.writeMemoryValue(toAddr(OWN+8),4,prior);
  results.add("PASS owned accessor rejects invalid active pointer and executes native stock accessor fallback");
  for(int gate=0;gate<2;gate++){
   long pointer=u32(OWN+8);byte[] before=e.readMemory(toAddr(pointer),10);int calls=buttonCalls;
   if(gate==0)e.writeMemoryValue(toAddr(0xa33ca314L),2,0);else e.writeMemoryValue(toAddr(0xa33ca2b8L),2,0x3000);
   runNative(translated(CODE+0x900+128*2),0,0);
   check(u8(OWN+5)==1&&buttonCalls==calls&&u32(OWN+8)==pointer&&Arrays.equals(before,e.readMemory(toAddr(pointer),10))&&!mutexes.get(u32(OWN+20)),"Gated transition published a profile or forwarded original");
   e.writeMemoryValue(toAddr(0xa33ca314L),2,3);e.writeMemoryValue(toAddr(0xa33ca2b8L),2,0x1700);liveButton(2);liveButton(3);
  }
  liveButton(1);results.add("PASS both native target gates reject AF-ON before publication/original call, preserve active bytes, unlock, and recover on next valid event");
 }
 void liveButton(int button)throws Exception {e.writeRegister("A0",0x700b4000L);e.writeRegister("A1",0x700b5000L);runNative(translated(CODE+0x900+128*button),0,0);trace.add(String.format("LIVE-DIAG button=%d owner=%d mode=%d active=%08x frame=%d kind=%d candidates=%08x/%08x home=%s activeBytes=%s",button,u8(OWN+4),u8(0x62a6a0ebL),u32(OWN+8),u16(0xa33ca384L),u8(0xa33ca386L),u32(dataAddress(WIDE)+12),u32(dataAddress(NARROW)+12),Arrays.toString(e.readMemory(toAddr(dataAddress(BANKS)+0x100),10)),Arrays.toString(e.readMemory(toAddr(u32(OWN+8)),10))));check(u8(OWN+5)==0&&!mutexes.get(u32(OWN+20)),"Live button status or mutex");}
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Live source mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  profileInit(6,out);try{prepareResident(out);load(1,0xa5);load(2,0xcc);byte[] absentSection=new byte[0x267800];Arrays.fill(absentSection,(byte)0xa5);e.writeMemory(toAddr(0x60828000L),absentSection);decodeCache.clear();e.writeRegister("D0",0);runNative(0x603cedfeL,0xc0,0x10);check(u8(0x62a6a0ebL)==0,"Mode setter before section 4 load");results.add("PASS native section 2 whole-range load and early stock mode setter with section 4 deliberately absent; mode guard resides in the same loaded section as its hook, before owned button activity");rejectCreate=true;load(4,0x55);modelButtonBodies=true;check(u8(OWN+17)==2&&u8(OWN+6)==0&&u32(OWN+20)==0,"Failed mutex creation did not select stock fallback");
   int priorCalls=buttonCalls;runNative(translated(CODE+0x900+128*2),0,0);check(buttonCalls==priorCalls+1&&u8(OWN+1)==0,"Failed initialization withheld stock button handler or altered held state");
   runNative(0x602153fbL,0xa0,0xc);check(u8(OWN+17)==1&&u8(OWN+6)==0,"Mutex retry unexpectedly armed feature");byteAt(OWN+6,1);initializeRAM();check(u8(OWN+17)==1&&u8(OWN+6)==1,"Live boot initialization");
   results.add("PASS failed native constructor mutex creation disables extension and forwards stock original-handler model without held-state change; resource retry creates mutex but requires explicit re-arm; no hardware startup assertion");
   writeSetting(0x84d1,0,2);writeSetting(0x88b2,0,526);writeSetting(0xdfa1,0,1);writeSetting(0x1db1,0,0);writeSetting(0x1dc1,0,0);writeSetting(0xe91,3,0);
   for(int i=0;i<10;i++)writeSetting(0x1dd1,i,i%2==0?5:7);
   for(int i=0;i<3;i++){writeSetting(0x9fa1,i,i+1);writeSetting(0x99d2,i,100+100*i);}
   for(int subject=0;subject<=6;subject++){writeSetting(0x1e71,0,subject);liveButton(0);check(u8(OWN+4)==1&&u8(0x62a6a0ebL)==subject&&u8(0xa33ca386L)==2,"Live half profile/SCP");liveButton(2);check(u8(OWN+4)==2&&u8(0x62a6a0ebL)==0&&u16(0xa33ca384L)==100&&u8(0xa33ca386L)==0,"Live Home AF-ON profile/bypass");liveButton(3);check(u8(OWN+4)==1&&u8(0x62a6a0ebL)==subject&&u8(0xa33ca386L)==2,"Live half restoration");liveButton(1);check(u8(OWN+4)==0&&u8(0x62a6a0ebL)==subject,"Live idle restoration");results.add("PASS live native RAM configuration, SCP="+subject+": stock All half profile, stock Home single-point AF-ON, size, bypass and restoration; uncached extension state, immutable staging, owned mutex, modeled original bodies");}
   expandedTests(results);Files.write(out.resolve("live-main-payload.research-only.bin"),image);Files.deleteIfExists(out.resolve("live-profile-failure.txt"));Files.write(out.resolve("live-profile-results.txt"),results);Files.write(out.resolve("live-profile-trace.txt"),trace);println("LIVE PROFILES: "+results.size()+" PASS; physical orientation source, original bodies, display and camera boot excluded");
  }catch(Exception ex){Files.writeString(out.resolve("live-profile-failure.txt"),ex.toString());Files.write(out.resolve("live-profile-last-trace.txt"),trace);throw ex;}finally{e.dispose();}
 }
}
