// Observation-only continuation. Keep the first trace's source and evidence immutable.
// Class layouts differ: backend state is +fc/+100; simple children use +b0/+b4.
// @category OM3
public class OM3BackendNotifyTrace extends OM3BackendStartTrace {
 String backendState(long p) {
  try{return String.format("obj=%08x vt=%08x coarse=%d active=%d current=%08x notify-count=%d",p,u32(p),u32(p+0xfc),u32(p+0x100),u32(p+0x68),u32(p+0xa8));}
  catch(Exception ex){return "unprovided "+ex;}
 }
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc==0x60daec9dL||pc==0x60daf108L||pc==0x60daf7b9L||pc==0x60db08ccL||pc==0x60c6abfbL||pc==0x60cb6779L||pc==0x60db0222L)
   note(String.format("BACKEND-STATE pc=%08x %s",pc,backendState(reg("A0"))));
  if(pc==0x60dbcc7fL||pc==0x60dbcd5bL){
   long p=reg("A0");
   note(String.format("OBSERVER pc=%08x obj=%08x arg=%08x count=%d data=%s arg-data=%s sp=%08x stack=%s",pc,p,reg("A1"),u32(p+0xc),hex(p,0x18),hex(reg("A1"),0x18),reg("SP"),hex(reg("SP"),0x10)));
  }
  if(pc==0x60dbb321L){long p=reg("A0");note(String.format("DONE-CALLBACK obj=%08x target=%08x data=%s",p,u32(p+0x14),hex(p,0x18)));}
  if(pc==0x60cb8f68L)note("BACKEND-EVENT "+backendState(reg("A0"))+String.format(" incoming=%04x",u16(reg("A1")+4)));
  return super.instruction(ins);
 }
}
