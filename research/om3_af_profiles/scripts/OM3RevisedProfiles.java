// Revision 2: native recovery admission and profile-change reconciliation.
// All code/data addresses remain emulator-only fixtures.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3RevisedProfiles extends OM3NativeFaults {
 static final long RECONCILE=CODE+0x500,CAPTURE=CODE+0xc00,BANKS=0x700c2000L;
 List<long[]> timers=new ArrayList<>();int timerDeliveries=0;
 boolean workerHealthGuard=true; // Disabled only by the explicit before-fix regression probe.
 @Override long eventEntry(){return RECONCILE;}
 void callAt(Asm a,long origin,long target,int mask,int frame){long pc=origin+a.b.size();a.x(0xdd);a.w(target-pc);a.x(mask,frame);}
 void load32(Asm a,long address){a.x(0xfc,0xa4);a.w(address);}
 void store32(Asm a,long address){a.x(0xfc,0x81);a.w(address);}
 void copy10(Asm a){for(int i=0;i<5;i++)a.x(0xf0,0x60,0xf0,0x71,0x20,2,0x21,2);}
 byte[] reconcile()throws Exception{
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0);a.x(0x82);a.load8(S+7);a.x(0xa0,0);a.ne("busy");
  // Record physical held-state even while a failed operation is awaiting completion.
  for(int i=0;i<4;i++){a.x(0x88,0xfc,0xc8);a.w(new long[]{HP,HR,AP,AR}[i]);a.eq("event"+i);}a.x(0x88,0xa0,0);a.eq("admit");a.jump("done");
  for(int i=0;i<4;i++){a.label("event"+i);a.imm(0,i%2==0?1:0);a.store8(S+(i<2?0:1));a.jump("admit");}
  a.label("admit");a.load8(S+5);a.x(0xa0,0);a.eq("profiles");a.x(0xa0,1);a.eq("profiles");a.x(0xa0,5);a.eq("profiles");
  a.load8(0xa33a1c18L);a.x(0xa0,0);a.ne("pending");load32(a,0x62f757d0L);a.x(0xa0,0);a.ne("pending");
  a.label("profiles");a.imm(0,1);a.store8(S+7);
  // Select a captured orientation bank, then compare the entire active record.
  a.load8(S+16);a.x(0xa0,0);a.eq("ori0");a.x(0xa0,1);a.eq("ori1");a.x(0xa0,2);a.eq("ori2");a.jump("invalid");
  for(int ori=0;ori<3;ori++){a.label("ori"+ori);a.ptr(0,BANKS+ori*16);a.load8(S+1);a.x(0xa0,0);a.eq("half"+ori);a.ptr(0,BANKS+0x100+ori*16);a.ptr(1,NARROW);a.jump("copy");a.label("half"+ori);a.ptr(1,WIDE);a.jump("copy");}
  a.label("copy");copy10(a);a.load8(S+1);a.x(0xa0,0);a.eq("compareHalf");a.ptr(0,NARROW);a.jump("compare");a.label("compareHalf");a.ptr(0,WIDE);a.label("compare");a.ptr(1,0xa33ca384L);
  for(int i=0;i<5;i++){a.x(0xf0,0x60,0xf0,0x65,0xa4);a.ne("changed");a.x(0x20,2,0x21,2);}
  // Cached ownership is insufficient after an external lifecycle reset.
  if(workerHealthGuard){a.load8(S+3);a.x(0x83,0xa0,0);a.eq("offHealth");a.load8(0xa33a1d10L);a.x(0xa0,1);a.ne("changed");a.load8(0xa33a1d14L);a.x(0xa3);a.ne("changed");a.jump("run");
  a.label("offHealth");a.load8(0xa33a1d10L);a.x(0xa0,0);a.ne("changed");a.jump("run");}else a.jump("run");
  a.label("changed");a.imm(0,5);a.store8(S+5);a.label("run");a.imm(0,0);callAt(a,RECONCILE,CODE,0,0);a.imm(0,0);a.store8(S+7);a.jump("done");
  a.label("invalid");a.imm(0,0);a.store8(S+7);a.imm(0,7);a.jump("error");a.label("pending");a.imm(0,4);a.jump("error");a.label("busy");a.imm(0,6);a.label("error");a.store8(S+5);a.label("done");a.x(0xdf,0xf0,0x30);return a.finish();
 }
 byte[] capture()throws Exception{
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0,0x82,0x87); // D2=button D3=orientation
  a.x(0xaa,0);a.eq("half");a.x(0xaa,1);a.ne("invalid");a.ptr(3,BANKS+0x100);a.jump("ori");a.label("half");a.ptr(3,BANKS);
  a.label("ori");a.x(0xaf,0);a.eq("capture");a.x(0xaf,1);a.eq("ori1");a.x(0xaf,2);a.ne("invalid");a.x(0x23,0x20);a.jump("capture");a.label("ori1");a.x(0x23,0x10);
  a.label("capture");callAt(a,CAPTURE,0x609b3c79L,0xe0,0x20);a.ptr(0,0xa33f2ce0L);a.x(0x9d);copy10(a);load32(a,S+12);a.x(0x40);store32(a,S+12);a.imm(0,0);a.jump("done");a.label("invalid");a.imm(0,1);a.label("done");a.x(0xdf,0xf0,0x30);return a.finish();
 }
 @Override void profileInit(int scp,Path out)throws Exception{
  super.profileInit(scp,out);timers.clear();timerDeliveries=0;failedMask=0;
  for(int ori=0;ori<3;ori++){e.writeMemory(toAddr(BANKS+16*ori),e.readMemory(toAddr(WIDE),10));e.writeMemory(toAddr(BANKS+0x100+16*ori),e.readMemory(toAddr(NARROW),10));}
  for(long[] id:new long[][]{{0x60043124L,101},{0x60043126L,102},{0x6004367aL,103},{0x6004367cL,104}})e.writeMemoryValue(toAddr(id[0]),2,id[1]);
  byte[] r=reconcile(),c=capture();check(r.length<0x300&&c.length<0x200,"Revision code overlaps guard or mapping");e.writeMemory(toAddr(RECONCILE),r);e.writeMemory(toAddr(CAPTURE),c);decodeCache.clear();Files.write(out.resolve("revised-reconcile.emulator-only.bin"),r);Files.write(out.resolve("revised-capture.emulator-only.bin"),c);
 }
 @Override boolean external(long t)throws Exception{
  if(t==0x600760f9L){check(reg("A0")==0x608412c5L,"Unexpected deferred callback");timers.add(new long[]{reg("A0"),reg("A1")});e.writeRegister("D0",0);return true;}
  if(t==0x60072c53L&&reg("A0")==0x608413b4L){child(0x608413b4L,0);return true;}
  return super.external(t);
 }
 @Override void drain()throws Exception{
  int bound=0;while(!callbacks.isEmpty()||!timers.isEmpty()){
   check(bound++<32,"Scheduler progress bound");if(!callbacks.isEmpty()){long[] c=callbacks.remove(0);check(c[0]==0x608418feL,"Unexpected scheduled callback");child(c[0],c[1]);}
   else {long[] c=timers.remove(0);timerDeliveries++;child(c[0],c[1]);}
  }
  worker=true;try{child(0x60841a6bL,0);}finally{worker=false;}
 }
 void revisedEvent(long event)throws Exception{e.writeRegister("D0",event);runNative(RECONCILE,0,0);}
 void captureStock(int button,int orientation)throws Exception{e.writeRegister("D0",button);e.writeRegister("D1",orientation);runNative(CAPTURE,0,0);check(reg("D0")==0,"Capture rejected");}
 @Override byte[] wrapper(long address,long event,long original)throws Exception{byte[] b=super.wrapper(address,event,original);int call=19;check((b[call]&255)==0xdd,"Wrapper layout");long delta=RECONCILE-(address+call);for(int i=0;i<4;i++)b[call+1+i]=(byte)(delta>>>(8*i));return b;}
 @Override void raw(long ev)throws Exception{revisedEvent(ev);}
}
