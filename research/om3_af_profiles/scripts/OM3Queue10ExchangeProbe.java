// Isolated native exchange and persistent-resume check. Replays the captured
// command-1 request as a labelled input fixture, never supplies response bytes.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3Queue10ExchangeProbe extends OM3Queue10WorkerProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String result;
  init();trace.clear();
  // Isolated call begins outside a hardware loop; the full UI fixture has
  // already established these registers, while init() alone has not.
  e.writeRegister("LIR",0);e.writeRegister("LAR",0);
  e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
   public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided exchange read "+a+" at "+e.getExecutionAddress());}
   public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown exchange address "+a);}
  });
  try{
   loadStaticMessageBuffers();
   // Same declared dynamic buffer contract as the observed caller's create.
   messageBuffers.put(1028L,new long[]{16,16,0});
   long request=0x700a0000L,env=request+0x40,reply=request+0x80,recvEnv=request+0x60;
   // The old trace captured the request header, not the pointed-to payload.
   // Declare a two-byte payload fixture; do not claim its value came from camera evidence.
   e.writeMemory(toAddr(0x7004ff38L),new byte[]{0,0});
   e.writeMemory(toAddr(request),HexFormat.of().parseHex("04040000020000000100000038ff0470"));
   e.writeMemoryValue(toAddr(env),4,request);e.writeMemoryValue(toAddr(env+4),4,16);
   e.writeMemoryValue(toAddr(recvEnv),4,reply);e.writeMemoryValue(toAddr(recvEnv+4),4,16);
   for(int i=0;i<2;i++){
    byte[] poison=new byte[16];Arrays.fill(poison,(byte)0xa5);e.writeMemory(toAddr(reply),poison);
    trace.add("REPLAY-INPUT:captured queue10 command1 exchange="+i+"; sender task=2; command=1; payload byte1=0 is a supplied fixture");
    e.writeRegister("D0",10);e.writeRegister("D1",0xffffffffL);e.writeRegister("A0",env);
    runNative(0x6004d171L,0xf0,0x30);
    check((eventFlags.get(11L)&2)!=0,"Native send hook must wake flag11 bit2");
    e.writeRegister("D0",1028);e.writeRegister("D1",0xffffffffL);e.writeRegister("A0",recvEnv);
    runNative(0x6004d087L,0xf0,0x2c);
    trace.add("NATIVE-EXCHANGE-RESULT:"+i+" wrapper-status="+reg("D0")+" bytes="+hex(reply,12));
    check(reg("D0")==0&&hex(reply,12).equals("000000000200000038ff0470"),"Native reply must overwrite the caller buffer with matching status/command/pointer");
    check(mbfQueue.getOrDefault(10L,new ArrayDeque<>()).isEmpty(),"Task10 request must be consumed");
    check(task10Context!=null,"Task10 context must persist between requests");
   }
   result="RETURNED: two captured command1 inputs received native replies using one persistent worker context; no camera/device completion asserted";
  }catch(Exception ex){result=String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex);}
  Files.write(out.resolve("queue10-exchange-trace.txt"),trace);Files.writeString(out.resolve("queue10-exchange-outcome.txt"),result+"\n");println(result);e.dispose();
 }
}
