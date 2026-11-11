// Complete the omitted, decoded protocol constructors in the stock table tail.
// Run original constructors, never write a type key or synthesize a reply.
// @category OM3
import java.util.*;
public class OM3StockModeInitializedProof extends OM3StockModeSequenceProof {
 static final long[][] PROTOCOL_CTORS={
  {0x60f1a760L,0x60dbe02cL},{0x60f1a764L,0x60dbef04L},
  {0x60f1a768L,0x60dbf3b6L},{0x60f1a76cL,0x60dcbbc0L},
  {0x60f1a770L,0x60dcd228L},{0x60f1a774L,0x60dd9dc4L}};
 @Override void beforeOriginal()throws Exception {
  note(String.format("PROTOCOL-INIT before subtype-key=%04x",u16(0x62b756bcL)));
  Map<String,java.math.BigInteger> saved=new LinkedHashMap<>();
  for(ghidra.program.model.lang.Register r:currentProgram.getLanguage().getRegisters())
   if(r.isBaseRegister()&&!r.isProcessorContext())saved.put(r.getName(),e.readRegister(r.getName()));
  long oldTop=stackTop;stackTop=0x700e4000L;
  try{
   for(long[] pair:PROTOCOL_CTORS){
    check(u32(pair[0])==pair[1],"Stock protocol constructor-table fingerprint");
    trace.add(String.format("STOCK-INIT:omitted protocol constructor table=%08x entry=%08x",pair[0],pair[1]));
    runNative(pair[1],0,0);
    note(String.format("PROTOCOL-INIT native-constructor=%08x subtype-key=%04x",pair[1],u16(0x62b756bcL)));
   }
   check(u16(0x62b756bcL)==0x26c,"Native photo subtype type-key initialization");
  }finally{stackTop=oldTop;for(var r:saved.entrySet())e.writeRegister(r.getKey(),r.getValue());}
  super.beforeOriginal();
 }
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(pc==0x60dcc872L)note(String.format("SUBTYPE-ROUTING obj=%08x key=%04x incoming=%04x",reg("A0"),u16(0x62b756bcL),u16(reg("A1")+4)));
  if(pc==0x60dcc889L)note(String.format("SUBTYPE-CLASS-RESULT result=%x",reg("D0")));
  return super.instruction(ins);
 }
}
