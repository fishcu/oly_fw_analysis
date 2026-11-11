// Cheap native AF-worker cold-start and persistent idle/resume check. No AF
// command, image, interrupt or completion is supplied.
// @category OM3
import java.nio.file.*;
public class OM3AFWorkerStartupProbe extends OM3CompleteStaticOSConsumerProof {
 @Override public void run()throws Exception {
  Path out=Paths.get(getScriptArgs()[0]);Files.createDirectories(out);String result;
  int tx=currentProgram.startTransaction("Temporary worker probe source mapping");
  try{if(currentProgram.getMemory().getBlock(toAddr(CODE))==null)currentProgram.getMemory().createInitializedBlock("emulator_only_worker_probe",toAddr(CODE),0x1000,(byte)0,monitor,false).setExecute(true);}
  finally{currentProgram.endTransaction(tx,true);}
  profileInit(6,out);
  try{
   heap=0x70010000L;objectID=1000;prepareResident(out);load(1,0xa5);load(4,0x55);coreFixture();
   e.setMemoryFaultHandler(new ghidra.pcode.memstate.MemoryFaultHandler(){
    public boolean uninitializedRead(ghidra.program.model.address.Address a,int n,byte[] d,int o){throw new IllegalStateException("Unprovided worker startup read "+a+" at "+e.getExecutionAddress());}
    public boolean unknownAddress(ghidra.program.model.address.Address a,boolean w){throw new IllegalStateException("Unknown worker startup address "+a);}
   });
   trace.add("WORKER-STARTUP:begin with complete ROM OS objects and native constructor groups; no input command");
   runStockTask(TASKS[1]);
   long before=trace.stream().filter(s->s.equals("native-call:609eff6b")).count();
   check(before==1&&afContexts.containsKey(94L),"Worker94 native initializer executed once and reached its own idle queue");
   runStockTask(TASKS[1]);
   check(trace.stream().filter(s->s.equals("native-call:609eff6b")).count()==1,"Resuming idle worker must not rerun native initialization");
   check(eventFlags.containsKey(197L),"ROM flag197 exists before any worker job");
   result="IDLE: native worker94 initializes once and resumes the same idle context; complete ROM OS tables loaded; no command/image/completion supplied";
  }catch(Exception ex){result=String.format("BOUNDARY pc=%08x: %s",e.getExecutionAddress().getOffset(),ex);}
  Files.write(out.resolve("af-worker-startup-trace.txt"),trace);Files.writeString(out.resolve("af-worker-startup-outcome.txt"),result+"\n");println(result);e.dispose();
 }
}
