// Separate target-size field is not represented by the four-byte enum converter.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3TargetSizeProof extends OM3RevisionChecks {
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();int tx=currentProgram.startTransaction("Temporary size-field probe mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  for(int button=0;button<2;button++)for(int size=0;size<2;size++){profileInit(6,out);try{
   targetSettings(0);setting(0x84d1,0,0);setting(0x9a41,0,size);captureStock(button,0);revisedEvent(HP);if(button==1)revisedEvent(AP);expected(true,button==1,button==1?0:6);long bank=BANKS+(button==1?0x100:0);check(u8(bank+3)==size&&u8(0xa33ca387L)==size,"Separate size field lost");int[] r={u16(SNAPSHOT+24),u16(SNAPSHOT+26),u16(SNAPSHOT+28),u16(SNAPSHOT+30)};check(r[0]<=r[1]&&r[2]<=r[3]&&r[1]<=639&&r[3]<=479,"Target-size rectangle bounds");
   results.add("PASS button="+button+", supplied target-size value="+size+": native stock capture, cache and snapshot rectangle="+Arrays.toString(r)+"; actual UI enum-to-size mapping remains unproved");Files.write(out.resolve("target-size-trace-"+button+"-"+size+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("target-size-results.txt"),results);println("TARGET SIZE: 4 PASS");
 }
}
