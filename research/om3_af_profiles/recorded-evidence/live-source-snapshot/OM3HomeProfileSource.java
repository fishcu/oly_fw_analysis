// Native second-profile builder from existing AF-Home settings. Research harness.
// Uses supplied orientation index; camera event adapter and packaging are separate.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3HomeProfileSource extends OM3RevisionCoverage {
 static final long HOME=CODE+0xe00;
 void getter(Asm a,int key,boolean orientation){a.imm(0,key);if(orientation)a.x(0x89);else a.imm(1,0);a.ptr(0,0);callAt(a,HOME,0x60063380L,0xc0,0xc);}
 byte[] homeBuilder()throws Exception {
  Asm a=new Asm();a.x(0xcf,0xf0,0xf8,0xfe,0xe0,0x82);
  for(int ori=0;ori<3;ori++){a.x(0xaa,ori);a.eq("ori"+ori);}a.imm(0,1);a.jump("done");
  for(int ori=0;ori<3;ori++){a.label("ori"+ori);a.ptr(3,BANKS+0x100+ori*16);a.jump("build");}
  a.label("build");getter(a,0x9fa1,true);a.x(0x3c,0x20,4);callAt(a,HOME,0x609b3ecdL,0xe0,0x14);
  // Converter kind, vertical, horizontal, priority -> native ten-byte record.
  for(int[] field:new int[][]{{4,2,0},{5,4,1},{6,6,1},{7,8,0}}){a.x(0xf8,0xb8,field[0],0xf8,field[2]==1?0x73:0x53,field[1]);}
  getter(a,0xdfa1,false);a.x(0xf8,0x53,3);getter(a,0x99d2,true);a.x(0xf0,0x73);
  getter(a,0x1e01,false);a.x(0xf8,0x53,9);
  a.x(0xf8,0x43,2,0xa0,2);a.eq("all");a.x(0xa0,0);a.eq("clearPriority");a.x(0xa0,3);a.ne("success");a.x(0xf8,0x63,4,0xa0,3);a.ne("success");a.jump("clearPriority");
  a.label("all");a.imm(0,526);a.x(0xf0,0x73);a.label("clearPriority");a.imm(0,0);a.x(0xf8,0x53,8);a.label("success");a.imm(0,0);
  a.label("done");a.x(0xdf,0xf0,0x30);return a.finish();
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary Home builder mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  for(int type=0;type<=10;type++){profileInit(6,out);try{
   byte[] code=homeBuilder();check(code.length<=0x200,"Home builder extent");e.writeMemory(toAddr(HOME),code);decodeCache.clear();
   for(int i=0;i<10;i++)setting(0x1dd1,i,i%2==0?5:7);for(int i=0;i<8;i++)setting(0x1df1,i,i%2);
   for(int ori=0;ori<3;ori++){setting(0x9fa1,ori,type);setting(0x99d2,ori,100+40*ori);}
   setting(0xdfa1,0,1);setting(0x1e01,0,1);
   for(int ori=0;ori<3;ori++){
    e.writeRegister("D0",ori);runNative(HOME,0,0);check(reg("D0")==0,"Home rejected valid orientation");long bank=BANKS+0x100+16*ori;
    long p=0x700b6000L;e.writeRegister("A0",p);e.writeRegister("D0",type);runNative(0x609b3ecdL,0xe0,0x14);int kind=u8(p),v=u8(p+1),h=u8(p+2),priority=u8(p+3);if(kind==0||kind==2||(kind==3&&v==3))priority=0;
    check(u16(bank)==(kind==2?526:100+40*ori)&&u8(bank+2)==kind&&u8(bank+3)==1&&u16(bank+4)==v&&u16(bank+6)==h&&u8(bank+8)==priority&&u8(bank+9)==1,"Home record does not match native stock normalization");
    byteAt(S+16,ori);revisedEvent(AP);check(Arrays.equals(e.readMemory(toAddr(bank),10),e.readMemory(toAddr(0xa33ca384L),10))&&u8(0x62a6a0ebL)==0,"Home AF-ON activation/bypass");revisedEvent(AR);check(u8(0x62a6a0ebL)==6,"SCP restoration");
   }
   results.add("PASS existing AF-Home settings -> native converter -> ten-byte profile -> AF-ON cache, enum="+type+", all three supplied orientation indices; size retained, SCP class restored, no setting writes");Files.write(out.resolve("home-profile-results.txt"),results);Files.write(out.resolve("home-profile-builder.emulator-only.bin"),code);
  }finally{e.dispose();}}
  println("HOME PROFILE SOURCE: "+results.size()+" PASS; UI/storage/physical orientation not asserted");
 }
}
