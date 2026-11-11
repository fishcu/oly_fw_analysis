// Reproducible consolidated suite; Ghidra project must be opened read-only.
// @category OM3
import ghidra.app.script.GhidraScript;
import java.nio.file.*;
import java.util.*;
public class OM3OfflineSuite extends GhidraScript {
 public void run()throws Exception{
  String[] scripts={"OM3NativeFlow.java","OM3NativeQueue.java","OM3NativeLifecycle.java","OM3NativeProfiles.java","OM3NativeHooks.java","OM3NativeFaults.java","OM3NativeStateSpace.java"};
  String[] files={"native-flow-results.txt","native-queue-results.txt","native-lifecycle-results.txt","native-profile-results.txt","native-hook-results.txt","native-fault-results.txt","native-state-space-results.txt"};int[] expected={4,6,6,28,4,4,14};
  Path out=Paths.get(getScriptArgs()[0]);List<String> all=new ArrayList<>();
  for(int i=0;i<scripts.length;i++){runScript(scripts[i],getScriptArgs());List<String> lines=Files.readAllLines(out.resolve(files[i]));if(lines.size()!=expected[i]||lines.stream().anyMatch(s->!s.startsWith("PASS ")))throw new Exception("Failed suite "+scripts[i]);all.add(scripts[i]+": "+lines.size()+" PASS");}
  Files.write(out.resolve("offline-suite-results.txt"),all);println("OFFLINE SUITE: 66 PASS; explicit models and boundaries remain");
 }
}
