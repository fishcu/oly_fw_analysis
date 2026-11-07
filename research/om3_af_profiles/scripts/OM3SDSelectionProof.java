// Stock OM-3 SD client and candidate-selection probes. No device or update output.
// Filesystem enumeration, file metadata and task services are explicit models.
// @category OM3
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
public class OM3SDSelectionProof extends OM3NativeQueue {
 int attributes, metadataCalls, absent; boolean client; List<String> patterns=new ArrayList<>();
 static final long CTX=0x700b0000L,OBJ=0x700b0100L,NAME=0x700b0200L,SLOT=0x700b0300L;
 static class Stopped extends Exception {Stopped(String s){super(s);}}
 String string(long a)throws Exception {byte[] b=e.readMemory(toAddr(a),80);int n=0;while(n<b.length&&b[n]!=0)n++;return new String(b,0,n,StandardCharsets.US_ASCII);}
 @Override boolean external(long t)throws Exception {
  if(!client){
   if(t==0x608c05eaL){check(reg("A0")==OBJ,"Attributes object");e.writeRegister("D0",attributes);return true;}
   if(t==0x60023c05L||t==0x608c068cL||t==0x608c078bL){check(reg("A0")==OBJ,"Metadata object");metadataCalls++;e.writeRegister("D0",t==0x60023c05L?77:t==0x608c068cL?12345:88);return true;}
  } else {
   if(t==0x60023c05L){e.writeRegister("D0",100);return true;}
   if(t==0x60023d68L||t==0x60023f59L)return true;
   if(t==0x6106d821L){check(reg("D0")==0,"SD initial controller argument");trace.add("MODEL:controller-command-acknowledgement:0");return true;}
   if(t==0x6106be04L||t==0x6106bdc4L){e.writeRegister("D0",0);trace.add("MODEL:filesystem-initialization-and-mount");return true;}
   if(t==0x6106be34L){long p=reg("A0");check(string(u32(p+4)).equals("DCOLYMP    "),"SD directory");patterns.add(string(u32(p+8)));e.writeRegister("D0",absent);return true;}
   if(t==0x600254cbL){check(reg("D0")==3,"No-file exit argument");throw new Stopped("native no-file exit reached before update service submission");}
   if(t==0x6004d171L)throw new Exception("Unexpected update service submission in no-file test");
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();
  String[] suffixes={"0000","0001","1100","9999","AAAA","ffff"};long[] previous={0,0x1100,0x9999};
  for(String suffix:suffixes)for(long prior:previous)for(int attr:new int[]{0,2,0x10,0x20}){
   init();try{client=false;attributes=attr;metadataCalls=0;trace.clear();
    e.writeMemoryValue(toAddr(SLOT),4,CTX);e.writeMemoryValue(toAddr(OBJ+4),4,NAME);e.writeMemoryValue(toAddr(OBJ+8),4,0x60023c05L);
    e.writeMemory(toAddr(NAME),("E147"+suffix+"BIN\0").getBytes(StandardCharsets.US_ASCII));
    long[] before={900,901,prior,902};for(int i=0;i<4;i++)e.writeMemoryValue(toAddr(CTX+28+i*4),4,before[i]);
    e.writeRegister("A0",SLOT);e.writeRegister("A1",OBJ);runNative(0x6106bec6L,0,0);
    boolean chosen=(attr&0x1e)==0&&Long.parseLong(suffix,16)>prior;long[] expected=chosen?new long[]{12345,77,Long.parseLong(suffix,16),88}:before;
    for(int i=0;i<4;i++)check(u32(CTX+28+i*4)==expected[i],"Candidate fields differ "+suffix+":"+prior+":"+attr);
    check(metadataCalls==(chosen?3:0),"Unexpected metadata calls");results.add("PASS native candidate selection suffix="+suffix+", previous="+Long.toHexString(prior)+", attributes="+Integer.toHexString(attr)+", selected="+chosen+"; modeled file metadata, enumeration prefilters model/name");
   }finally{e.dispose();}
  }
  for(int missing:new int[]{0xe00,0xe0c}){init();try{client=true;absent=missing;patterns.clear();trace.clear();
   List<String> expected=new ArrayList<>();for(int row=0;row<11;row++){long descriptor=0x612ea1ecL+20*row,n=u32(descriptor+12),array=u32(descriptor+8);check(n>0&&n<=8,"Pattern count");for(int i=0;i<n;i++)expected.add(string(u32(array+4*i)));}
   try{runNative(0x6106b87aL,0,0);throw new Exception("Client unexpectedly returned");}catch(Stopped stop){check(patterns.equals(expected),"Pattern scan differs "+patterns);check(patterns.contains("E147????BIN"),"OM-3 body pattern absent");results.add("PASS native SD client all 11 descriptor rows, missing="+Integer.toHexString(missing)+", patterns="+patterns+"; native no-file exit before service submission; filesystem/mount/controller modeled, physical entry not tested");}
   Files.write(out.resolve("sd-no-file-trace-"+Integer.toHexString(missing)+".txt"),trace);
  }finally{e.dispose();}}
  Files.write(out.resolve("sd-selection-results.txt"),results);println("SD SELECTION: "+results.size()+" PASS; no device access or flash writes; physical entry and update acceptance unproved");
 }
}
