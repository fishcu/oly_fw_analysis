// Route the original button edges through the stock GUI event engine instead of calling the feature wrappers directly.
// Background (twenty-second follow-up): after the first AF-ON release, state word 0x62b7f7b4 stays set and later AF-ON
// presses fail permission check 6108ad0a/6108b9c6. The release writes follow-up event 0x0400001c into the handler
// context's pending slot (+0xb0/+0xb4, kind at +0xc0); its handlers would clear the word. The harness invoked the
// feature's table wrappers directly, so the stock engine never ran.
// This probe applies the feature as designed (OFFLINE-AF-PROOF.md "native table wrappers"): the four shooting-table
// handler fields (state 0x5100 table 0x6131bd50; records 6131bd50 half press, 6131bd60 half release, 6131c290 AF-ON
// press, 6131c2a0 AF-ON release; handler at +0xc) are redirected in emulator memory to the same resident wrappers,
// which run the profile transaction and continue into the unchanged original handlers. Each edge is then delivered to
// the stock engine 0x610beb04 (GUI state-machine class vtable 0x6133a46c slot +8; A0 = machine 0x700b6000 initialized by
// stock 0x610b9eb7, A1 = the existing context, current event at context+0, D0 = event).
// Recorded after each edge: context +0xb0/+0xb4/+0xc0, state word 0x62b7f7b4, whether the wrapper/original ran.
// Nothing is cleared or supplied; the only memory change beyond the inherited fixtures is the feature's table redirect.
// Disable routing with -Dom3.directWrappers for the af-startup-consumer4 baseline.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3EngineRoutedConsumerProof extends OM3AFStartupConsumerProof {
 static final long MACHINE=0x700b6000L,CTX=0x700b5000L,ENGINE=0x610beb04L,STATE_WORD=0x62b7f7b4L;
 static final long[][] RECORDS={{0x6131bd50L,0x01000002L,0x610b9197L,0},{0x6131bd60L,0x01000003L,0x610b96f0L,1},{0x6131c290L,0x01050007L,0x610b962aL,2},{0x6131c2a0L,0x01050008L,0x610b9653L,3}};
 final List<String> engineLog=new ArrayList<>();
 final Map<Long,Long> wrapperByEvent=new HashMap<>();
 boolean redirected;int edge;
 void elog(String s){trace.add(s);engineLog.add(s);}
 String slot(){try{return String.format("ctx+b0=%08x +b4=%08x +c0=%08x state-word=%08x machine+ac=%x +b8=%x",u32(CTX+0xb0),u32(CTX+0xb4),u32(CTX+0xc0),u32(STATE_WORD),u32(MACHINE+0xac),u32(MACHINE+0xb8));}catch(Exception ex){return "unreadable "+ex;}}
 void redirect()throws Exception {
  if(redirected)return;redirected=true;
  for(long[] r:RECORDS){
   String seen;try{seen=String.format("%08x %08x %08x %08x",u32(r[0]),u32(r[0]+4),u32(r[0]+8),u32(r[0]+12));}catch(Exception ex){seen="unreadable "+ex;}
   elog(String.format("TABLE-RECORD-RUNTIME %08x expect event=%08x handler=%08x seen=%s",r[0],r[1],r[2],seen));
   if(!(u32(r[0])==r[1]&&u32(r[0]+12)==r[2])){
    for(long a=r[0]-0x200;a<=r[0]+0x200;a+=4){try{if(u32(a)==r[1]&&u32(a+12)==r[2])elog(String.format("TABLE-RECORD-FOUND-NEARBY %08x",a));}catch(Exception ex){}}
   }
   long wrapper=translated(CODE+0x900+128*r[3]);wrapperByEvent.put(r[1],wrapper);
   long handler=u32(r[0]+12);
   check(u32(r[0])==r[1]&&(handler==r[2]||handler==wrapper),String.format("Stock shooting-table record %08x seen %s (wrapper %08x)",r[0],seen,wrapper));
   if(handler==wrapper){
    // engine-routed2: the inherited resident preparation (prepareResident) already installs this redirect.
    elog(String.format("FEATURE-TABLE-REDIRECT already installed by inherited resident preparation record=%08x event=%08x -> wrapper=%08x (original %08x)",r[0],r[1],wrapper,r[2]));
   }else{
    e.writeMemoryValue(toAddr(r[0]+12),4,wrapper);
    elog(String.format("FEATURE-TABLE-REDIRECT applied record=%08x event=%08x original=%08x -> wrapper=%08x",r[0],r[1],r[2],wrapper));
   }
  }
 }
 // engine-routed3: the engine consults the machine's secondary state (+0xb8) table before the shooting state (+0xac).
 // The inherited fixture value 0x5a05 (first written in OM3ShootingRuntime, provenance undocumented) selects table
 // 0x61333858, whose first record handles half press with 0x610b10b6 and which has no AF-ON or half-release records:
 // an overlay state in which half press is consumed before the shooting table. Stock 610bfc0a returns no table for a
 // state below 0x5000 and the engine skips null tables, so "no secondary state" is representable. FIXTURE (labelled):
 // secondary state = -Dom3.secondaryState (default 0 = none) after the stock machine init; shooting state 0x5100 kept.
 boolean secondarySet;
 @Override void beforeNativeButton(long event)throws Exception {
  super.beforeNativeButton(event);
  if(!secondarySet&&System.getProperty("om3.directWrappers")==null){
   secondarySet=true;long v=Long.decode(System.getProperty("om3.secondaryState","0"));
   elog(String.format("FIXTURE:machine secondary state +0xb8 %x -> %x (shooting state +0xac=%x kept)",u32(MACHINE+0xb8),v,u32(MACHINE+0xac)));
   e.writeMemoryValue(toAddr(MACHINE+0xb8),4,v);
  }
  if(System.getProperty("om3.directWrappers")==null)redirect();
  elog(String.format("EDGE %d BEFORE event=%08x %s",edge,event,slot()));
 }
 @Override void runNative(long entry,int mask,int frame)throws Exception {
  Long event=null;
  if(redirected&&mask==0&&frame==0)for(var en:wrapperByEvent.entrySet())if(en.getValue()==entry)event=en.getKey();
  if(event==null){super.runNative(entry,mask,frame);return;}
  // Same registers the direct call had (A1 = context with event at +0, D0 = event); A0 becomes the stock machine.
  check(u32(CTX)==event&&reg("A1")==CTX,"Engine route: context must carry the edge event");
  e.writeRegister("A0",MACHINE);
  elog(String.format("ENGINE-ROUTE edge=%d event=%08x engine=%08x machine-vt=%08x",edge,event,ENGINE,u32(MACHINE)));
  int before=trace.size();
  super.runNative(ENGINE,0,0);   // explicit prologue (movm [d2,d3,a2,a3]; add -0x34)
  boolean wrapperRan=false,origRan=false;long orig=0;for(long[] r:RECORDS)if(r[1]==event)orig=r[2];
  for(int i=before;i<trace.size();i++){String t=trace.get(i);if(t.equals("native-call:"+Long.toHexString(orig)))origRan=true;}
  elog(String.format("EDGE %d AFTER event=%08x original-handler-called=%s %s",edge,event,origRan,slot()));
  for(long sa:followSlots){try{elog(String.format("  FOLLOWUP-SLOT %08x now=%08x +4=%08x",sa,u32(sa),u32(sa+4)));}catch(Exception ex){}}
  edge++;
 }
 // engine-routed4 follow-up observation: 61088066 stores the follow-up event 0x0400001c with "mov D0,(A0)" at
 // 610880c1 (A0 = arg+0xb0) or "mov D0,(A2)" at 61088180 (A2 = arg+0xb0). Record the slot address and watch it.
 final Set<Long> followSlots=new LinkedHashSet<>();
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc==0x610880c1L||pc==0x61088180L){long slotAddr=pc==0x610880c1L?reg("A0"):reg("A2");followSlots.add(slotAddr);
   elog(String.format("FOLLOWUP-STORE pc=%08x slot=%08x event=%08x (object=%08x; harness ctx=%08x machine=%08x)",pc,slotAddr,reg("D0"),slotAddr-0xb0,CTX,MACHINE));}
  for(var en:wrapperByEvent.entrySet())if(pc==en.getValue()&&redirected)elog(String.format("ENGINE-CALLED-WRAPPER event=%08x pc=%08x",en.getKey(),pc));
  return super.instruction(ins);
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   engineLog.add("FINAL "+slot());
   Files.write(Paths.get(getScriptArgs()[0]).resolve("engine-route-log.txt"),engineLog);
  }
 }
}
