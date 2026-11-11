// Exercise all four original button edges for each SCP selection 0..6.
// Configuration is supplied through the existing native setting setter;
// backend activation, selection callbacks and original handler bodies stay native.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3OriginalButtonMatrixProof extends OM3ReusingHeapProof {
 int matrixStep,configuredSubject;
 final List<String> matrixResults=new ArrayList<>();
 @Override long[] nativeButtonSequence(){long[] a=new long[28];for(int i=0;i<7;i++){a[4*i]=HP;a[4*i+1]=AP;a[4*i+2]=AR;a[4*i+3]=HR;}return a;}
 @Override String nativeButtonLabel(long event){return super.nativeButtonLabel(event)+" [SCP="+configuredSubject+"]";}
 @Override void beforeNativeButton(long event)throws Exception {
  if(event==HP){
   configuredSubject=matrixStep/4;
   trace.add("SUPPLIED-CONFIGURATION:SCP Subject Detect="+configuredSubject+" via native60063431; UI interaction/timing unproven");
   writeSetting(0x1e71,0,configuredSubject);
  }
 }
 @Override void afterOriginal()throws Exception {
  super.afterOriginal();
  int edge=matrixStep%4,owner=u8(ownedState()+4),subject=u8(0x62a6a0ebL);
  int expectedOwner=new int[]{1,2,1,0}[edge],expectedSubject=edge==1?0:configuredSubject;
  String row=String.format("ORIGINAL-MATRIX SCP=%d edge=%d owner=%d expected-owner=%d effective-subject=%d expected-subject=%d capture-coarse=%d active=%d",configuredSubject,edge,owner,expectedOwner,subject,expectedSubject,u32(0x62b71778L+0xfc),u32(0x62b71778L+0x100));
  matrixResults.add(row);trace.add(row);
  check(owner==expectedOwner&&subject==expectedSubject,"Original button profile/SCP ownership mismatch; see matrix row");
  matrixStep++;
 }
 @Override public void run()throws Exception {
  try{super.run();}finally{
   Path out=Paths.get(getScriptArgs()[0]);
   Files.write(out.resolve("original-button-matrix.txt"),matrixResults);
   String scope="Original button matrix completed edges="+matrixStep+"/28 under supplied native SCP settings0..6, stock-reset/shooting-context fixtures and declared OS/device models. A returning handler/profile check is not physical AF acquisition, valid camera boot or installation safety.\n";
   Files.writeString(out.resolve("original-button-matrix-outcome.txt"),scope);
   Files.writeString(out.resolve("backend-start-outcome.txt"),scope,StandardOpenOption.APPEND);
  }
 }
}
