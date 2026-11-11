// Differential control: exact stock code, descriptor table and native handlers.
// Same declared startup/settings/kernel fixtures as the extension probe.
// @category OM3
import java.nio.file.*;
public class OM3StockReceiverControl extends OM3ReceiverStartupProof {
 boolean stockExecution=false;
 @Override void init(){super.init();stockExecution=false;}
 @Override long ownedState(){return S;}
 @Override long translated(long p){
  if(stockExecution)for(int i=0;i<4;i++)if(p==CODE+0x900+128*i)return new long[]{0x610b9197L,0x610b96f0L,0x610b962aL,0x610b9653L}[i];
  return super.translated(p);
 }
 @Override void prepareResident(Path out)throws Exception {
  super.prepareResident(out);image=Files.readAllBytes(Paths.get("analysis/decoded/00_0100_50000020.decoded.bin"));e.writeMemory(toAddr(0x60021020L),image);decodeCache.clear();stockExecution=true;
  Files.writeString(out.resolve("stock-control-scope.txt"),"Stock payload restored in full before section loading; original descriptor pointers, original mode/accessor bytes and zero constructor count. Direct original-handler execution; same declared runtime fixtures. No extension code runs.\n");
 }
 @Override void afterOriginal()throws Exception {trace.add("CHECK:stock-original-return; no extension hooks or ownership assertions");}
}
