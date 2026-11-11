// Camera-address placement and native section-loading tests, emulator only.
// No firmware/update image is written. Storage/cache aliasing remain explicit models.
// @category OM3
import java.nio.file.*;
import java.util.*;
import ghidra.app.util.PseudoDisassembler;
import ghidra.app.util.PseudoInstruction;
public class OM3ResidentProof extends OM3PackedRelocation {
 static final long DATA=0x6031e920L;
 long[][] dataMap={{S,DATA,24},{WIDE,DATA+0x20,10},{NARROW,DATA+0x30,10},{SNAPSHOT,DATA+0x40,50},{BANKS,DATA+0x80,0x130}};
 byte[] image;int storageReads;
 long dataAddress(long a){for(long[] m:dataMap)if(a>=m[0]&&a<m[0]+m[2])return m[1]+a-m[0];return a;}
 void put(byte[] b,int p,long v){for(int i=0;i<4;i++)b[p+i]=(byte)(v>>>(8*i));}
 void inImage(long a,byte[] bytes){System.arraycopy(bytes,0,image,(int)(a-0x60021020L),bytes.length);}
 byte[] absoluteData(byte[] bytes,long origin)throws Exception{
  byte[] result=bytes.clone();PseudoDisassembler dis=new PseudoDisassembler(currentProgram);dis.setRespectExecuteFlag(false);
  for(int i=0;i<bytes.length;){PseudoInstruction ins=dis.disassemble(toAddr(origin+i),Arrays.copyOfRange(bytes,i,Math.min(i+16,bytes.length)));check(ins!=null,"Resident decode");int n=ins.getLength();
   if((bytes[i]&255)==0xfc&&n>=6){long old=0;for(int k=0;k<4;k++)old|=(long)(bytes[i+2+k]&255)<<(8*k);long mapped=dataAddress(old);if(mapped!=old)put(result,i+2,mapped);}
   i+=n;check(i<=bytes.length,"Resident instruction split");}
  return result;
 }
 void prepareResident(Path out)throws Exception{
  pack(out);image=Files.readAllBytes(Paths.get("analysis/decoded/00_0100_50000020.decoded.bin"));storageReads=0;
  for(long[] b:blocks){byte[] code=absoluteData(e.readMemory(toAddr(b[1]),(int)b[2]),b[1]);e.writeMemory(toAddr(b[1]),code);inImage(b[1],code);}
  for(long[] m:dataMap){byte[] bytes=e.readMemory(toAddr(m[0]),(int)m[2]);e.writeMemory(toAddr(m[1]),bytes);}
  e.writeMemoryValue(toAddr(DATA+8),4,dataAddress(u32(S+8)));
  byte[] data=e.readMemory(toAddr(DATA),0x1b0);inImage(DATA,data);
  byte[] accessor=absoluteData(e.readMemory(toAddr(0x609b3bb2L),9),0x609b3bb2L);e.writeMemory(toAddr(0x609b3bb2L),accessor);inImage(0x609b3bb2L,accessor);inImage(0x603cedfeL,e.readMemory(toAddr(0x603cedfeL),5));
  long[] tables={0x6131bd50L,0x6131bd60L,0x6131c290L,0x6131c2a0L};for(int i=0;i<4;i++){byte[] p=new byte[4];put(p,0,translated(CODE+0x900+i*128));e.writeMemory(toAddr(tables[i]+12),p);inImage(tables[i]+12,p);}
  decodeCache.clear();e.writeMemoryValue(toAddr(0xa32de590L),4,0);
  Files.write(out.resolve("resident-code.emulator-only.bin"),e.readMemory(toAddr(DEST),packedSize));Files.write(out.resolve("resident-data-initial.emulator-only.bin"),data);
 }
 @Override boolean external(long t)throws Exception{
  if(t==0x600232d1L){long dst=reg("A0"),src=reg("A1"),n=reg("D0");check((dst==0xa0134000L&&src==0x50113000L&&n==0x1eb000L)||(dst==0xa0828000L&&src==0x50807000L&&n==0x267800L),"Unexpected native storage request "+Long.toHexString(dst)+":"+Long.toHexString(src)+":"+Long.toHexString(n));check(reg("D1")==0x10200,"Native storage flags");int offset=(int)(src-0x50000020L);byte[] bytes=Arrays.copyOfRange(image,offset,offset+(int)n);e.writeMemory(toAddr(dst),bytes);e.writeMemory(toAddr(dst-0x40000000L),bytes);storageReads++;trace.add("MODEL:section-storage-and-cache-alias:"+Long.toHexString(dst)+":"+n);decodeCache.clear();e.writeRegister("D0",0);return true;}
  return super.external(t);
 }
 void load(int section,int fill)throws Exception{
  long lo=section==1?0x60134000L:0x60828000L,hi=section==1?0x6031f000L:0x60a8f800L;byte[] poison=new byte[(int)(hi-lo)];Arrays.fill(poison,(byte)fill);e.writeMemory(toAddr(lo),poison);decodeCache.clear();e.writeRegister("D0",section);runNative(0x60045ed5L,0xf0,0x14);check((u32(0xa32de590L)&(1L<<(section-1)))!=0,"Loaded bit missing");check(Arrays.equals(e.readMemory(toAddr(lo),(int)(hi-lo)),Arrays.copyOfRange(image,(int)(lo-0x60021020L),(int)(hi-0x60021020L))),"Whole section load differs");
 }
 void residentEvent(long ev,int scp,boolean half,boolean on)throws Exception{
  e.writeRegister("D0",ev);runNative(packedEntry,0,0);int mode=on?0:scp;check(u8(DATA)==(half?1:0)&&u8(DATA+1)==(on?1:0)&&u8(DATA+5)==0&&u8(DATA+7)==0,"Resident held/status state");check(u8(DATA+4)==(on?2:half?1:0)&&u8(0x62a6a0ebL)==mode,"Resident ownership/mode");check(u8(0xa33a1d10L)==(mode==0?0:1),"Resident worker state");if(mode!=0)check(u8(0xa33a1d14L)==mode,"Resident worker class");long bank=dataAddress(BANKS)+(on?0x100:0)+16*u8(DATA+16);check(Arrays.equals(e.readMemory(toAddr(bank),10),e.readMemory(toAddr(0xa33ca384L),10)),"Resident active cache");
 }
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary resident probe source mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  try{for(int scp=0;scp<=6;scp++){profileInit(scp,out);try{prepareResident(out);load(1,0xa5);load(4,0x55);check(storageReads==2,"Storage read count");residentEvent(HP,scp,true,false);residentEvent(AP,scp,true,true);residentEvent(AR,scp,true,false);residentEvent(HR,scp,false,false);results.add("PASS camera-address code/data placement, SCP="+scp+": native section 1/4 load, descriptor indexing, end selector, uncached-address helper and loaded bits; four native profile transitions after full poisoned-section replacement; storage/cache alias modeled");
   targetSettings(0);setting(0x88b2,0,100);e.writeRegister("D0",0);e.writeRegister("D1",0);runNative(packedCapture,0,0);residentEvent(HP,scp,true,false);check(u16(0xa33ca384L)==100,"Resident capture");load(4,0xa5);residentEvent(0,scp,true,false);check(u16(0xa33ca384L)==100,"Code reload lost retained section-1 data");results.add("PASS code-section reload retains separately placed captured profile, SCP="+scp);
   load(1,0x55);residentEvent(HP,scp,true,false);check(u16(0xa33ca384L)==526,"Data-section initial profile restoration");results.add("BOUNDARY data-section reload restores image defaults and loses volatile frame 100, SCP="+scp+"; persistence and concurrent reload ownership are not established");Files.write(out.resolve("resident-trace-"+scp+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("resident-results.txt"),results);println("RESIDENT PROOF: 14 PASS, 7 BOUNDARY");
  }catch(Exception ex){Files.write(out.resolve("resident-results.txt"),results);Files.write(out.resolve("resident-last-trace.txt"),trace);Files.writeString(out.resolve("resident-failure.txt"),ex.toString());throw ex;}
 }
}
