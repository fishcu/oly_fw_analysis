// Additional native probes. Fixture adapters and stop boundaries are explicit.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3PrehardwareContracts extends OM3RevisionChecks {
 void mapped()throws Exception{int tx=currentProgram.startTransaction("Temporary additional probe mapping; discarded");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}}
 void rectangle()throws Exception{int x0=u16(SNAPSHOT+24),x1=u16(SNAPSHOT+26),y0=u16(SNAPSHOT+28),y1=u16(SNAPSHOT+30);check(x0<=x1&&y0<=y1&&x1<=639&&y1<=479,"Invalid native search rectangle: "+x0+","+x1+","+y0+","+y1);}
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();mapped();
  try{
   // The stock four-byte converter and ten-byte refresh are separately native.
   // This explicitly supplies the still-unresolved UI-to-internal setting bridge.
   int[] kinds={2,0,3,3,0,3,7,7,7,7,3};
   for(int type=0;type<=10;type++){profileInit(6,out);try{
    for(int i=0;i<10;i++)setting(0x1dd1,i,i<2?1:(i%2==0?5:7));for(int i=0;i<8;i++)setting(0x1df1,i,0);
    long p=0x700b6000L;e.writeRegister("A0",p);e.writeRegister("D0",type);runNative(0x609b3ecdL,0xe0,0x14);byte[] d=e.readMemory(toAddr(p),4);check((d[0]&255)==kinds[type],"Stock converter kind");
    targetSettings(0);setting(0x84d1,0,d[0]&255);setting(0x1dd1,0,d[1]&255);setting(0x1dd1,1,d[2]&255);setting(0x1df1,0,d[3]&255);captureStock(0,0);revisedEvent(HP);expected(true,false,6);rectangle();
    byte[] captured=e.readMemory(toAddr(BANKS),10);check((captured[2]&255)==kinds[type]&&u16(BANKS+4)==(d[1]&255)&&u16(BANKS+6)==(d[2]&255),"Captured descriptor");
    e.writeRegister("A0",p+16);e.writeRegister("A1",p+18);runNative(0x6095be40L,0x30,0xc);check(u16(p+16)==(d[2]&255)&&u16(p+18)==(d[1]&255),"Active dimensions consumer");
    e.writeRegister("D0",0);e.writeRegister("D1",0);runNative(0x60905296L,0xf0,0x34);int classified=kinds[type]==0?5:kinds[type]==2?4:((d[1]&255)<12&&(d[2]&255)<16?7:4);check(reg("D0")==classified,"Active-zone presentation classification");
    for(int button=0;button<2;button++)for(int ori=0;ori<3;ori++){setting(0x88b2,0,100+40*button+ori);captureStock(button,ori);byteAt(S+16,ori);revisedEvent(button==1?AP:AR);expected(true,button==1,button==1?0:6);rectangle();}
    results.add("PASS stock enum="+type+": native four-byte conversion, supplied setting bridge, native ten-byte capture/activation in both buttons x three supplied orientation banks, bounded search rectangle, active dimensions consumer and presentation classifier");Files.write(out.resolve("stock-type-trace-"+type+".txt"),trace);
   }finally{e.dispose();}}
   for(int frame:new int[]{0,38,526,1014,1052})for(int priority:new int[]{0,1}){profileInit(6,out);try{
    revisedEvent(HP);for(int[] dim:new int[][]{{1,1},{3,5},{9,13},{27,39}}){targetSettings(0);setting(0x88b2,0,frame);setting(0x1dd1,0,dim[0]);setting(0x1dd1,1,dim[1]);setting(0x1df1,0,priority);setting(0x1e01,0,1);captureStock(0,0);revisedEvent(0);expected(true,false,6);rectangle();check(u16(0xa33ca384L)==frame&&u8(0xa33ca38cL)==(dim[0]==3?0:priority)&&u8(0xa33ca38dL)==1,"Movement/priority/CAF fields lost");}
    results.add("PASS same-owner native recapture at frame="+frame+", priority="+priority+", four dimensions and CAF-start flag; stock three-row priority normalization, cache and search rectangle checked");
   }finally{e.dispose();}}
   for(int mode=1;mode<=6;mode++){profileInit(mode,out);try{
    revisedEvent(HP);byte[] old=new byte[356];for(int i=0;i<old.length;i++)old[i]=(byte)(i*13+7);long p=0x700b8000L;e.writeMemory(toAddr(p),old);revisedEvent(AP);byte[] stopped=e.readMemory(toAddr(0xa33a7de0L),356);
    e.writeRegister("A0",p);boolean rejected=false;try{runNative(0x6087215eL,0xf0,0x40);}catch(Exception ex){check(ex.toString().contains("3106001e"),"Unexpected publisher failure "+ex);rejected=true;}check(rejected&&Arrays.equals(stopped,e.readMemory(toAddr(0xa33a7de0L),356)),"Stopped publisher copied stale input");
    results.add("PASS native outer publisher rejects supplied result while stopped, class="+mode+", diagnostic 3106001e before changing 356-byte buffer");
    revisedEvent(AR);e.writeRegister("A0",p);breakpoints.add(0x608721f6L);hitBreakpoint=0;try{runNative(0x6087215eL,0xf0,0x40);}finally{breakpoints.clear();}check(hitBreakpoint==0x608721f6L&&Arrays.equals(old,e.readMemory(toAddr(0xa33a7de0L),356)),"Restart publisher copy boundary");
    results.add("BOUNDARY restarted outer publisher accepts supplied old bytes into its copy stage, class="+mode+"; no generation check before copy; caller/hardware provenance and downstream selection remain unproven");Files.write(out.resolve("late-publisher-trace-"+mode+".txt"),trace);
   }finally{e.dispose();}}
   profileInit(6,out);try{
    targetSettings(0);setting(0x88b2,0,100);captureStock(0,0);byte[] saved=e.readMemory(toAddr(BANKS),10);revisedEvent(HP);byteAt(0xa33f2ceaL,1);e.writeMemory(toAddr(0xa33f2ce0L),new byte[10]);e.writeRegister("D0",3);runNative(0x609029f1L,0xb0,0x14);check(Arrays.equals(saved,e.readMemory(toAddr(0xa33ca384L),10)),"Dirty refresh did not retain bank");
    results.add("PASS native dirty target refresh retains captured profile after ordinary stock target RAM changes; no display rendering or custom-mode recall claimed");
    byteAt(S+16,3);revisedEvent(0);check(u8(S+5)==7&&u8(S+7)==0,"Invalid orientation admission");results.add("PASS invalid orientation-bank input is rejected and unlocks native guard");
   }finally{e.dispose();}
   for(int enabled=0;enabled<2;enabled++)for(int kind:new int[]{2,4}){profileInit(6,out);try{
    long object=0x700b7000L;e.writeRegister("A0",object);e.writeRegister("A1",0x700b7100L);e.writeRegister("D0",enabled);e.writeRegister("D1",kind);e.writeMemoryValue(toAddr(stackTop+4),4,2);runNative(0x60af491fL,0xc0,0xc);check(u32(object)==0x60dfd0e0L&&u16(object+4)==0x5e9&&u32(object+32)==enabled&&u32(object+36)==kind&&u32(object+40)==2,"Native AFL request construction");
    results.add("PASS native shooting request constructor: ID=5e9, enabled="+enabled+", kind="+kind+", context fields retained; provided allocation buffer, transaction dispatch and lens completion excluded");
   }finally{e.dispose();}}
   profileInit(6,out);try{check(u16(BANKS)==526,"Fresh fixture default");results.add("BOUNDARY fresh initialization restores baseline profile rather than prior captured frame 100; current prototype has no persistent bank storage or camera reset/recall hook");}finally{e.dispose();}
   profileInit(6,out);try{
    observedStackLow=0xffffffffL;revisedEvent(HP);revisedEvent(AP);revisedEvent(AR);long low=observedStackLow;check(low>=0x70040000L,"Fixture stack region exhausted");
    int controller=controller().length,reconcile=reconcile().length,capture=capture().length;int wrappers=0;for(int i=0;i<4;i++)wrappers+=wrapper(CODE+0x900+i*0x80,new long[]{HP,HR,AP,AR}[i],new long[]{0x610b9197L,0x610b96f0L,0x610b962aL,0x610b9653L}[i]).length;
    results.add("PASS observed synthetic-stack bound across native start/stop/restart: lowest SP="+Long.toHexString(low)+"; independent child stacks supplied by scheduler model, not measured camera task stack");
    results.add("BOUNDARY revision component sizes controller="+controller+", reconcile="+reconcile+", capture="+capture+", wrappers="+wrappers+" bytes; sparse mapped span=4096 bytes; RAM addresses are fixtures, no allocator reservation or deployable relocation established");
   }finally{e.dispose();}
   Files.write(out.resolve("additional-contract-results.txt"),results);println("ADDITIONAL CONTRACTS: "+results.size()+" records");
  }catch(Exception ex){Files.write(out.resolve("additional-contract-results.txt"),results);Files.write(out.resolve("additional-contract-last-trace.txt"),trace);Files.writeString(out.resolve("additional-contract-failure.txt"),ex.toString());throw ex;}
 }
}
