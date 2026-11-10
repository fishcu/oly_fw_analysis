// Seed known main-application landmarks, then let Ghidra analyze reachable code.
// @category OM3
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
public class OM3Prepare extends GhidraScript {
    public void run() throws Exception {
        long[] starts={0x60021020L,0x60405804L,0x6040580dL,0x60518381L,
            0x60518573L,0x604a3e73L,0x603f34ecL,0x604037f9L,0x6040391aL,
            0x60403a3bL,0x60403b5cL,0x60045e6cL,0x60045ed5L,0x601e75baL};
        for(long value:starts){
            Address a=toAddr(value);
            addEntryPoint(a);
            disassemble(a);
            if(getFunctionAt(a)==null) createFunction(a,null);
        }
        println("Seeded "+starts.length+" main-code entry candidates; default auto-analysis follows.");
    }
}
