// Native core setting table registration, scalar getters and pointer bindings.
// ROM defaults are not a dump of the user's nonvolatile settings.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CoreSettingsProof extends OM3NativeQueue {
 static final long META=0xa32a990cL;
 @Override boolean external(long t)throws Exception {if(t==0x60063380L)return false;return super.external(t);}
 long expected(long p,int size,boolean signed)throws Exception {byte[] b=e.readMemory(toAddr(p),size);long v=0;for(int i=0;i<size;i++)v|=(b[i]&255L)<<(8*i);if(signed&&size==1)v=(byte)v;else if(signed&&size==2)v=(short)v;return v&0xffffffffL;}
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();init();try{
   e.writeMemory(toAddr(0xa32a9908L),new byte[0x10004]);
   long[][] tables={{0x60095584L,0x600b8f50L,452},{0x600b8f54L,0x600bb5e0L,544},{0x600bb5ecL,0x600bda6cL,128},{0x600bda78L,0x600e4b54L,204},{0x600e4becL,0x6011fe20L,1215}};
   for(long[] table:tables){e.writeRegister("A0",table[0]);e.writeRegister("A1",0);e.writeRegister("D0",META);runNative(0x60062536L,0xf0,0x30);check(reg("D0")==0,"Registration result");
    long p=table[0];int count=0,reads=0;
    while(p<table[1]){int key=u16(p),n=u16(p+2),width=(key&3)==0?4:key&3;long meta=META+8*(key>>4);
     check(u16(meta)==key&&u16(meta+2)==n&&u32(meta+4)==p+4,"Native metadata mismatch "+Integer.toHexString(key));
     for(int index:new int[]{0,n-1}){e.writeRegister("D0",key);e.writeRegister("D1",index);e.writeRegister("A0",0);runNative(0x60063380L,0xc0,0xc);long value=expected(p+4+(long)index*width,width,(key&8)!=0);check(reg("D0")==value,"Native scalar read mismatch key="+Integer.toHexString(key)+" index="+index);reads++;}
     p=(p+4+(long)n*width+3)&~3L;count++;
    }
    check(p==table[1]&&count==table[2]&&u16(p)==0,"Table extent");results.add("PASS native ROM default registration table="+Long.toHexString(table[0])+", records="+count+", first/last scalar reads="+reads+"; key, count, data pointer, width and signedness checked");
   }
   // The complete stock UI pointer binder now executes against real native core
   // metadata, rather than supplying invented pointers for individual getters.
   runNative(0x60471a7fL,0xe0,0x20);
   for(long[] table:new long[][]{{0x60658adcL,77},{0x60658e78L,54}}){for(int i=0;i<table[1];i++){long record=table[0]+12*i;int key=u16(record),index=u16(record+2),type=u8(record+4),width=(type%3)==0?4:(type%3)==1?2:1;long destination=u32(record+8),pointer=u32(META+(key>>4)*8+4)+index*width;check(u32(destination)==pointer,"Native UI pointer binding "+Long.toHexString(destination));}results.add("PASS native UI setting pointer binder table="+Long.toHexString(table[0])+", entries="+table[1]+"; every binding matches registered core record");}
   Files.write(out.resolve("core-settings-results.txt"),results);Files.write(out.resolve("core-settings-trace.txt"),trace);println("CORE SETTINGS: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("core-settings-last-trace.txt"),trace);Files.writeString(out.resolve("core-settings-failure.txt"),ex.toString());throw ex;}finally{e.dispose();}
 }
}
