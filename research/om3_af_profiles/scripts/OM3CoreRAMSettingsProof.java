// Native mutable core settings and dirty-state behavior, with a synthetic cache.
// The checksum-valid cache is NOT read from a camera and is NOT for restoration.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CoreRAMSettingsProof extends OM3SerializedShooting {
 boolean settingSemaphoreHeld=false,nativeRead=false;
 @Override void init(){super.init();settingSemaphoreHeld=false;nativeRead=false;}
 @Override boolean external(long t)throws Exception {
  if(t==0x60063380L&&nativeRead)return false;
  if(t==0x600213f3L){trace.add("MODEL:UART-byte:"+(reg("D0")&255));return true;}
  if(t==0x6005cec3L&&reg("D0")==0xc0a000cL){check(!settingSemaphoreHeld&&reg("D1")==255,"Setting semaphore acquisition contract");settingSemaphoreHeld=true;e.writeRegister("D0",0xc0a000cL);trace.add("MODEL:shared-setting-semaphore-acquire");return true;}
  if(t==0x6005d00eL&&reg("D0")==0xc0a000cL){check(settingSemaphoreHeld,"Setting semaphore release contract");settingSemaphoreHeld=false;trace.add("MODEL:shared-setting-semaphore-release");return true;}
  if(t==0x60070e69L){check(settingSemaphoreHeld,"Cache publication without setting semaphore");trace.add("MODEL:coherent-emulator-cache-publication");return true;}
  return super.external(t);
 }
 void initializeRAM()throws Exception {
  nativeInstructionLimit=4000000;
  // Assigned by stock 60062691 before 60062ac1.
  e.writeMemoryValue(toAddr(0xa32bb90cL),4,0x60095584L);e.writeMemoryValue(toAddr(0xa32bb910L),4,0x600b8f54L);
  // Native startup's optional bank 10 object is consulted before bank 6/7
  // selection. Supply a synthetic valid bank solely to initialize that object.
  byte[] cache=new byte[0x80000];int id=u16(0x6011fe24L);cache[0]=(byte)id;cache[1]=(byte)(id>>8);int checksum=(-id)&65535;cache[cache.length-2]=(byte)checksum;cache[cache.length-1]=(byte)(checksum>>8);
  e.writeMemory(toAddr(0xa351d280L),cache);e.writeMemory(toAddr(0x6351d280L),cache);runNative(0x6006291eL,0,4);check(u32(0xa32bb928L)!=0&&u16(0xa32bb92eL)==0&&!settingSemaphoreHeld,"Synthetic cache initialization failed");
  // These are the destination addresses used by stock 6006229b. Populate
  // their values from ROM defaults after native pointer registration.
  for(long[] table:new long[][]{{0x60095584L,0x600b8f50L,0},{0x600b8f54L,0x600bb5e0L,0},{0x600bb5ecL,0x600bda6cL,0x62960708L},{0x600bda78L,0x600e4b54L,0x628f0708L},{0x600e4becL,0x6011fe20L,0x62920708L}}){
   long source=table[0];if(source==0x600b8f54L){e.writeRegister("A0",source);e.writeRegister("A1",0x628cc700L);runNative(0x60062ac1L,0,4);source=0x628cc700L;}
   e.writeRegister("A0",source);e.writeRegister("A1",table[2]);e.writeRegister("D0",0xa32a990cL);runNative(0x60062536L,0xf0,0x30);
   if(table[2]!=0){long p=table[0];while(p<table[1]){int key=u16(p),n=u16(p+2),width=(key&3)==0?4:key&3;long data=u32(0xa32a990cL+8*(key>>4)+4);byte[] values=e.readMemory(toAddr(p+4),n*width);e.writeMemory(toAddr(data),values);e.writeMemory(toAddr(data+0x40000000L),values);p=(p+4+(long)n*width+3)&~3L;}}
  }
  nativeRead=true;
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();init();trace.clear();e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided RAM fixture "+a+" at "+e.getExecutionAddress());}public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown RAM fixture "+a);}});try{initializeRAM();results.add("PASS native optional-bank checksum and constructor on explicitly synthetic zero-value cache; native registration binds normal settings to stock RAM destinations; shared-setting hardware semaphore/cache publication modeled");
   int[][] changes={{0x9fa1,0,3},{0x9fa1,1,7},{0x9fa1,2,10},{0x99d2,0,100},{0x99d2,1,200},{0x99d2,2,300},{0xdfa1,0,1}};
   for(int[] change:changes){byteAt(0xa32bfb32L,0);e.writeRegister("D0",change[0]);runNative(0x6006327fL,0xc0,0xc);check(reg("D0")==7,"AF Home does not map to native user bank 7");
    e.writeRegister("D0",change[0]);e.writeRegister("D1",change[1]);e.writeRegister("A0",0);e.writeRegister("A1",change[2]);runNative(0x60063431L,0xf0,0x28);
    check(u8(0xa32bfb32L)==1,"AF Home change did not mark user bank dirty");long data=u32(0xa32a990cL+8*(change[0]>>4)+4),location=data+change[1]*((change[0]&3)==0?4:change[0]&3);check((change[0]&3)==2?u16(location)==change[2]&&u16(location+0x40000000L)==change[2]:u8(location)==change[2]&&u8(location+0x40000000L)==change[2],"Core cache aliases diverged");e.writeRegister("D0",change[0]);e.writeRegister("D1",change[1]);e.writeRegister("A0",0);runNative(0x60063380L,0xc0,0xc);check(reg("D0")==change[2],"Native AF Home readback");
    byteAt(0xa32bfb32L,0);e.writeRegister("D0",change[0]);e.writeRegister("D1",change[1]);e.writeRegister("A0",0);e.writeRegister("A1",change[2]);runNative(0x60063431L,0xf0,0x28);check(u8(0xa32bfb32L)==0,"Unchanged value dirtied bank");
    results.add("PASS AF Home native key="+Integer.toHexString(change[0])+", index="+change[1]+": bank 7 selection, mutable value write/readback, both cache aliases, dirty-on-change and unchanged-write suppression; physical NVM write excluded");
   }
   int tx=currentProgram.startTransaction("Temporary Home builder execution mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
   e.writeMemory(toAddr(OM3HomeProfileSource.HOME),new OM3HomeProfileSource().homeBuilder());decodeCache.clear();
   for(int orientation=0;orientation<3;orientation++){e.writeRegister("D0",orientation);runNative(OM3HomeProfileSource.HOME,0,0);check(reg("D0")==0,"Home builder rejected native stored profile");long bank=BANKS+0x100+orientation*16;check(u8(bank+3)==1,"Stored Home target size was lost");e.writeRegister("D0",0x9fa1);e.writeRegister("D1",orientation);e.writeRegister("A0",0);runNative(0x60063380L,0xc0,0xc);long kindBuffer=0x700b6000L;e.writeRegister("A0",kindBuffer);runNative(0x609b3ecdL,0xe0,0x14);int kind=u8(kindBuffer);check(u8(bank+2)==kind&&u16(bank)==(kind==2?526:100+100*orientation),"Stored Home native conversion mismatch");results.add("PASS native mutable Home parameters -> native scalar getter -> Home builder -> stock enum converter -> profile record, supplied orientation="+orientation+"; configured size retained; live orientation selection excluded");}
   Files.deleteIfExists(out.resolve("core-ram-settings-failure.txt"));Files.write(out.resolve("core-ram-settings-results.txt"),results);println("CORE RAM SETTINGS: "+results.size()+" PASS");
  }catch(Exception ex){Files.writeString(out.resolve("core-ram-settings-failure.txt"),ex.toString());throw ex;}finally{Files.write(out.resolve("core-ram-settings-trace.txt"),trace);e.dispose();}
 }
}
