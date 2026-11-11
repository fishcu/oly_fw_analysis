// Reproducible before-fix audit; health guard disabled at code generation only.
// @category OM3
import java.nio.file.*;
public class OM3WakeBeforeAudit extends OM3WakeAudit {
 @Override void profileInit(int mode,Path out)throws Exception{workerHealthGuard=false;super.profileInit(mode,out);}
 @Override String resultName(){return "wake-before-results.txt";}
}
