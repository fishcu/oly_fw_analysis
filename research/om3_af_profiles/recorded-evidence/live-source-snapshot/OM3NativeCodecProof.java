// Stock update decoder against the host codec permutation; no flash service.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3NativeCodecProof extends OM3NativeQueue {
 static final int[] ORDER={1,3,0,2,6,4,7,5,11,10,9,8,13,14,12,15};
 byte[] encoded(byte[] payload){byte[] result=new byte[payload.length];for(int i=0;i<payload.length;i++)result[(i&~15)+ORDER[i&15]]=(byte)(payload[i]^255);return result;}
 void probe(byte[] payload)throws Exception {
  long p=0x700b0000L;byte[] container=new byte[payload.length+64];Arrays.fill(container,(byte)0x5a);System.arraycopy(encoded(payload),0,container,32,payload.length);e.writeMemory(toAddr(p),container);
  e.writeRegister("A0",p);e.writeRegister("D0",container.length);runNative(0x6106b7dbL,0xf0,0x1c);
  check(reg("D0")==0,"Native decoder rejected aligned payload");check(Arrays.equals(e.readMemory(toAddr(p+32),payload.length),payload),"Native decoder differs from host permutation");
  for(int i=0;i<32;i++)check(u8(p+i)==0x5a&&u8(p+32+payload.length+i)==0x5a,"Decoder changed header/trailer");
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);List<String> results=new ArrayList<>();init();try{
   for(int value=0;value<256;value++){byte[] payload=new byte[16];for(int i=0;i<16;i++)payload[i]=(byte)(value+i);probe(payload);}
   results.add("PASS native 6106b7db decoder: 256 distinct sixteen-byte patterns cover every byte value at every slot; matches host permutation/inversion; header/trailer retained");
   Random r=new Random(1471100);for(int size:new int[]{32,64,4096}){byte[] payload=new byte[size];r.nextBytes(payload);probe(payload);}results.add("PASS native decoder multi-block loop: 32, 64 and 4096 byte deterministic payloads, exact bytes and unchanged header/trailer");
   for(int size:new int[]{0,16,64,65,79,81,95}){long p=0x700b0000L;byte[] before=new byte[128];Arrays.fill(before,(byte)0xa5);e.writeMemory(toAddr(p),before);e.writeRegister("A0",p);e.writeRegister("D0",size);runNative(0x6106b7dbL,0xf0,0x1c);check(reg("D0")==0x3201&&Arrays.equals(before,e.readMemory(toAddr(p),128)),"Malformed decode extent mutated buffer or accepted");}results.add("PASS native decoder rejects seven empty/short/unaligned extents with 3201 before changing memory");
   Files.write(out.resolve("native-codec-results.txt"),results);println("NATIVE CODEC: "+results.size()+" PASS");
  }catch(Exception ex){Files.write(out.resolve("native-codec-failure-trace.txt"),trace);throw ex;}finally{e.dispose();}
 }
}
