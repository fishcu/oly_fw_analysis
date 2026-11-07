// Audit reconciliation after an external lifecycle reset, not an emulated sleep.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3WakeAudit extends OM3RevisionChecks {
 String resultName(){return "wake-audit-results.txt";}
 @Override public void run()throws Exception{Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();mapped();for(int mode=1;mode<=6;mode++){profileInit(mode,out);try{revisedEvent(HP);stop();check(u8(0xa33a1d10L)==0,"Stock stop");revisedEvent(0);boolean restored=u8(0xa33a1d10L)==1&&u8(0xa33a1d14L)==mode;results.add((restored?"PASS ":"REPRODUCED ")+"external lifecycle reset with unchanged held/profile state, class="+mode+": native reconcile worker running="+restored+"; actual sleep/wake dispatcher excluded");}finally{e.dispose();}}Files.write(out.resolve(resultName()),results);for(String r:results)println(r);}
 void mapped()throws Exception{int tx=currentProgram.startTransaction("Temporary wake audit mapping");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}}
}
