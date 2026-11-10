// Locate native NotConsumed replies and inactive receiver components.
// @category OM3
public class OM3LiveReceiverTrace extends OM3LiveDispatch {
 @Override boolean instruction(ghidra.app.util.PseudoInstruction ins)throws Exception {
  long pc=ins.getAddress().getOffset();
  if(dispatching&&pc==0x60db8ad3L)trace.add(String.format("NATIVE-REQUEST-BUFFER object=%08x",reg("A0")));
  if(dispatching&&(pc==0x60db385cL||pc==0x60db375cL||pc==0x60db36aaL)){
   long object=reg("A0");trace.add(String.format("NATIVE-CAPTURE-ROUTER pc=%08x object=%08x state=%d backend=%08x requested-backend=%08x",pc,object,u32(object+0xb4),u32(object+0xb8),u32(object+0xbc)));
  }
  if(dispatching&&pc==0x60dbac1bL){long handler=reg("A0");trace.add(String.format("NATIVE-HANDLER-ENTRY pointer=%08x bytes=%s",handler,java.util.HexFormat.of().formatHex(e.readMemory(toAddr(handler),16))));}
  if(dispatching&&(pc==0x60dbd81eL||pc==0x60dbabe4L)){
   long object=reg("A0");trace.add(String.format("NATIVE-RECEIVER pc=%08x object=%08x vtable=%08x component-state=%d machine-state=%d tree=%08x",pc,object,u32(object),u32(object+0xb0),u32(object+0x100),u32(object+0x140)));
  }
  return super.instruction(ins);
 }
}
