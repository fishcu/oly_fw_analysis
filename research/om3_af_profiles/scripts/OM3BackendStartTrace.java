// Observe one stock-reset connection, then stop deliberately before button execution.
// No event, reply, backend pointer or component state is synthesized by this subclass.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3BackendStartTrace extends OM3CaptureAfTaskProof {
 final List<String> backendTrace=new ArrayList<>(); boolean snapshotComplete;
 void note(String s){backendTrace.add(s);}
 String state(long p){try{return String.format("obj=%08x vt=%08x life=%d state=%d parent=%08x event=%08x",p,u32(p),u32(p+0xb0),u32(p+0xb4),u32(p+0xa8),u32(p+0x68));}catch(Exception ex){return "obj="+Long.toHexString(p)+" unprovided "+ex;}}
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc==0x60cb8f68L||pc==0x60c6a0ebL){long m=reg("A1");note(String.format("BACKEND-HANDLER pc=%08x %s msg=%08x type=%04x key=%04x",pc,state(reg("A0")),m,u16(m+4),u16(0x62b74d54L)));}
  if(pc==0x60c6a0feL)note(String.format("BACKEND-CLASS-RESULT result=%x",reg("D0")));
  if(pc==0x60db0fe5L||pc==0x60dba55cL||pc==0x60dbb01aL||pc==0x60daea4bL)note(String.format("START-HANDLER pc=%08x %s",pc,state(reg("A0"))));
  if(pc==0x60db113dL||pc==0x60dba6caL||pc==0x60dbb18eL)note(String.format("ENTER-STATE4 pc=%08x %s",pc,state(reg("A0"))));
  if(pc==0x60dbd12dL||pc==0x60dbd132L||pc==0x60dd96ccL){long m=reg("A1");try{note(String.format("POST pc=%08x target=%08x message=%08x type=%04x source-context=%s",pc,reg("A0"),m,u16(m+4),state(reg("A0"))));}catch(Exception ex){note("POST unprovided "+ex);}}
  if(pc==0x60bbbbd4L||pc==0x60bbbb40L)note(String.format("RESULT-CONSTRUCTOR pc=%08x message=%08x sp=%08x mdr=%08x",pc,reg("A0"),reg("SP"),reg("MDR")));
  return super.instruction(ins);
 }
 @Override void beforeOriginal()throws Exception {
  super.beforeOriginal();
  note(String.format("SNAPSHOT key269-object=%s type=%04x router=%s",hex(0x62b74d50L,0x20),u16(0x62b74d54L),state(0x62b7315cL)));
  for(long p:new long[]{0x62b71778L,0x62b71f9cL,0x62b72f2cL})note("SNAPSHOT "+state(p)+" data="+hex(p,0x180));
  snapshotComplete=true;
  throw new Exception("INTENTIONAL OBSERVATION STOP after first connection; no original button executed by this subclass");
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);
  try{super.run();}finally{
   Files.write(out.resolve("backend-start-observations.txt"),backendTrace);
   Files.writeString(out.resolve("backend-start-outcome.txt"),(snapshotComplete?"OBSERVATION COMPLETE: one labelled stock-reset connection; deliberate stop before button execution":"BOUNDARY before connection snapshot; inspect retained traces")+"\nNo new reply, event, backend pointer or lifecycle state supplied by this subclass.\n");
  }
 }
}
