// Execute the stock section-6 constructor group once, instead of a selective
// list of framework initializers. The default harness behavior is preserved in
// the parent initialization seams; this variant replaces only those seams.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3ProtocolConstructorGroupProof extends OM3Queue10WorkerProof {
 boolean groupInProgress,groupComplete;
 final Set<Long> groupAddresses=new LinkedHashSet<>();
 final Map<Long,Integer> groupVisits=new LinkedHashMap<>();
 @Override void coreFixture()throws Exception {
  super.coreFixture();
  check(u32(0x6021541cL)==0x60f1a6b4L&&u32(0x60215412L)==0xc4,"Stock section-6 constructor group fingerprint");
  // Pool constructors are section 2, which precedes section 6 in stock startup.
  check(u32(0x602153f2L)==0x60718770L,"Stock section-2 pool constructor group fingerprint");
  runNative(0x602153e6L,0xa0,0xc);poolCtorsEmulator=e;
  for(int i=0;i<49;i++)groupAddresses.add(u32(0x60f1a6b4L+4*i));
  check(groupAddresses.size()==49,"Constructor table entries must be unique");
  groupInProgress=true;
  try{runNative(0x60215410L,0xa0,0xc);}finally{groupInProgress=false;}
  check(groupVisits.size()==49,"Every stock section-6 constructor must execute");
  check(u16(0x62b756bcL)==0x26c&&u16(0x62b74d54L)==0x269,"Native framework type-key initialization");
  check(u32(0x6036c024L)==0xffffffffL&&u32(0x6036c028L)==0x60c7100aL&&
        u32(0x6036c548L)==0xffffffffL&&u32(0x6036c54cL)==0x60c70675L&&
        u32(0x6036d17cL)==0xffffffffL&&u32(0x6036d180L)==0x60d28814L,
        "Representative native member-function descriptors must be initialized");
  groupComplete=true;
  note("CONSTRUCTOR-GROUP completed 49 stock section-6 constructors after 13 stock section-2 pool constructors");
  Files.writeString(Paths.get(getScriptArgs()[0]).resolve("constructor-group-proof.txt"),
   "Native group 60215410; ROM table 60f1a6b4; 49 unique entries observed.\nRepresentative member-function descriptors verified at 6036c024, 6036c548, 6036d17c.\nVisits: "+groupVisits+
   String.format("\nSubtype key=%04x; request key=%04x\nNo completion event, reply or active/requested backend field supplied.\n",u16(0x62b756bcL),u16(0x62b74d54L)));
 }
 @Override void prepareMainThreadStorage()throws Exception {
  check(groupComplete&&u8(0x6036d700L)==1&&u32(0x62b76554L)==0x60f19b98L,"Preserve the singleton already constructed by native group");
  trace.add("STOCK-INIT:preserving native main-thread singleton; no post-constructor fixture zeroing");
 }
 @Override void initializeFrameworkStatics()throws Exception {
  check(groupComplete,"Framework construction requires the completed stock initializer group");
  trace.add("STOCK-INIT:framework statics already initialized by group 60215410; no duplicate harness constructor calls");
 }
 @Override void initializeReceiverStatics()throws Exception {
  check(groupComplete,"Receiver construction requires the completed stock initializer group");
  trace.add("STOCK-INIT:receiver statics already initialized by group 60215410; no duplicate harness constructor calls");
 }
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(groupInProgress&&groupAddresses.contains(pc))groupVisits.merge(pc,1,Integer::sum);
  if(pc==0x60dcc872L)note(String.format("SUBTYPE-ROUTING obj=%08x key=%04x incoming=%04x",reg("A0"),u16(0x62b756bcL),u16(reg("A1")+4)));
  if(pc==0x60dcc889L)note(String.format("SUBTYPE-CLASS-RESULT result=%x",reg("D0")));
  return super.instruction(ins);
 }
}

