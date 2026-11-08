// Continue only through the MMIO read proved irrelevant in status-property1.
// This is a conditional software proof, never an assertion of camera MMIO state.
// @category OM3
import java.nio.file.*;
public class OM3Queue10StatusIndependentProof extends OM3ProtocolConstructorGroupProof {
 int independentReads;
 @Override boolean external(long t)throws Exception {
  if(t==0x600216f2L){
   check(inTask10&&e.getExecutionAddress().getOffset()==0x600644f0L,
     "MMIO independence model restricted to the verified task10 status-builder call");
   check((reg("D2")&255)==0&&u8(0x6299555eL)==0,
     "MMIO result can be ignored only with the observed zero source result");
   // Raw 600644f7..64510 has only zero/nonzero tests of this value. With
   // D2.low == 0, both classes join at 600644fe and return identical bytes.
   // status-property1 executes both classes natively and verifies that join.
   independentReads++;e.writeRegister("D0",0);
   trace.add("MODEL:status-MMIO-value-independent D2.low=0 source=0; representative=0; not observed camera MMIO");
   return true;
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);
   String scope="Conditional MMIO abstraction: getter600216f2 only at600644f0 in task10, with D2.low=0 and source6299555e=0. Both zero/nonzero result classes are equivalent in the verified native builder. Reads="+independentReads+". No claim about the actual camera register.\n";
   Files.writeString(out.resolve("status-independent-model.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
