/* Copyright 2026 fishku (original contributions)
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
 */
/* Offline MN103 execution harness around GNU libsim. GPL-3.0-or-later.
   Input protocol is private to penf_emulator.py; no camera/device access. */
#include "defs.h"
#include "sim-main.h"
#include "sim-fpu.h"
#include "sim-signal.h"
#include "mn10300-sim.h"
#include "sim/sim.h"
#include "sim/callback.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>

extern host_callback default_callback;
extern unsigned penf_fault_kind, penf_fault_map, penf_fault_size;
extern unsigned penf_fault_address, penf_fault_pc;

struct region { uint32_t address, size, permissions, capture, alias; unsigned char *allocation, *data, *original; };
struct trace { uint32_t regs[32]; };

static void die(const char *message) { fprintf(stderr, "%s\n", message); exit(2); }
static void read_exact(void *out, size_t size) {
  if (fread(out, 1, size, stdin) != size) die("Truncated harness input");
}
static uint32_t read_u32(void) {
  unsigned char b[4]; read_exact(b, 4);
  return b[0] | (uint32_t)b[1]<<8 | (uint32_t)b[2]<<16 | (uint32_t)b[3]<<24;
}
static void print_regs(const uint32_t *r) {
  putchar('[');
  for (unsigned i=0; i<32; i++) printf("%s%u", i ? "," : "", r[i]);
  putchar(']');
}

int main(void) {
  char magic[8]; read_exact(magic, sizeof magic);
  if (memcmp(magic, "PFMN002\0", 8)) die("Bad harness input magic");
  uint32_t limit=read_u32(), stop=read_u32(), trace_limit=read_u32(), count=read_u32();
  uint32_t hook_count=read_u32(), trace_tail=read_u32();
  if (hook_count>1024 || trace_tail>1) die("Invalid hook/trace settings");
  uint32_t *hooks=calloc(hook_count ? hook_count : 1, sizeof *hooks);
  if (!hooks) die("Allocation failed");
  for (unsigned i=0; i<hook_count; i++) hooks[i]=read_u32();
  if (!limit || limit>100000000 || trace_limit>100000 || count>1024) die("Invalid harness limits");
  uint32_t initial[32], before[32];
  for (unsigned i=0; i<32; i++) initial[i]=read_u32();
  struct region *regions=calloc(count, sizeof *regions);
  struct trace *trace=calloc(trace_limit ? trace_limit : 1, sizeof *trace);
  if (!regions || !trace) die("Allocation failed");
  uint64_t total=0;
  for (unsigned i=0; i<count; i++) {
    struct region *r=&regions[i];
    r->address=read_u32(); r->size=read_u32();
    r->permissions=read_u32(); r->capture=read_u32();
    r->alias=read_u32();
    total+=r->size;
    if (!r->size || total>268435456 || (uint64_t)r->address+r->size>0x100000000ULL ||
        !r->permissions || r->permissions>7 || r->capture>2) die("Invalid memory region");
    for (unsigned j=0; j<i; j++)
      if ((uint64_t)r->address< (uint64_t)regions[j].address+regions[j].size &&
          (uint64_t)regions[j].address < (uint64_t)r->address+r->size) die("Overlapping regions");
    if (r->alias!=UINT32_MAX) {
      if (r->alias>=i || regions[r->alias].size!=r->size ||
          (regions[r->alias].address & 7)!=(r->address & 7)) die("Invalid memory alias");
      r->data=regions[r->alias].data;
    } else {
      r->allocation=malloc((size_t)r->size+8);
      if (!r->allocation) die("Allocation failed");
      r->data=r->allocation+(r->address & 7);
      read_exact(r->data, r->size);
    }
    if (r->capture==2) {
      r->original=malloc(r->size);
      if (!r->original) die("Allocation failed");
      memcpy(r->original,r->data,r->size);
    }
  }
  if (getchar()!=EOF) die("Trailing harness input");

  char *args[]={"penf-mn103", "--architecture=mn10300", "--endian=little", NULL};
  bfd_init();
  default_callback.init(&default_callback);
  SIM_DESC sd=sim_open(SIM_OPEN_DEBUG, &default_callback, NULL, args);
  if (!sd) die("sim_open failed");
  if (sim_create_inferior(sd, NULL, NULL, NULL)!=SIM_RC_OK) die("sim_create_inferior failed");
  for (unsigned i=0; i<count; i++) {
    struct region *r=&regions[i];
    sim_core_attach(sd, NULL, 0, r->permissions, 0, r->address, r->size, 0, NULL, r->data);
  }
  for (unsigned i=0; i<32; i++) State.regs[i]=initial[i];
  memcpy(before, initial, sizeof before);
  penf_fault_kind=0;
  uint32_t attempted=0, completed=0, traced=0;
  enum sim_stop reason=sim_stopped;
  int sig=0;
  const char *status="instruction_limit";
  while (attempted<limit) {
    if (PC==stop) { status="returned"; break; }
    unsigned hit=0;
    for (unsigned i=0; i<hook_count; i++) if (PC==hooks[i]) { hit=1; break; }
    if (hit) { status="breakpoint"; break; }
    for (unsigned i=0; i<32; i++) before[i]=State.regs[i];
    if (trace_limit && (trace_tail || traced<trace_limit)) {
      memcpy(trace[traced % trace_limit].regs, before, sizeof before);
      traced++;
    }
    attempted++;
    sim_resume(sd, 1, 0);
    sim_stop_reason(sd, &reason, &sig);
    if (penf_fault_kind) { status=penf_fault_kind==1 ? "memory_fault" : "instruction_fault"; break; }
    if (reason!=sim_stopped || sig!=SIGTRAP) { status="simulator_stop"; break; }
    completed++;
  }
  if (!penf_fault_kind && completed==attempted && PC==stop) status="returned";
  printf("{\"status\":\"%s\",\"attempted\":%u,\"completed\":%u,\"signal\":%d,\"registers\":",
         status, attempted, completed, sig);
  uint32_t final[32]; for (unsigned i=0; i<32; i++) final[i]=State.regs[i];
  print_regs(final);
  printf(",\"before_last_instruction\":"); print_regs(before);
  printf(",\"fault\":");
  if (penf_fault_kind)
    printf("{\"kind\":%u,\"pc\":%u,\"map\":%u,\"address\":%u,\"size\":%u}",
           penf_fault_kind,penf_fault_pc,penf_fault_map,penf_fault_address,penf_fault_size);
  else printf("null");
  printf(",\"trace\":[");
  unsigned retained=traced<trace_limit ? traced : trace_limit;
  for (unsigned i=0; i<retained; i++) {
    if (i) putchar(',');
    unsigned slot=trace_tail && traced>trace_limit ? (traced+i)%trace_limit : i;
    print_regs(trace[slot].regs);
  }
  printf("],\"trace_start_instruction\":%u,\"trace_truncated\":%s,\"memory\":[",
         trace_tail ? attempted-retained : 0, attempted>retained ? "true" : "false");
  unsigned captured=0;
  for (unsigned i=0; i<count; i++) if (regions[i].capture) {
    struct region *r=&regions[i];
    if (r->capture==2 && !memcmp(r->data,r->original,r->size)) continue;
    printf("%s{\"index\":%u,\"address\":%u,\"hex\":\"", captured++ ? "," : "", i, r->address);
    for (unsigned j=0; j<r->size; j++) printf("%02x", r->data[j]);
    printf("\"}");
  }
  printf("]}\n");
  sim_close(sd, 1);
  default_callback.shutdown(&default_callback);
  for (unsigned i=0; i<count; i++) { free(regions[i].allocation); free(regions[i].original); }
  free(regions); free(trace); free(hooks);
  return 0;
}
