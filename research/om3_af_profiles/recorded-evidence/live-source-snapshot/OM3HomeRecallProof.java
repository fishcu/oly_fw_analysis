// Execute stock setHome with enumerated UI property service models.
// These models do not establish flash persistence or property notification delivery.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3HomeRecallProof extends OM3NativeFlow {
 Map<Integer,Long> ui=new HashMap<>();List<Integer> writes=new ArrayList<>(),commits=new ArrayList<>();
 @Override boolean external(long t)throws Exception {
  int id=(int)reg("D0");
  if(t==0x603f039dL){check(ui.containsKey(id),"Unprovided UI property "+Integer.toHexString(id));e.writeRegister("D0",ui.get(id));return true;}
  if(t==0x60ae9fddL){check(ui.containsKey(id),"Unknown UI write");ui.put(id,reg("D1"));writes.add(id);e.writeRegister("D0",0);return true;}
  if(t==0x60aea0a8L){check(ui.containsKey(id)&&reg("D1")==1,"Unknown UI commit");commits.add(id);e.writeRegister("D0",0);return true;}
  if(t==0x60ae7412L){check(id==0,"Unexpected log severity");return true;}
  return super.external(t);
 }
 void recall(long[] values)throws Exception {
  e.writeRegister("D0",values[0]);e.writeRegister("D1",values[1]);e.writeRegister("A1",values[2]);
  for(int i=0;i<3;i++)e.writeMemoryValue(toAddr(stackTop+4+4*i),4,values[3+i]);
  runNative(0x60af3dd1L,0xf0,0x30);check(reg("D0")==1,"Stock Home return");
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  for(int flags=0;flags<64;flags++){
   init();try{ui.clear();writes.clear();commits.clear();
    int lever=flags&1,change=(flags>>1)&1,area=(flags>>2)&1,position=(flags>>3)&1,areaAlt=(flags>>4)&1,posAlt=(flags>>5)&1;
    ui.put(0x216,(long)(lever==1?4:0));ui.put(0x217,(long)change);ui.put(0x540,(long)area);ui.put(0x541,(long)position);ui.put(0x53d,(long)areaAlt);ui.put(0x53e,(long)posAlt);
    int[] normal={0xa3,0x66a,0x66c,0x53a,0x66e,0x670},alternate={0x535,0x66b,0x66d,0x53b,0x66f,0x671};
    for(int i=0;i<6;i++){ui.put(normal[i],(long)(i<3?i:526+i));ui.put(alternate[i],(long)(i<3?10-i:320+i));}
    ui.put(0x205,1L);ui.put(0x70b,0L);ui.put(0x28,3L);ui.put(0x534,2L);ui.put(0x537,1L);ui.put(0x6b1,0L);
    Map<Integer,Long> before=new HashMap<>(ui);int[] selected=new int[6];long[] restore=new long[6],home={10,7,3,100,200,300};Set<Integer> expected=new HashSet<>();
    for(int i=0;i<6;i++){boolean alt=lever==1&&change==1&&(i<3?areaAlt:posAlt)==1;selected[i]=(alt?alternate:normal)[i];restore[i]=ui.get(selected[i]);if((i<3?area:position)==1)expected.add(selected[i]);}
    recall(home);check(writes.size()==expected.size()&&new HashSet<>(writes).equals(expected)&&commits.equals(writes),"Stock copy/commit set differs");
    for(int id:ui.keySet()){long value=before.get(id);for(int i=0;i<6;i++)if(expected.contains(id)&&id==selected[i])value=home[i];check(ui.get(id)==value,"Unexpected property side effect "+Integer.toHexString(id));}
    // Reapplying the exact snapshot through the same native command restores only
    // the enabled selected fields, provided lever/change/enable flags stay fixed.
    writes.clear();commits.clear();recall(restore);check(ui.equals(before),"Stock recall did not restore snapshot");
    results.add("PASS stock setHome flags="+flags+": exact enabled normal/lever alternate fields and commit order; explicit snapshot round trip; target size and focus mode unchanged; UI storage/notification service modeled");
   }finally{e.dispose();}
  }
  Files.write(out.resolve("home-recall-results.txt"),results);println("HOME RECALL: "+results.size()+" PASS; no automatic restore or target-size switch in this command");
 }
}
