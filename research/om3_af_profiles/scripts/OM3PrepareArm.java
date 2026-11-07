// Prepare the 0107 secondary MCU payload using its Cortex-M vector table.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.data.DWordDataType;
import java.math.BigInteger;
public class OM3PrepareArm extends GhidraScript {
    public void run() throws Exception {
        Address base=toAddr(0x08000000L);
        var block=currentProgram.getMemory().getBlock(base);
        currentProgram.getProgramContext().setValue(currentProgram.getRegister("TMode"),base,block.getEnd(),BigInteger.ONE);
        int count=0;
        for(int i=0;i<128;i++){
            long value=Integer.toUnsignedLong(getInt(base.add(i*4)));
            if(i>0 && ((value&1)==0 || value<0x08000000L || value>=0x0803ffc0L))break;
            createData(base.add(i*4),new DWordDataType());
            if(i==0)continue;
            Address target=toAddr(value&~1L);
            addEntryPoint(target);disassemble(target);
            if(getFunctionAt(target)==null)createFunction(target,i==1?"Reset_Handler":null);
            count++;
        }
        println("Prepared "+count+" Cortex-M vector entries; base selected from reset code, not container address.");
    }
}
