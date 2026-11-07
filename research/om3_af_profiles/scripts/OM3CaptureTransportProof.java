// Conditional stock command producer, beyond the uninitialized RPC kernel.
// Runs native packaging; stops before submission. No response is fabricated.
// @category OM3
import java.nio.file.*;
import java.util.*;
public class OM3CaptureTransportProof extends OM3FullShooting {
 static class TransportBoundary extends Exception {}
 boolean guard;
 @Override boolean external(long t)throws Exception {
  if(t==0x6004d35eL||t==0x6004d43fL){check((reg("D0")&65535)==u16(0x60042efaL),"Unexpected command guard ID");boolean take=t==0x6004d35eL;check(guard!=take,"Command guard ownership");guard=take;e.writeRegister("D0",0);trace.add("MODEL:stock-command-guard:"+take);return true;}
  if(t==0x6007a7b5L){
   check(guard,"Native transport without command guard");
   long envelope=reg("A0"),packet=u32(envelope);trace.add(String.format("NATIVE-TRANSPORT-ENVELOPE pointer=%08x length=%d",packet,u32(envelope+4)));check(u32(envelope+4)==36,"Expected native 36-byte transport packet");check(allocations.containsKey(packet),"Unowned native transport packet");
   trace.add(String.format("NATIVE-COMMAND-TRANSPORT:port=%d timeout=%d packet=%08x bytes=%s",reg("D0"),reg("D1"),packet,java.util.HexFormat.of().formatHex(e.readMemory(toAddr(packet),36))));
   check(u16(packet)==0xb&&u16(packet+6)==0x1c&&u8(packet+8)==0x40,"Stock transport header and command 40");
   throw new TransportBoundary();
  }
  return super.external(t);
 }
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);init();guard=false;heap=0x70010000L;
  try{
   e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided transport input "+a+" at "+e.getExecutionAddress());}public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown transport address "+a);}});
   long input=0x700b4000L;e.writeMemory(toAddr(input),new byte[8]);e.writeMemoryValue(toAddr(input),1,8);e.writeMemoryValue(toAddr(input+1),1,1);e.writeRegister("A0",input);e.writeRegister("D0",4);
   trace.add("SUPPLIED-INPUT:direct native 61061c4c command-group=4 and command-8 payload; task-207 scheduling/RPC bypassed, not proven");
   try{runNative(0x61061c4cL,0xe0,0x2c);throw new Exception("Native command returned without reaching transport boundary");}
   catch(TransportBoundary ex){Files.writeString(out.resolve("capture-transport-outcome.txt"),"BOUNDARY conditional native command-40 packaging reaches transport 6007a7b5; no submission, reply or operational AF completion tested\n");}
  }finally{Files.write(out.resolve("capture-transport-trace.txt"),trace);e.dispose();}
 }
}
