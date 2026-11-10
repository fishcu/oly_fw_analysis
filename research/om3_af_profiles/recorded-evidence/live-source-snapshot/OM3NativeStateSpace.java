// Exhaustive finite button-state edges under stock S-AF and C-AF setting values.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3NativeStateSpace extends OM3NativeProfiles {
 @Override public void run()throws Exception{
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  int tx=currentProgram.startTransaction("Temporary state-space mapping; discarded read-only");try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_controller",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}finally{currentProgram.endTransaction(tx,true);}
  try{for(int focus:new int[]{0,2})for(int scp=0;scp<=6;scp++){profileInit(scp,out);try{
   setting(0xc021,0,focus);byteAt(0xa33f2c9dL,focus);event(0,scp,false,false);
   for(int state=0;state<4;state++)for(int edge=0;edge<4;edge++){
    event(HR,scp,false,u8(S+1)==1);event(AR,scp,false,false);boolean half=(state&1)!=0,on=(state&2)!=0;if(half)event(HP,scp,true,false);if(on)event(AP,scp,half,true);
    if(edge==0)half=true;else if(edge==1)half=false;else if(edge==2)on=true;else on=false;
    event(new long[]{HP,HR,AP,AR}[edge],scp,half,on);check(settings.get(0xc0210000L)==focus&&u8(0xa33f2c9dL)==focus,"Shared S-AF/C-AF setting/context changed");
   }
   results.add("PASS all 16 button-state/event edges, SCP="+scp+", MODE_FOCUS="+focus+" ("+(focus==0?"S-AF":"C-AF")+"); shared setting/context retained; native target/snapshot, detection decision and worker state checked for each edge");Files.write(out.resolve("native-state-space-trace-"+focus+"-"+scp+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("native-state-space-results.txt"),results);println("NATIVE STATE SPACE: "+results.size()+" PASS, 224 exhaustive finite edges");
  }catch(Exception ex){Files.write(out.resolve("native-state-space-results.txt"),results);Files.write(out.resolve("native-state-space-last-trace.txt"),trace);Files.writeString(out.resolve("native-state-space-failure.txt"),ex.toString());throw ex;}
 }
}
