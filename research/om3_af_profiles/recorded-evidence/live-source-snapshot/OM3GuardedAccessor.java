// Research-only lifecycle guard. Does not build an installable update.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3GuardedAccessor extends OM3ResidentProof {
 static final long ACCESSOR=CODE+0xf50;
 byte[] guardedAccessor()throws Exception {
  Asm a=new Asm();a.load8(S+6);a.x(0xa0,1);a.ne("stock");
  a.load8(S+4);a.x(0xa0,1);a.eq("half");a.x(0xa0,2);a.eq("on");
  a.label("stock");
  // First stock instruction is six bytes; replay it and resume at its boundary.
  a.load8(0xa33f2ceaL);int p=a.b.size();a.x(0xdc);a.w(0x609b3bb8L-(ACCESSOR+p));
  a.label("half");a.ptr(0,WIDE);a.x(0xdf,0,4);
  a.label("on");a.ptr(0,NARROW);a.x(0xdf,0,4);return a.finish();
 }
 byte[] guardedMode()throws Exception {
  long origin=CODE+0x800;Asm a=new Asm();
  a.x(0xfc,0xa9);a.w(S+6);a.x(0xa5,1);a.ne("original");
  a.x(0xfc,0xa9);a.w(S+1);a.x(0xa5,1);a.ne("original");a.x(0x00);
  a.label("original");a.x(0x83,0xfc,0xaa);a.w(0x62a6a0ebL);
  int p=a.b.size();a.x(0xdc);a.w(0x603cee05L-(origin+p));return a.finish();
 }
 void installGuarded(Path out)throws Exception {
  byte[] original=new byte[24];currentProgram.getMemory().getBytes(toAddr(0x609b3bb2L),original);
  check(java.util.HexFormat.of().formatHex(Arrays.copyOf(original,6)).equals("fca8ea2c3fa3"),"Stock accessor fingerprint");
  e.writeMemory(toAddr(0x609b3bb2L),original);byte[] code=guardedAccessor();check(code.length<=0xb0,"Guard mapping extent");
  e.writeMemory(toAddr(ACCESSOR),code);Asm j=new Asm();j.x(0xdc);j.w(ACCESSOR-0x609b3bb2L);e.writeMemory(toAddr(0x609b3bb2L),j.finish());
  byte[] mode=guardedMode();e.writeMemory(toAddr(CODE+0x800),mode);decodeCache.clear();
  Files.write(out.resolve("guarded-accessor.emulator-only.bin"),code);Files.write(out.resolve("guarded-mode.emulator-only.bin"),mode);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  int tx=currentProgram.startTransaction("Temporary guarded accessor mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  profileInit(6,out);try{installGuarded(out);
   for(int enabled:new int[]{0,1,255})for(int owner:new int[]{0,1,2,3,255})for(int dirty:new int[]{0,1}){
    byteAt(S+6,enabled);byteAt(S+4,owner);targetSettings(0);setting(0x88b2,0,100);byteAt(0xa33f2ceaL,dirty);
    e.writeMemoryValue(toAddr(0xa33f2ce0L),2,200);byte[] before=e.readMemory(toAddr(0xa33f2ce0L),10);e.writeMemoryValue(toAddr(S+8),4,0xdeadbeefL);
    runNative(0x609b3bb2L,0,4);boolean owned=enabled==1&&(owner==1||owner==2);
    check(reg("A0")== (owned?(owner==1?WIDE:NARROW):0xa33f2ce0L),"Guard returned wrong source");
    if(owned){check(u8(0xa33f2ceaL)==dirty&&Arrays.equals(before,e.readMemory(toAddr(0xa33f2ce0L),10)),"Owned accessor mutated stock record");}
    else if(dirty==1){check(u16(0xa33f2ce0L)==100&&u8(0xa33f2ceaL)==1,"Stock dirty rebuild did not execute: frame="+u16(0xa33f2ce0L)+", dirty="+u8(0xa33f2ceaL));}
    results.add("PASS native accessor enabled="+enabled+", owner="+owner+", dirty="+dirty+"; invalid saved pointer ignored; exact stock fallback or fixed owned bank; stack restored");
   }
   for(int enabled:new int[]{0,1,255})for(int held:new int[]{0,1,255})for(int mode=0;mode<=6;mode++){
    byteAt(S+6,enabled);byteAt(S+1,held);byteAt(0x62a6a0ebL,mode);e.writeRegister("D0",mode);runNative(0x603cedfeL,0xc0,0x10);
    check(u8(0x62a6a0ebL)==(enabled==1&&held==1?0:mode),"Guarded effective subject selection");
   }
   results.add("PASS native effective-subject setter: all seven classes, three enable values and three held values; disabled guard restores stock setter behavior");
  }finally{e.dispose();}
  Files.write(out.resolve("guarded-accessor-results.txt"),results);println("GUARDED ACCESSOR: "+results.size()+" PASS; activation/initialization wiring remains separate");
 }
}
