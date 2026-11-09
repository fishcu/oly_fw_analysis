#!/usr/bin/env python3
# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Evidence-bounded startup experiments; explicit modeled service boundaries.

Not a physical board boot. Unknown accesses stop and are retained in the report.
"""
import argparse
from dataclasses import replace
import hashlib
import gzip
import json
from pathlib import Path
import struct

from penf_emulator import Region, execute, firmware, ROOT, BASE, INITIAL_SP, STACK, ENGINE
from penf_runtime_model import RuntimeInterrupts
from penf_alex_model import AlexPeer

ENTRY = 0x60021020
HOOK_RETURN = 0x18030000


class BootState:
    def __init__(self, boot_status=0, ideal_storage=False, strap_bits=7):
        self.regions = [Region('main_image', BASE, firmware(), 'rx'),
                        Region('incoming_stack', STACK, bytes(0x1100), 'rw', True),
                        Region('return_trampoline', HOOK_RETURN, b'\xcb'*8, 'rx')]
        self.regs = {'pc': ENTRY, 'sp': INITIAL_SP, 'psw': 0}
        self.events = []
        self.steps = 0
        self.cpu = 0
        self.cpu_regs = {}
        self.private_memory = {}
        self.blocked = {}
        self.ram('early_globals', 0x6181e340, bytes(0xcc0))
        self.ram('internal_stack', 0x47000000, bytes(0x800), aliases=False)
        self.ram('relocated_helper_destination', 0x47000800, b'\xa5'*0x1800, aliases=False, executable=True)
        self.ram('data_initializer_destination', 0x61170fe0, b'\xa5'*0x648)
        self.ram('kernel_cpu0_stack', 0x61821c00, b'\xa5'*0x200)
        # Pointer targets in CPU0 configuration 600414c4; firmware initializes them.
        self.ram('kernel_cpu0_control_structures', 0x618357f8, b'\xa5'*0x154)
        self.ram('kernel_cpu0_object_arena', 0x616fd340, b'\xa5'*0x91000)
        self.ram('kernel_cpu0_fixed_objects', 0x61821e00, b'\xa5'*(0x618357f8-0x61821e00))
        self.ram('kernel_cpu0_interrupt_stack', 0x6181fc00, b'\xa5'*0x1000)
        # Small-object scheap pool, bounded by the native free classifier at
        # 600233fc and allocated by 60023603. Bitmap/allocator code runs natively.
        self.ram('scheap_small_objects',0x61173fc0,b'\xa5'*(0x61221fc0-0x61173fc0))
        self.regions.append(Region('kernel_per_core_configuration_pointers', 0x8ff00004, b'\xa5'*12, 'rw', True))
        for name, address, data, permissions in [
            ('boot_status_scenario', 0x98e00060, struct.pack('<I', boot_status), 'r'),
            ('core_config_scenario', 0x8070, bytes(2), 'rw'),
            ('initial_write_98100008', 0x98100008, bytes(4), 'w'),
            ('cpu0_vector_words', 0x8000, bytes(0x20), 'w'),
            ('cpu_index_0', 0x8050, bytes(4), 'r'),
            ('startup_shared_flags', 0x8ff00060, bytes(0x1c), 'rw'),
            ('startup_shared_flag_3fc', 0x8ff003fc, bytes(4), 'rw'),
            ('early_interrupt_setup_28', 0x98900028, bytes(4), 'w'),
            ('early_interrupt_setup_00', 0x98900000, bytes(4), 'w'),
            ('early_interrupt_setup_24', 0x98900024, bytes(4), 'w'),
            ('early_interrupt_setup_4c', 0x9890004c, bytes(4), 'w'),
            ('controller_58_scenario', 0x98e00058, bytes(4), 'r'),
        ]:
            self.regions.append(Region(name, address, data, permissions, 'w' in permissions))
        # Reviewed writes in 600223d7 and 60022302, not a blanket MMIO mapping.
        for address in [0x9b800c30, 0x98d0015c, 0x98d00150, 0x98d00160,
                        0x98d00158, 0x98d010a8, 0x98d0103c, 0x98d01108,
                        0x98d01018, 0x98d01058, 0x98d0105c, 0x98d01060,
                        0x98d01064, 0x98d01038, 0x98d0106c, 0x98d0108c,
                        0x98d01054, 0x98d01094, 0x98d0107c, 0x98d01084,
                        0x98d01080, 0x98d0104c, 0x98d01088]:
            self.regions.append(Region(f'storage_setup_{address:x}', address, bytes(4), 'w', True))
        if ideal_storage:
            self.regions.append(Region('storage_initialization_ready_scenario', 0x98d01104,
                                       struct.pack('<I', 0x2000), 'rw', True))
            self.ram('bad_block_table_destination', 0x61171fc0, b'\xa5'*8192)
        self.gpio_reads = set()
        # Exact register addresses from the initialization tables, not MMIO pages.
        pins = struct.unpack_from('<194I', firmware(), 0x60025cec-BASE)
        for address in pins[:191]:
            self.register(address, 'w'); self.register(address+4, 'w')
        for i in range(50):
            address = struct.unpack_from('<I', firmware(), 0x60025fe8-BASE+8*i)[0]
            self.register(address, 'w')
        for i in range(8):
            address = struct.unpack_from('<I', firmware(), 0x60026178-BASE+8*i+4)[0]
            self.register(address+20, 'w'); self.register(address+24, 'w')
        for i in range(15):
            address = struct.unpack_from('<I', firmware(), 0x600267b0-BASE+12*i)[0]
            for offset in (0,4,8): self.register(address+offset, 'w')
        for offset in (0x130,0x134,0x138,0x128c,0x1294,0x1298,0x1288,0x129c,0x1280,0x1284,0x127c,0,4):
            self.register(0x9b800000+offset, 'w')
        for offset in range(0xc4,0xf4,4):
            self.register(0x9b800000+offset, 'w')
        for bit, pin in enumerate((90,91,92)):
            self.register(pins[pin], 'rw', 0x10 if strap_bits & (1<<bit) else 0)
            self.register(pins[pin]+4, 'rw', 0)
            self.gpio_reads.update((pins[pin], pins[pin]+4))
        for address in (0x99e20008,0x99e2000c,0x99e20010):
            self.register(address, 'rw', 0); self.gpio_reads.add(address)
        self.regions.append(Region('decoded_board_revision', 0x8ff00188, b'\xa5', 'rw', True))
        for address in (0x8fe00000,0x8fe00002,0x8fe00004,0x8fe00006):
            self.regions.append(Region(f'uncontended_lock_byte_{address:x}', address, bytes(1), 'rw', True))
        # Reference-counted gate writes in 6008ec54; reads are still forbidden.
        for address in (0x988000d0,0x988000d4,0x988000d8,0x98800128,0x988000dc,0x988000e0,0x9880012c):
            self.regions.append(Region(f'gate_command_{address:x}', address, bytes(4), 'w', True))
        for address in (0x9b8000f4,0x9b8000f8,0x9b8000fc,0x9b800100):
            self.register(address, 'w')
        # 122 interrupt-priority slots/core, bounded by 6006d79e.
        for address in (0x99200000,0x99300000,0x99b00000):
            self.regions.append(Region(f'interrupt_priority_{address:x}', address, bytes(122*4), 'w', True))
        self.regions.append(Region('kernel_shared_state', 0x8ff00000, bytes(4), 'rw', True))
        self.register(0x99200314, 'w')
        # CPU0 interrupt initialization callback 6006ad5b.
        for address in range(0x8940,0x895c,4):
            self.regions.append(Region(f'local_interrupt_control_{address:x}', address, bytes(2), 'rw', True))
        self.regions.append(Region('diagnostic_state', 0x8ff0007c, bytes(12), 'rw', True))
        for address in (0x9b801328,0x9b80133c,0x98700004,0x98700040,0x98700010,0x98700020):
            self.register(address, 'w')
        for address in (0x98700000,0x98700014,0x98700028):
            self.register(address, 'rw', 0)
        # TX-ready hypothesis for 6006d1ba; no RX input or UART timing modeled.
        self.regions.append(Region('uart_tx_ready_scenario', 0x9870001c, struct.pack('<I',1), 'r'))
        self.register(0x98700018, 'w')
        self.regions.append(Region('initial_task_shared_word', 0x8ff0018c, b'\xa5'*4, 'rw', True))
        self.regions.append(Region('cross_core_work_state', 0x8ff000b0, b'\xa5'*4, 'rw', True))
        # 6006e799 timer configuration shadows; this does not deliver timer IRQs.
        for address in (0x98900000,0x98900004,0x98900078): self.register(address,'rw',0)
        self.register(0x9890002c,'w')
        # Timer-channel enable RMW at 60085158, after native GPIO initialization.
        self.register(0x9b8000dc, 'rw', 0)
        # 6007c518 enables the diagnostic bus-error handler (no injected error).
        self.register(0x98000000, 'rw', 0)
        self.register(0x98000004, 'w')
        # Register shadows for 6007f498/6007f4d7/6007fa72 configuration.
        for offset in (0,4,0x10,0x14,0x18,0x1c): self.register(0x99700000+offset,'rw',0)
        for offset in range(0x40,0x80,4): self.register(0x99700000+offset,'w')
        # Six 16-byte and six 12-byte shared objects initialized by 6008a8aa.
        self.regions.append(Region('shared_peripheral_objects',0x8ff000e0,b'\xa5'*0xa8,'rw',True))
        # 60069f70 writes four control words and 57 pairs from 60091550.
        self.regions.append(Region('arbitration_controls',0x98b00800,bytes(16),'w',True))
        self.regions.append(Region('arbitration_table',0x98b00840,bytes(57*8),'w',True))
        # 60079ac9/60079b0e reset and configure the 98c00000 peripheral.
        for address in (0x98c00000,0x98c00008,0x98c0000c): self.register(address,'w')

    def register(self, address, permissions, initial=0):
        for i,r in enumerate(self.regions):
            if r.address == address and len(r.data) == 4:
                self.regions[i] = replace(r, permissions=''.join(c for c in 'rwx' if c in permissions+r.permissions),
                                         data=struct.pack('<I', initial) if 'r' in permissions else r.data,
                                         capture=r.capture or 'w' in permissions+r.permissions)
                return
        self.regions.append(Region(f'gpio_init_{address:x}', address, struct.pack('<I', initial), permissions, True))

    @staticmethod
    def is_private(region):
        return region.address < 0x10000 or 0x47000000 <= region.address < 0x47002000

    def switch_core(self, cpu):
        self.cpu_regs[self.cpu] = dict(self.regs)
        self.private_memory[self.cpu] = {r.name:r.data for r in self.regions if self.is_private(r)}
        if cpu not in self.cpu_regs:
            self.cpu_regs[cpu] = {'pc':(0x60027035,0x60027511)[cpu-1], 'psw':0, 'sp':INITIAL_SP}
        bank = self.private_memory.setdefault(cpu,{})
        self.regions = [replace(r,data=bank.get(r.name, b'\xa5'*len(r.data) if r.address>=0x47000000 else bytes(len(r.data))))
                        if self.is_private(r) else r for r in self.regions]
        self.regs = dict(self.cpu_regs[cpu])
        self.cpu = cpu
        self.write(0x8050,struct.pack('<I',cpu))
        self.events.append({'kind':'schedule', 'cpu':cpu, 'pc':hex(self.regs['pc'])})

    def notify_core(self, cpu):
        # Inferred polling interrupt-controller delivery, not exception injection.
        if cpu == self.cpu:
            old=struct.unpack('<H',self.read(0x8958,2))[0]
            self.write(0x8958,struct.pack('<H',old|0x10))
        else:
            bank=self.private_memory.setdefault(cpu,{})
            name='local_interrupt_control_8958'
            old=struct.unpack('<H',bank.get(name,bytes(2)))[0]
            bank[name]=struct.pack('<H',old|0x10)
        self.blocked.pop(cpu,None)

    def schedule_wait(self, reason):
        self.blocked[self.cpu] = reason
        for cpu in (0,1,2):
            if cpu != self.cpu and cpu not in self.blocked:
                self.switch_core(cpu)
                return True
        return False

    def read(self, address, size):
        for r in self.regions:
            if r.address <= address and address+size <= r.address+len(r.data):
                return bytes(r.data[address-r.address:address-r.address+size])
        raise ValueError(f'Unmapped harness read {address:#x}+{size:#x}')

    def write(self, address, data):
        for i, r in enumerate(self.regions):
            if r.address <= address and address+len(data) <= r.address+len(r.data):
                root = r.alias_of or r.name
                backing = next(x for x in self.regions if x.name == root)
                offset = address-r.address
                blob = backing.data[:offset]+bytes(data)+backing.data[offset+len(data):]
                self.regions = [replace(x, data=blob) if x.name==root or x.alias_of==root else x for x in self.regions]
                return
        raise ValueError(f'Unmapped harness write {address:#x}+{len(data):#x}')

    def ram(self, name, address, data, *, aliases=True, executable=False):
        address = address-0x40000000 if 0xa0000000 <= address < 0xc0000000 else address
        end = address+len(data)
        # Promote an exact portion of the flat image to writable runtime RAM.
        rebuilt = []
        for r in self.regions:
            rend = r.address+len(r.data)
            if address < rend and r.address < end:
                if r.alias_of or r.capture:
                    if r.address <= address and end <= rend:
                        self.write(address, data)
                        return
                    raise ValueError(f'RAM extent overlaps existing mutable region: {name}, {r.name}')
                if r.address < address:
                    rebuilt.append(replace(r, name=r.name+'_lo', data=r.data[:address-r.address]))
                if end < rend:
                    rebuilt.append(replace(r, name=r.name+'_hi', address=end, data=r.data[end-r.address:]))
            else:
                rebuilt.append(r)
        perms = 'rwx' if executable else 'rw'
        rebuilt.append(Region(name, address, bytes(data), perms, True))
        if aliases and 0x60000000 <= address < 0x80000000:
            rebuilt.append(Region(name+'_uncached', address+0x40000000, bytes(data), perms, False, name))
        self.regions = rebuilt

    def run(self, hooks, limit=200000):
        result = execute(self.regions, self.regs, 0xffffffff, breakpoints=hooks,
                         limit=limit, trace_limit=40, trace_tail=True, timeout=120, changed_captures=True)
        memory = []
        for item in result['memory']:
            region = self.regions[item['index']]
            data = bytes.fromhex(item['hex'])
            self.write(region.address, data)
            memory.append({'name': item['name'], 'address': item['address'], 'bytes': len(data),
                           'sha256': hashlib.sha256(data).hexdigest()})
        self.regs = result['registers']
        self.steps += result['completed']
        # Do not write megabytes of checkpoint buffers into the human report.
        result['memory'] = memory
        self.events.append({'kind': 'execution', 'cpu':self.cpu, 'result': result})
        return result

    def return_from_model(self, result=0):
        ret = self.regs['mdr']
        call = None
        for length, opcode, fmt in ((7,0xdd,'<i'),(5,0xcd,'<h')):
            try:
                candidate = self.read(ret-length,length)
            except ValueError:
                continue
            if candidate[0] != opcode:
                continue
            target = (ret-length+struct.unpack_from(fmt,candidate,1)[0]) & 0xffffffff
            if target == self.regs['pc']:
                call = candidate
                break
        if call is None:
            raise ValueError(f'Modeled boundary lacks a supported CALL frame at return {ret:#x}')
        self.write(HOOK_RETURN, b'\xdf'+call[-2:]+b'\xcb'*5)
        self.regs['pc'] = HOOK_RETURN
        self.regs['d0'] = result

    def task_snapshot(self, cpu=0):
        tasks = []
        config=(0x600414c4,0x60041650,0x600417dc)[cpu]
        table,end=struct.unpack('<II',self.read(config+0xcc,8))
        for index in range((end-table)//4):
            address = struct.unpack('<I',self.read(table+4*index,4))[0]
            if not address: break
            blob = self.read(address,92)
            task_id = struct.unpack_from('<H',blob,16)[0]
            if task_id & 0xfff:
                attributes, argument, entry, priority, size, stack = struct.unpack_from('<6I',blob,68)
                tasks.append({'id':task_id, 'tcb':hex(address),
                              'state':struct.unpack_from('<H',blob,12)[0],
                              'attributes':hex(attributes), 'argument':argument, 'entry':hex(entry),
                              'priority':priority, 'stack_bytes':size, 'stack':hex(stack)})
        return tasks

    def save_snapshot(self, path):
        """Inspection artifact only: a fault may have partial instruction effects."""
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        registers={**self.cpu_regs,self.cpu:dict(self.regs)}
        banks={**self.private_memory,
               self.cpu:{r.name:r.data for r in self.regions if self.is_private(r)}}
        payload={'scope':'Post-stop inspection, not an automatically resumable checkpoint',
                 'cpu':self.cpu,'registers':registers,'completed':self.steps,'blocked':self.blocked,
                 'private_memory':{cpu:{n:b.hex() for n,b in bank.items()} for cpu,bank in banks.items()},
                 'regions':[{'name':r.name,'address':r.address,'permissions':r.permissions,
                             'alias_of':r.alias_of,'size':len(r.data),
                             'hex':None if r.alias_of else r.data.hex()} for r in self.regions]}
        write_gzip_json(path, payload)


def write_gzip_json(path, payload):
    """Write the same JSON, batching top-level list items through the C encoder.

    Boot reports contain millions of scalar fields. json.dump's tiny writes are
    costly; json.dumps of the entire report would add a large peak allocation.
    Events and snapshot regions can each be encoded independently and in order.
    """
    with gzip.open(path, 'wt', encoding='utf-8') as stream:
        stream.write('{')
        for index, (key, value) in enumerate(payload.items()):
            if index:
                stream.write(', ')
            stream.write(json.dumps(key)+': ')
            if isinstance(value, list):
                stream.write('[')
                for item_index, item in enumerate(value):
                    if item_index:
                        stream.write(', ')
                    stream.write(json.dumps(item))
                stream.write(']')
            else:
                stream.write(json.dumps(value))
        stream.write('}')


def boot_experiment(boot_status=0, segments=400, ideal_storage=False, strap_bits=7, erased_parameters=False,
                    assume_peer_ready=False, run_peers=False, timer_clock=False, counter_step=None,
                    controller_init=False, peripheral_reset=False, adc_clock=False, adc_idle=False,
                    adc_sample=None, runtime_peers=False, runtime_irqs=0, serial_clock_word=None,
                    controller_input_bits=None, gpio_inputs=None, input_counter=None, alex_peer=None):
    if segments < 1: raise ValueError('At least one execution segment is required')
    provenance={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__).resolve(),ROOT/'tools/penf_emulator.py',
                          ENGINE,ROOT/'tools/mn103_strict.patch',ROOT/'tools/penf_runtime_model.py',
                          ROOT/'tools/penf_alex_model.py')}
    state = BootState(boot_status, ideal_storage, strap_bits)
    if serial_clock_word is not None:
        if not 0<=serial_clock_word<=0xffffffff: raise ValueError('Invalid serial clock word')
        state.register(0x988000fc,'r',serial_clock_word)
        state.events.append({'kind':'model','name':'serial peripheral PLL scenario',
            'address':'0x988000fc','value':hex(serial_clock_word),
            'assumption':'Unmeasured pre-main PLL state; native 6008f506/6008f5a9 computes frequency and serial divisor'})
    counter_ticks=0
    controller_config_request=None
    gpio_inputs=dict(gpio_inputs or {})
    if any(not 0<=p<191 or v not in (0,1) for p,v in gpio_inputs.items()):
        raise ValueError('GPIO scenarios require native pin 0..190 and value 0/1')
    if controller_input_bits is not None and not 0<=controller_input_bits<32:
        raise ValueError('Five controller input flags required')
    if adc_sample is not None and not 0 <= adc_sample <= 65535:
        raise ValueError('ADC sample must fit the native unsigned 16-bit sample buffer')
    if input_counter is not None and not 0<=input_counter<=0xffffffff:
        raise ValueError('Input counter must fit a 32-bit hardware word')
    adc_conversions=0
    interrupts=RuntimeInterrupts(runtime_irqs) if runtime_irqs else None
    if interrupts and not runtime_peers: raise ValueError('Runtime interrupts require runtime peers')
    alex=AlexPeer(alex_peer) if alex_peer else None
    if alex and (not interrupts or gpio_inputs.get(83)!=1):
        raise ValueError('Alex scenario requires runtime IRQs and explicit GPIO 83=1 readiness hypothesis')
    if counter_step is not None and not 0 < counter_step <= 0x3fffffff:
        raise ValueError('Counter step must be a positive 30-bit value')
    if timer_clock:
        state.register(0x9880004c, 'r', 1)
        state.register(0x98800008, 'r', 0)
        state.events.append({'kind':'model', 'name':'12 MHz timer clock scenario',
                             'assumption':'Unmeasured pre-main clock state: mux 9880004c=1, divider 98800008=0',
                             'evidence':'6008f27d selects 24 MHz; 6008f563 divides by 2*(register+1)'})
    if adc_clock:
        state.register(0x988000c8,'r',0)
        state.register(0x98800020,'r',0)
        state.events.append({'kind':'model','name':'12 MHz ADC clock scenario',
                             'assumption':'Unmeasured pre-main state: mux 988000c8=0, divider 98800020=0',
                             'evidence':'6008f390 clock index 7 selects 24 MHz and applies 6008f563 divider'})
    if erased_parameters:
        if not ideal_storage: raise ValueError('Erased parameter scenario requires ideal storage')
        state.ram('persistent_parameter_destinations', 0x61e72c00, b'\xa5'*0xb0000)
        state.ram('parameter_auxiliary_destination', 0x62f23c00, b'\xa5'*0x800)
    hooks = {0x600213ed, 0x60023e05, 0x600224c2, 0x6003008c, 0x60021c4f,
             0x60022bc4, 0x60022402, 0x60021365, 0x600213bb, 0x6006ad97}
    landmarks = {0x60041ae3:'system services initialization',
                 0x60041a48:'power gate accepted (camons)',
                 0x60041a74:'power gate rejected (camNoon)',
                 0x60041a8a:'power startup callback',
                 0x60041d9a:'normal startup section loading',
                 0x6006bf05:'CPUCONN0 task', 0x6007025b:'CPUSW0 task',
                 0x601a70cc:'USTART1 task', 0x601a7644:'USTART3 task',
                 0x601a7ed1:'USTART4 task', 0x601a8019:'USTART5 task',
                 0x60ab8ec8:'TPC USB task', 0x60b1d012:'FIRMUP service task',
                 0x60b1cbb5:'SD updater task'}
    hooks.update(landmarks)
    if gpio_inputs: hooks.add(0x60022bf4)
    gpio_irq_masks=set()
    gpio_irq_controls=set()
    gpio_irq_reads={0x6008491d,0x6008492a,0x6008494a,0x60084957,0x6008497c,0x600849d0}
    if runtime_peers and gpio_inputs:
        # Native input->IRQ descriptor lookup: 60084a9c and 6008474d.
        for pin in range(191):
            index=state.read(0x6012b8f8+pin,1)[0]
            if index==255: continue
            descriptor=struct.unpack('<8I',state.read(0x6012b9b8+32*index,32))
            control,status,mask=descriptor[1],descriptor[4],descriptor[5]
            if not all(0x9b800000<=a<0x9b802000 for a in (control,status,mask)):
                raise ValueError('Unreviewed GPIO interrupt descriptor')
            gpio_irq_controls.add(control+8)
            state.register(status,'w')
            gpio_irq_masks.add(mask)
        for address in gpio_irq_masks:state.register(address,'w')
        hooks.update(gpio_irq_reads)
        hooks.add(0x600847b5)
        state.events.append({'kind':'model','name':'static GPIO interrupt configuration scenario',
            'mask_addresses':[hex(a) for a in sorted(gpio_irq_masks)],
            'assumption':'Exact descriptors for native pins 0..190 permit configuration writes; mask registers initially zero and retain native RMW writes. No GPIO edges are generated. Status writes do not invent readable events, and input levels still require explicit per-pin scenarios.'})
    controller_input_reads={pc:0x98e00058+4*i for i,pc in enumerate((0x6007d43c,0x6007d449,0x6007d455,0x6007d468,0x6007d479))}
    if controller_input_bits is not None: hooks.update(controller_input_reads)
    if interrupts: hooks.update(interrupts.hooks)
    if alex: hooks.update(alex.hooks)
    input_control_reads={0x6019d3c2:0x9bd0000c,0x6019d3ef:0x9bd0008c,
                         0x6019d41f:0x9bd0000c,0x6019d45f:0x9bd0008c}
    serial_control_reads={0x6008a9e8:'a0',0x6008acae:'a1',
                          0x6008b5e8:'a0',0x6008b5f1:'a0',0x6008b614:'a0',0x6008b61d:'a0'}
    if input_counter is not None:hooks.update((0x6019d399,0x6019d3a7))
    if runtime_peers:
        if not run_peers: raise ValueError('Runtime peers require native peer kernel initialization')
        hooks.add(0x6003718b)
        hooks.update((0x6007dc71,0x6007dcdf,0x6007dd35))
        hooks.update(serial_control_reads)
        # Upper portions of the native 6181ec00/6181f400 task-stack extents;
        # the lower portion is already covered by early_globals.
        state.ram('late_task_stack_tails',0x6181f000,b'\xa5'*0xc00)
        landmarks.update({0x600271e7:'CPU1 initial task',0x6002764c:'CPU2 initial task'})
        hooks.update(landmarks)
        # Native peer timer setup 6006e826 / 6006e883.
        for address in (0x98900008,0x9890000c): state.register(address,'rw',0)
        for address in (0x98900030,0x98900034): state.register(address,'w')
        for address in (0x98800034,0x988000c0,0x988000c4): state.register(address,'w')
        # Four-channel input peripheral initialization at 6019d213/6019d285.
        # Record configuration writes only; no counter/event result is invented.
        for base in (0x9bd00000,0x9bd00080):
            for offset in (0,4,8,0xc,0x10,0x14,0x18,0x1c,0x20,0x24,0x28,0x2c):
                state.register(base+offset,'w')
        hooks.update(input_control_reads)
        state.events.append({'kind':'model','name':'input peripheral configuration write sink',
            'assumption':'Reviewed 6019d213/6019d285/6019d3ac writes in two 9bd00000/80 banks are retained; enable masks start zero and retain RMW writes. Event status reads and interrupts remain unmodeled.'})
        # Exact register pointers in six native serial-controller descriptors.
        serial_registers=set()
        for channel in range(6):
            for address in struct.unpack('<24I',state.read(0x6012e7c0+96*channel,96)):
                if 0x98200000<=address<0x98800000:
                    serial_registers.add(address)
                    state.register(address,'w')
        # Separate cold retained-parameter scenario used by CPU2's bulk restore.
        for address in range(0x98e00004,0x98e00040,4): state.register(address,'w')
        state.regions.append(Region('initial_shared_runtime_mailboxes',0x8ff00088,bytes(0x28),'rw',True))
        state.regions.append(Region('initial_shared_cpu2_mailboxes',0x8ff000b4,bytes(0x2c),'rw',True))
        state.events.append({'kind':'model','name':'initial shared runtime mailboxes empty',
            'assumption':'8ff00088..8ff000b0 and 8ff000b4..8ff000e0 start zero; no pending cross-core dispatch request before application initialization. Native later writes retained.'})
    hooks.add(0x600307dd)
    gpio_readbacks={0x600845a9:4,0x600845e6:4}
    if runtime_peers:
        gpio_readbacks.update({p:0 for p in (0x60084ed9,0x60084ee6,0x60084ef5,0x60084f23,0x60084f2c,0x60084f36)})
        landmarks.update({0x60075eb5:'ADC request callback',0x60075eb2:'ADC average returned',
                          0x60041d66:'initial battery requests returned'})
        hooks.update(landmarks)
    hooks.update(gpio_readbacks)
    mux_registers={0x9b801234,0x9b80126c,0x9b801250,0x9b801004,0x9b80101c,
                   0x9b80103c,0x9b800d9c,0x9b800db8,0x9b800dd4,0x9b801288}
    mux_returns={0x6008c876,0x6008c8a6,0x6008c8aa,0x6008c958,0x6008ca07}
    hooks.update(mux_returns|{0x6008c84e})
    if peripheral_reset: hooks.add(0x6008a9c2)
    if adc_idle or adc_sample is not None: hooks.add(0x60079d66)
    adc_reads={pc:0x98c0003c+4*i for i,pc in enumerate((0x6007a213,0x6007a228,0x6007a23f,
               0x6007a256,0x6007a26d,0x6007a284,0x6007a29b,0x6007a2b2))}
    adc_readbacks={0x6007a028:0x98c00000,0x6007a03b:0x98c00004,0x6007a042:0x98c00004}
    if adc_sample is not None:
        hooks.update({0x60079da7,0x60079dbd,0x60079dc3,0x60079dc9,0x60079dcd}|set(adc_reads))
        hooks.update(adc_readbacks)
    if counter_step is not None: hooks.add(0x60022eef)
    controller_registers=(0x98e00000,0x98e00040,0x98e00048,0x98e00084,0x98e000a0,0x98e000a4)
    if controller_init:
        hooks.update((0x6007d1c2,0x6007d2fe,0x6007d36e,0x60022720,0x6002274b,0x60022755,
                      0x47001112,0x47001146,0x4700114a,0x6007d9a0,
                      0x6007d812,0x6007d828,0x6007d841))
        if runtime_peers: hooks.update((0x4700114d,0x6007d91f,0x6007d96e,0x6007d978))
    if assume_peer_ready:
        hooks.update((0x60033777,0x60033563))
        for address in (0x99300310,0x99b00310): state.register(address, 'w')
    notifications = {0x600300a3:1,0x600300ae:2,0x600300c5:0,
                     0x600300d0:2,0x600300e7:0,0x600300f2:1}
    if run_peers:
        if assume_peer_ready: raise ValueError('Select actual peer execution or assumed readiness, not both')
        hooks.update((0x60033777,0x60033563,0x6002794d,0x60032a11,0x60032a1f))
        hooks.update(notifications)
        for address in (0x98100408,0x98100808,0x99200310,0x99300310,0x99b00310,0x99300314,0x99b00314): state.register(address,'w')
        state.regions.append(Region('peer_core_local_8a80',0x8a80,bytes(2),'w',True))
        for cpu, config in ((1,0x60041650),(2,0x600417dc)):
            arena,size=struct.unpack('<II',state.read(config+0x2c,8))
            state.ram(f'kernel_cpu{cpu}_object_arena',arena,b'\xa5'*size)
            stack,size=struct.unpack('<II',state.read(config+0x70,8))
            state.ram(f'kernel_cpu{cpu}_interrupt_stack',stack,b'\xa5'*size)
    for _ in range(segments):
        result = state.run(hooks,limit=2000000 if runtime_peers else 200000)
        pc = state.regs['pc']
        if result['status'] != 'breakpoint':
            break
        if alex and pc in alex.hooks:
            if not alex.handle(state,hooks,interrupts): break
        elif pc==0x60022bf4 and gpio_inputs:
            pin=state.regs['d1']
            if pin not in gpio_inputs:
                # Preserve original permission checks (including boot straps).
                step=state.run(hooks-{pc},limit=1)
                if step['completed']!=1 or step['status']!='instruction_limit': break
                continue
            address=struct.unpack('<I',state.read(0x60025cec+4*pin,4))[0]
            if state.regs['a0']!=address: raise ValueError('Unexpected GPIO read address')
            region=next(r for r in state.regions if r.address==address)
            value=(struct.unpack('<I',region.data)[0]&~16)|(gpio_inputs[pin]<<4)
            state.register(address,'rw',value)
            state.events.append({'kind':'model','name':'explicit GPIO input level',
                'pin':pin,'value':gpio_inputs[pin],'address':hex(address),'entry':hex(pc)})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions=region.permissions) if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif runtime_peers and gpio_inputs and pc==0x600847b5:
            address=state.regs['a1']+8
            if address not in gpio_irq_controls: raise ValueError('Unreviewed GPIO interrupt control write')
            state.register(address,'w')
            state.events.append({'kind':'model','name':'GPIO interrupt configuration write',
                'entry':hex(pc),'address':hex(address),'value':state.regs['d0']})
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif runtime_peers and gpio_inputs and pc in gpio_irq_reads:
            address=state.regs['a0']
            if address not in gpio_irq_masks: raise ValueError('Unreviewed GPIO interrupt mask read')
            old=struct.unpack('<I',state.read(address,4))[0]
            state.register(address,'rw',old)
            state.events.append({'kind':'model','name':'GPIO interrupt mask readback',
                'entry':hex(pc),'address':hex(address),'value':hex(old)})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif controller_input_bits is not None and pc in controller_input_reads:
            address=controller_input_reads[pc]
            old=struct.unpack('<I',state.read(address,4))[0]
            bit=(address-0x98e00058)//4
            value=(old&0x7fffffff)|(((controller_input_bits>>bit)&1)<<31)
            state.register(address,'rw',value)
            state.events.append({'kind':'model','name':'controller input flags scenario',
                'entry':hex(pc),'address':hex(address),'value':hex(value),
                'assumption':'High input bit supplied by configurable five-bit mask; low native configuration bits retained'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif input_counter is not None and pc in (0x6019d399,0x6019d3a7):
            address=state.regs['a0']+state.regs['d1' if pc==0x6019d399 else 'd0']
            if address not in (0x9bd00038,0x9bd0003c,0x9bd000b8,0x9bd000bc):
                raise ValueError('Unreviewed input counter address')
            state.register(address,'r',input_counter)
            state.events.append({'kind':'model','name':'static input counter scenario',
                'entry':hex(pc),'address':hex(address),'value':input_counter,
                'assumption':'Constant raw value for four input channels, no motion or input interrupt; physical control mapping unverified'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[r for r in state.regions if r.address!=address]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif runtime_peers and pc in input_control_reads:
            address=input_control_reads[pc]
            if state.regs['a0']!=address:raise ValueError('Unexpected input enable mask address')
            old=struct.unpack('<I',state.read(address,4))[0]
            state.register(address,'rw',old)
            state.events.append({'kind':'model','name':'input peripheral enable mask readback',
                'entry':hex(pc),'address':hex(address),'value':old})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif runtime_peers and pc in serial_control_reads:
            address=state.regs[serial_control_reads[pc]]
            if address not in serial_registers or (pc==0x6008a9e8 and state.regs['a1']!=address):
                raise ValueError('Unexpected serial reset-control address')
            old=struct.unpack('<I',state.read(address,4))[0]
            state.register(address,'rw',old)
            state.events.append({'kind':'model','name':'serial control readback','entry':hex(pc),
                                 'address':hex(address),'value':old,
                                 'assumption':'Last control write retained for this RMW; no serial response supplied'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif runtime_peers and pc in (0x6007dc71,0x6007dcdf,0x6007dd35):
            address=0x98100000+0x400*state.cpu
            if pc==0x6007dc71:
                for a in (0x28a00000,0x28a80000):
                    state.regions.append(Region(f'cache_discard_{a:x}',a,bytes(0x1000),'r'))
                state.register(address,'rw',0)
                state.events.append({'kind':'model','name':'coherent-cache maintenance scenario',
                    'cpu':state.cpu,'entry':hex(pc),
                    'assumption':'Discarded cache-aperture reads return zero; per-core control starts idle, invalidate completes immediately; no cache contents/timing modeled'})
            elif pc==0x6007dcdf:
                old=struct.unpack('<I',state.read(address,4))[0]
                if old!=0x10: raise ValueError('Unexpected cache-maintenance command')
                state.write(address,bytes(4))
            else:
                state.regions=[r for r in state.regions if r.address not in (0x28a00000,0x28a80000,address)]
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif interrupts and pc in interrupts.hooks:
            if not interrupts.handle(state,hooks): break
        elif pc==0x6003718b and runtime_peers:
            state.events.append({'kind':'milestone','name':'native kernel idle','cpu':state.cpu,
                                 'instructions':state.steps,'entry':hex(pc)})
            if interrupts and interrupts.deliver_pending(state): continue
            if not state.schedule_wait('native kernel idle; waiting for runtime interrupt'):
                if interrupts and interrupts.timer(state): continue
                result['unresolved']={'name':('Runtime interrupt scenario budget exhausted'
                    if interrupts and interrupts.delivered>=interrupts.budget
                    else 'All cores idle; runtime interrupt delivery needed')}
                break
        elif adc_sample is not None and pc in adc_readbacks:
            address=adc_readbacks[pc]
            old=struct.unpack('<I',state.read(address,4))[0]
            state.register(address,'rw',old)
            state.events.append({'kind':'model','name':'ADC control readback','entry':hex(pc),
                                 'address':hex(address),'value':old})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif adc_sample is not None and pc in ({0x60079da7,0x60079dbd,0x60079dc3,0x60079dc9,0x60079dcd}|set(adc_reads)):
            if pc in (0x60079da7,0x60079dbd,0x60079dcd) and state.regs['d3']!=1:
                raise ValueError('Unexpected ADC command')
            if pc in (0x60079dc3,0x60079dc9):
                old=struct.unpack('<I',state.read(0x98c00014,4))[0]
                state.register(0x98c00014,'rw',old)
            if pc in adc_reads:
                state.register(adc_reads[pc],'r',adc_sample)
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
            if pc==0x60079dbd:
                adc_conversions+=1
                state.write(0x98c00004,bytes(4))
                state.write(0x98c00014,struct.pack('<I',1))
                state.events.append({'kind':'model','name':'ADC polling conversion completion',
                    'entry':hex(pc),'conversion':adc_conversions,'sample':adc_sample,
                    'control':hex(struct.unpack('<I',state.read(0x98c00000,4))[0]),
                    'assumption':'Immediate conversion; arbitrary configurable raw sample, not measured voltage or calibration'})
            elif pc in (0x60079da7,0x60079dcd):
                state.write(0x98c00014,bytes(4))
            elif pc in adc_reads:
                state.events.append({'kind':'model','name':'ADC sample read','entry':hex(pc),
                                     'channel':(adc_reads[pc]-0x98c0003c)//4,'value':adc_sample})
                state.regions=[r for r in state.regions if r.address!=adc_reads[pc]]
            state.regions=[replace(r,permissions='w') if r.address==0x98c00014 else r for r in state.regions]
        elif pc==0x60079d66 and (adc_idle or adc_sample is not None):
            state.register(0x98c00004,'rw',0)
            state.register(0x98c00010,'w')
            state.register(0x98c00014,'w')
            state.events.append({'kind':'model','name':'ADC initially idle',
                                 'entry':hex(pc),'assumption':'No active conversion before this request; no completion or sample value supplied'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==0x98c00004 else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
            if adc_sample is None: hooks.remove(pc)
        elif pc==0x6008a9c2 and peripheral_reset:
            channel=state.regs['d2']
            if not 0<=channel<6: raise ValueError('Unexpected peripheral channel')
            address=struct.unpack('<I',state.read(0x6012e7c0+96*channel,4))[0]
            if state.regs['a0']!=address or state.regs['a1']!=address:
                raise ValueError('Unexpected peripheral reset address')
            state.register(address,'rw',0)
            state.events.append({'kind':'model','name':'peripheral reset-control initial value',
                                 'channel':channel,'address':hex(address),
                                 'assumption':'Zero before first reset request; does not complete reset, transfers or interrupts'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc==0x6008c84e or pc in mux_returns:
            for address in mux_registers:
                if not any(r.address==address and len(r.data)==4 for r in state.regions):
                    raise ValueError(f'Uninitialized mux configuration {address:#x}')
            state.regions=[replace(r,permissions='rw' if pc==0x6008c84e else 'w')
                           if r.address in mux_registers else r for r in state.regions]
            if pc==0x6008c84e:
                state.events.append({'kind':'model','name':'scoped peripheral pin-mux readback',
                                     'entry':hex(pc),'channel':state.regs['d0'],
                                     'assumption':'Ten reviewed configuration words retain previous writes during 6008c84e only; no pin input values'})
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc in (0x6007d812,0x6007d828,0x6007d841) and controller_init:
            address=0x98e00040
            old=struct.unpack('<I',state.read(address,4))[0]
            state.register(address,'rw',old)
            state.events.append({'kind':'model','name':'controller configuration readback',
                                 'entry':hex(pc),'address':hex(address),'value':hex(old),
                                 'assumption':'Configuration byte RMW sees the last write; no controller status is synthesized'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif runtime_peers and controller_init and pc in (0x6007d91f,0x6007d96e,0x6007d978):
            if pc==0x6007d91f:
                index=state.read(state.regs['a0'],1)[0]
                if index>4 or state.regs['mdr']!=0x6007d8cb:
                    result['unresolved']={'name':'Unreviewed controller bank configuration','bank':index,'return':hex(state.regs['mdr'])}
                    break
                controller_config_request=(0x98e00058+4*index,state.regs['d1'])
                old=struct.unpack('<I',state.read(0x98e000a4,4))[0]
                if old: raise ValueError('Controller configuration begins while mailbox busy')
                state.register(0x98e000a4,'rw',old)
            elif pc==0x6007d96e:
                address,value=controller_config_request
                if state.read(address,4)!=struct.pack('<I',value) or state.read(0x98e000a4,4)!=struct.pack('<I',0x20041001):
                    result['unresolved']={'name':'Unexpected bank configuration transaction',
                        'parameter_address':hex(address),'expected_parameter':hex(value),
                        'actual_parameter':state.read(address,4).hex(),'command':state.read(0x98e000a4,4).hex(),
                        'selector_pointer':hex(state.regs['a0']),'selector':state.read(state.regs['a0'],1)[0]}
                    break
                state.write(0x98e000a4,bytes(4))
                state.events.append({'kind':'model','name':'acknowledge controller bank configuration',
                    'entry':hex(pc),'parameter_address':hex(address),'value':hex(value),
                    'assumption':'Controller accepts native packed configuration immediately; no physical power transition or reset modeled'})
            else:
                controller_config_request=None
                state.regions=[replace(r,permissions='w') if r.address==0x98e000a4 else r for r in state.regions]
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc==0x4700114d and runtime_peers and controller_init:
            if state.regs['mdr'] not in (0x60089ea3,0x60089eb3):
                result['unresolved']={'name':'Unreviewed controller counter caller','return':hex(state.regs['mdr'])}
                break
            state.register(0x98e00098,'r',0)
            state.events.append({'kind':'model','name':'unchanged retained controller counter',
                'entry':hex(pc),'assumption':'Counter starts at zero and does not advance; no retained new diagnostic event'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[r for r in state.regions if r.address!=0x98e00098]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc == 0x6007d9a0 and controller_init:
            index=state.regs['d1']
            address=state.regs['a0']+state.regs['d0']
            bulk_retained=runtime_peers and state.regs['mdr']==0x600735eb and 0<=index<=14
            if not bulk_retained and (index,state.regs['mdr']) not in ((12,0x60041c3b),(13,0x60041c45),(14,0x60041c4f)):
                result['unresolved']={'name':'Unreviewed retained controller word','index':index,
                                      'caller_return':hex(state.regs['mdr'])}
                break
            if address!=0x98e00004+4*index: raise ValueError('Unexpected retained-word address')
            old=struct.unpack('<I',state.read(address,4))[0] if bulk_retained else 0
            state.register(address,'r',old)
            state.events.append({'kind':'model','name':'zero retained startup diagnostic word',
                                 'index':index,'address':hex(address),
                                 'value':old,'assumption':'Zero initial retained words; native writes persist' if bulk_retained else 'No retained mode/destination/sender for the 60041c32 diagnostic block only'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions='w') if r.address==address else r for r in state.regions] if runtime_peers else [r for r in state.regions if r.address!=address]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc in (0x60022720,0x47001112) and controller_init:
            if (pc==0x60022720 and state.regs['d0']!=10) or state.cpu!=0:
                result['unresolved']={'name':'Controller operation outside reviewed CPU0 watchdog scenario',
                                      'argument':state.regs['d0'],'cpu':state.cpu}
                break
            state.register(0x98e000a4,'rw',struct.unpack('<I',state.read(0x98e000a4,4))[0])
            if pc==0x60022720:
                state.register(0x98e0008c,'rw',struct.unpack('<I',state.read(0x98e0008c,4))[0])
            else:
                state.register(0x98e00090,'w')
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc in (0x6002274b,0x47001146) and controller_init:
            command=struct.unpack('<I',state.read(0x98e000a4,4))[0]
            parameter_address=0x98e0008c if pc==0x6002274b else 0x98e00090
            parameter=struct.unpack('<I',state.read(parameter_address,4))[0]
            if command!=0x20041001 or parameter!=(0x10a if pc==0x6002274b else 0x19191012):
                result['unresolved']={'name':'Unreviewed watchdog transaction','command':hex(command),'parameter':hex(parameter)}
                break
            state.write(0x98e000a4,bytes(4))
            state.events.append({'kind':'model','name':'acknowledge bounded watchdog transaction',
                                 'entry':hex(pc),'command':hex(command),'parameter':hex(parameter),
                                 'assumption':'Immediate completion; no watchdog expiry or real controller execution; reset requests excluded'})
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc in (0x60022755,0x4700114a) and controller_init:
            state.regions=[replace(r,permissions='w') if r.address in (0x98e000a4,0x98e0008c) else r for r in state.regions]
            step=state.run(hooks-{pc},limit=1)
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc == 0x6007d1c2 and controller_init:
            for address in controller_registers: state.register(address,'rw',0)
            for offset in (0x74,0x6c,0x78,0x7c,0x88,0x58,0x5c,0x60,0x64,0x68,0x50,0x8c):
                state.register(0x98e00000+offset,'w')
            state.events.append({'kind':'model','name':'controller initialization scenario',
                                 'assumption':'Idle command mailbox; no pending message or latched startup cause; RMW registers initially zero',
                                 'scope':'6007d1c2..6007d36e only; does not model controller code or reset'})
            hooks.remove(pc)
        elif pc == 0x6007d2fe and controller_init:
            command=struct.unpack('<I',state.read(0x98e000a4,4))[0]
            parameter=struct.unpack('<I',state.read(0x98e0008c,4))[0]
            if command!=0x20041001 or parameter!=0x10a:
                result['unresolved']={'name':'Unexpected controller command','command':hex(command),'parameter':hex(parameter)}
                break
            state.write(0x98e000a4,bytes(4))
            state.events.append({'kind':'model','name':'acknowledge one initialization command',
                                 'command':hex(command),'parameter':hex(parameter),
                                 'assumption':'Mailbox clears immediately; controller internals and timing unknown; not a reset/recovery model'})
            hooks.remove(pc)
        elif pc == 0x6007d36e and controller_init:
            state.regions=[replace(r,permissions='w') if r.address in controller_registers+(0x98e00058,0x98e00060) else r for r in state.regions]
            state.events.append({'kind':'milestone','name':'controller initialization returned under scenario',
                                 'entry':hex(pc),'instructions':state.steps})
            hooks.remove(pc)
        elif pc == 0x60022eef and counter_step is not None:
            counter_ticks=(counter_ticks+counter_step)&0x3fffffff
            state.register(0x98900074,'r',0x3fffffff-counter_ticks)
            state.events.append({'kind':'model','name':'synthetic monotonic counter read',
                                 'ticks':counter_ticks,'step_per_read':counter_step,
                                 'assumption':'Advances once per read; no physical time, timer interrupt, or hardware event delivery'})
            step=state.run(hooks-{pc},limit=1)
            # Other access sites still stop for review.
            state.regions=[r for r in state.regions if r.address!=0x98900074]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc in gpio_readbacks:
            address=state.regs['a1']+gpio_readbacks[pc]
            pins=struct.unpack_from('<194I',firmware(),0x60025cec-BASE)
            if address not in {p+4 for p in pins[:191]}:
                result['unresolved']={'name':'Unreviewed GPIO configuration readback','address':hex(address)}
                break
            region=next(r for r in state.regions if r.address==address and len(r.data)==4)
            state.regions=[replace(r,permissions='rw') if r.name==region.name else r for r in state.regions]
            state.events.append({'kind':'model','name':'GPIO configuration readback',
                                 'entry':hex(pc),'address':hex(address),'value':hex(struct.unpack('<I',region.data)[0]),
                                 'assumption':'Read returns last configuration write; admitted only for this RMW instruction'})
            step=state.run(hooks-{pc},limit=1)
            state.regions=[replace(r,permissions=region.permissions) if r.name==region.name else r for r in state.regions]
            if step['completed']!=1 or step['status']!='instruction_limit': break
        elif pc in landmarks:
            state.events.append({'kind':'milestone', 'name':landmarks[pc], 'cpu':state.cpu,
                                 'entry':hex(pc), 'instructions':state.steps,'d0':state.regs['d0']})
            hooks.remove(pc)
        elif pc == 0x600307dd:
            state.events.append({'kind':'task_start_request', 'cpu':state.cpu,
                                 'task_id':state.regs['d0'], 'return':hex(state.regs['mdr']),
                                 'instructions':state.steps})
            state.run(hooks-{pc},limit=1)
        elif pc in (0x600213ed,0x6002794d):
            start = (state.regs['d0'] & 0x3fffffff) | 0x60000000
            end = (state.regs['d1'] & 0x3fffffff) | 0x60000000
            if not start < end or end-start > 0x1000000:
                raise ValueError('Unexpected startup clear extent')
            state.ram(f'cleared_{start:x}', start, bytes(end-start))
            state.events.append({'kind': 'model', 'name': 'hardware-assisted RAM clear',
                                 'entry': hex(pc), 'start': hex(start), 'end': hex(end),
                                 'assumption': 'DMA clear succeeds; timing and device internals omitted',
                                 'cpu':state.cpu,
                                 'evidence': '600213ed..600215dc / 6002794d..60027b0d construct zero-fill DMA commands and clear a CPU tail'})
            state.return_from_model()
        elif pc == 0x60023e05:
            address = state.regs['a0']
            text = bytearray()
            for i in range(256):
                byte = state.read(address+i, 1)
                if byte == b'\0': break
                text.extend(byte)
            state.events.append({'kind': 'model', 'name': 'startup diagnostic sink',
                                 'entry': hex(pc), 'string_pointer': hex(address),
                                 'text': text.decode('ascii', errors='replace'),
                                 'assumption': 'Diagnostic output succeeds; logging side effects omitted'})
            state.return_from_model()
        elif pc == 0x60021c4f and ideal_storage:
            source, destination, size = state.regs['d1'], state.regs['d0'], state.regs['a0']
            if source not in (0x47ec0000, 0x47ee0000, 0x47f00000) or size != 8192:
                break
            # Synthetic no-bad-block case matching the scanner's table layout.
            table = b''.join(struct.pack('<II', i, 0xffffffff if 992<=i<1014 else i) for i in range(1024))
            state.write(destination, table)
            state.events.append({'kind': 'model', 'name': 'synthetic redundant bad-block table',
                                 'entry': hex(pc), 'source': hex(source), 'destination': hex(destination),
                                 'bytes': size, 'sha256': hashlib.sha256(table).hexdigest(),
                                 'assumption': 'Ideal NAND: no bad blocks; three identical copies; not a camera dump',
                                 'evidence': '600216a2 builds 1024 eight-byte entries and reserves indices 992..1013'})
            state.return_from_model()
        elif pc == 0x600224c2 and ideal_storage:
            source, destination, size = state.regs['a0'], state.regs['a1'], state.regs['d1']
            canonical_source=source-0x40000000 if 0x80000000<=source<0x88000000 and not source%2048 else source
            # Native 600221de accepts aligned 40000000 and 80000000 bases,
            # subtracting the selected base before NAND page translation.
            offset = canonical_source-0x403a0020
            erased = erased_parameters and any(lo <= source < source+size <= hi for lo,hi in (
                (0x40060000,0x400e0000),(0x400e0000,0x40160000)))
            if erased:
                data = b'\xff'*size
            elif 0 <= offset < offset+size <= len(firmware()):
                data = firmware()[offset:offset+size]
            else:
                result['unresolved'] = {'name': 'Flash bytes absent from downloaded main component',
                                        'source': hex(source), 'destination': hex(destination), 'bytes': size}
                break
            cached = destination-0x40000000 if 0xa0000000 <= destination < 0xc0000000 else destination
            state.ram(f'flash_copy_{source:x}', destination, data, executable=cached<0x61500000)
            state.events.append({'kind': 'model', 'name': 'synthetic erased parameter read' if erased else 'decoded logical flash read',
                                 'entry': hex(pc), 'source': hex(source), 'destination': hex(destination),
                                 'canonical_source':hex(canonical_source),
                                 'bytes': size, 'image_offset': hex(offset), 'sha256': hashlib.sha256(data).hexdigest(),
                                 'assumption': 'Erased persistent data, not actual camera settings/calibration' if erased else 'Successful logical read; supplied decoded payload; NAND I/O/ECC/timing omitted'})
            state.return_from_model()
        elif pc == 0x60022bc4:
            state.events.append({'kind': 'model', 'name': 'GPIO initialization read window closed',
                                 'strap_bits': strap_bits, 'decoded_board_revision': state.read(0x8ff00188,1)[0],
                                 'assumption': 'Strap input is a scenario, not a measured PEN-F board revision; write effects are register shadows'})
            state.regions = [replace(r, permissions='w') if r.address in state.gpio_reads else r for r in state.regions]
            hooks.remove(pc)
        elif pc == 0x60022402 and erased_parameters:
            address, size = state.regs['a0'], state.regs['d1']
            if address not in (0x400e0000,0x40100000,0x40120000,0x40140000) or size != 0x20000:
                result['unresolved'] = {'name': 'Erase outside modeled parameter banks', 'address': hex(address), 'bytes': size}
                break
            state.events.append({'kind': 'model', 'name': 'erase already-erased synthetic parameter bank',
                                 'entry': hex(pc), 'address': hex(address), 'bytes': size,
                                 'assumption': 'Successful erase in hypothetical storage only; no physical write'})
            state.return_from_model()
        elif pc == 0x60021365:
            # These read values only feed writes; no readiness acknowledgement.
            for address in (0x988000d0,0x988000d4,0x988000d8):
                state.register(address, 'rw', 0)
            for address in (0x98d00140,0x98d00144,0x988000f0,0x9880010c):
                state.register(address, 'w')
            state.events.append({'kind': 'model', 'name': 'secondary CPU release register window',
                                 'entry': hex(pc), 'assumption': 'Zero RMW input scenario; accepts release writes but does not execute other cores'})
            hooks.remove(pc)
        elif pc == 0x600213bb:
            state.regions = [replace(r, permissions='w') if r.address in (0x988000d0,0x988000d4,0x988000d8) else r for r in state.regions]
            state.events.append({'kind': 'milestone', 'name': 'secondary CPU entries published',
                                 'cpu1': hex(struct.unpack('<I',state.read(0x98d00140,4))[0]),
                                 'cpu2': hex(struct.unpack('<I',state.read(0x98d00144,4))[0])})
            hooks.remove(pc)
        elif pc == 0x6003008c:
            state.events.append({'kind': 'milestone', 'name': 'kernel entry reached', 'entry': hex(pc), 'instructions': state.steps})
            hooks.remove(pc)
        elif pc == 0x60033777 and assume_peer_ready:
            address, bit = state.regs['a0'], state.regs['d1']
            if address != 0x8958 or bit != 0: raise ValueError('Unreviewed peer notification')
            old = struct.unpack('<H', state.read(address,2))[0]
            state.write(address, struct.pack('<H', old | (1 << (bit+4))))
            state.events.append({'kind': 'model', 'name': 'assumed peer notification delivery',
                                 'entry': hex(pc), 'control': hex(address), 'bit': bit+4,
                                 'assumption': 'Peer has notified CPU0; other cores and interrupt timing not executed',
                                 'evidence': '600371f9 CPU0 waits for CPU1; peer notify 60039255 -> 600300b3 writes 99200310'})
            state.run(hooks-{pc}, limit=1)
        elif pc == 0x60033563 and assume_peer_ready:
            old = struct.unpack('<H',state.read(0x8ff00000,2))[0]
            if old != 1: raise ValueError('Unexpected kernel-ready mask before modeled peer arrival')
            state.write(0x8ff00000,struct.pack('<H',old|6))
            state.events.append({'kind': 'model', 'name': 'assumed peer kernel readiness',
                                 'entry': hex(pc), 'before': old, 'after': old|6,
                                 'assumption': 'CPU1 and CPU2 complete kernel object setup; their instructions have not executed',
                                 'evidence': '60033511 sets own bit under lock then waits for (1<<core_count)-1'})
            hooks.remove(pc)
        elif pc == 0x6006ad97:
            state.events.append({'kind': 'milestone', 'name': 'initial task entered through native kernel dispatcher',
                                 'entry':hex(pc), 'instructions':state.steps, 'tasks':state.task_snapshot()})
            hooks.remove(pc)
        elif pc in (0x60032a11,0x60032a1f) and run_peers:
            state.events.append({'kind':'milestone', 'name':'peer kernel entry reached', 'cpu':state.cpu,
                                 'entry':hex(pc), 'instructions':state.steps})
            hooks.remove(pc)
        elif pc in notifications and run_peers:
            target = notifications[pc]
            state.events.append({'kind':'model', 'name':'deliver native peer notification write',
                                 'cpu':state.cpu, 'target_cpu':target, 'entry':hex(pc),
                                 'assumption':'Successful delivery from 992/993/99b00310 to target local 8958 bit 4; inferred polling semantics, no IRQ handler/timing'})
            state.run(hooks-{pc},limit=1)
            state.notify_core(target)
        elif pc == 0x60033777 and run_peers:
            if state.regs['a0']!=0x8958 or state.regs['d1']!=0:
                raise ValueError('Unreviewed multicore notification channel')
            pending = struct.unpack('<H',state.read(0x8958,2))[0] & 0x10
            if pending:
                state.blocked.pop(state.cpu,None)
                state.run(hooks-{pc},limit=1)
            elif not state.schedule_wait('kernel peer notification'):
                result['unresolved']={'name':'All three cores wait for notifications'}
                break
        elif pc == 0x60033563 and run_peers:
            mask=struct.unpack('<H',state.read(0x8ff00000,2))[0]
            if mask != 7:
                if not state.schedule_wait('kernel ready mask'):
                    result['unresolved']={'name':'All cores wait before complete kernel-ready mask', 'mask':mask}
                    break
            else:
                state.events.append({'kind':'milestone','name':'all three kernels initialized shared readiness',
                                     'cpu':state.cpu, 'mask':mask, 'instructions':state.steps})
                # All peers executed setup through their barrier. Continue CPU0;
                # peer tasks/interrupt handlers remain unscheduled until modeled.
                if state.cpu != 0: state.switch_core(0)
                if runtime_peers: state.blocked.clear()
                hooks.remove(pc)
        else:
            break
    else:
        state.events.append({'kind':'unresolved','name':'Execution segment limit reached','limit':segments})
    return {'scope': 'Conditional execution from known main and published peer entries, not hardware reset',
            'source_sha256':provenance, 'main_sha256':hashlib.sha256(firmware()).hexdigest(),
            'boot_status_scenario': hex(boot_status), 'completed_instructions': state.steps,
            'ideal_storage_scenario': ideal_storage,
            'erased_parameters_scenario': erased_parameters,
            'assume_peer_ready': assume_peer_ready,
            'run_peers':run_peers, 'final_cpu':state.cpu,
            'timer_clock_scenario':timer_clock,
            'adc_clock_scenario':adc_clock,
            'adc_idle_scenario':adc_idle,
            'adc_sample_scenario':adc_sample,
            'runtime_peers_scenario':runtime_peers,
            'runtime_irqs_scenario':runtime_irqs,
            'runtime_interrupt_state':None if not interrupts else {
                'delivered':interrupts.delivered,'budget':interrupts.budget,
                'pending':[{'cpu':cpu,'irq':irq} for cpu,irq in sorted(interrupts.pending)]},
            'serial_clock_word_scenario':serial_clock_word,
            'controller_input_bits_scenario':controller_input_bits,
            'gpio_inputs_scenario':gpio_inputs,
            'input_counter_scenario':input_counter,
            'alex_peer_scenario':None if not alex else alex.summary(),
            'counter_step_scenario':counter_step,
            'controller_init_scenario':controller_init,
            'peripheral_reset_scenario':peripheral_reset,
            'final_cpu0_tasks':state.task_snapshot() if any(e.get('name')=='initial task entered through native kernel dispatcher' for e in state.events) else [],
            'final_peer_tasks':{cpu:state.task_snapshot(cpu) for cpu in (1,2)} if run_peers and any(e.get('name')=='all three kernels initialized shared readiness' for e in state.events) else {},
            'strap_bits_scenario': strap_bits,
            'final_pc': hex(state.regs['pc']), 'events': state.events}, state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--boot-status', type=lambda s:int(s,0), default=0)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--snapshot',type=Path,help='Optional gzip JSON of final memory/core state for inspection; not a resume file')
    p.add_argument('--segments',type=int,default=400,help='Maximum execution/model segments; default 400')
    p.add_argument('--ideal-storage', action='store_true', help='Explicit hypothetical ready controller and no-bad-block metadata')
    p.add_argument('--strap-bits', type=int, choices=range(8), default=7)
    p.add_argument('--erased-parameters', action='store_true', help='Separate hypothetical erased persistent parameter banks')
    p.add_argument('--assume-peer-ready', action='store_true', help='Explicit hypothetical successful kernel peer notifications')
    p.add_argument('--run-peers', action='store_true', help='Execute peer entry paths cooperatively with modeled notification delivery')
    p.add_argument('--timer-clock', action='store_true', help='Explicit hypothetical 12 MHz timer clock from pre-main mux/divider values')
    p.add_argument('--counter-step', type=lambda s:int(s,0), help='Explicit virtual elapsed-counter increment per read; no IRQs or real timing')
    p.add_argument('--controller-init', action='store_true', help='Explicit idle/no-startup-cause scenario and one bounded initialization-command acknowledgement')
    p.add_argument('--peripheral-reset', action='store_true', help='Explicit zero initial control words for six reviewed peripheral reset requests; completion remains unknown')
    p.add_argument('--adc-clock',action='store_true',help='Explicit hypothetical 12 MHz ADC clock; no conversion results supplied')
    p.add_argument('--adc-idle',action='store_true',help='Explicit idle ADC for the first request only; completion and samples still stop')
    p.add_argument('--adc-sample',type=lambda s:int(s,0),help='Explicit immediate polling ADC completion with this unsigned 16-bit raw sample; no IRQ conversions')
    p.add_argument('--runtime-peers',action='store_true',help='Continue peer initial/application tasks when a native kernel becomes idle')
    p.add_argument('--runtime-irqs',type=int,default=0,help='Bounded hypothetical timer interrupts through native vectors, delivered only when all cores idle')
    p.add_argument('--serial-clock-word',type=lambda s:int(s,0),help='Explicit pre-main PLL word at 988000fc; 0x200000 gives 192 MHz to clock index 9')
    p.add_argument('--controller-input-bits',type=lambda s:int(s,0),help='Five explicit input flags returned by 6007d43c, separate from retained configuration bits')
    p.add_argument('--gpio-pin',action='append',default=[],metavar='PIN=VALUE',help='Explicit GPIO input scenario; repeat for reviewed pins only')
    p.add_argument('--input-counter',type=lambda s:int(s,0),help='Explicit static raw value for four reviewed input-counter reads')
    p.add_argument('--alex-peer',choices=('startup','bad-first-reply'),help='Hypothetical seven-command serial peer, with native CPU0 IRQ and CPU1 comparison; requires GPIO 83=1')
    args = p.parse_args()
    report, state = boot_experiment(args.boot_status, segments=args.segments, ideal_storage=args.ideal_storage, strap_bits=args.strap_bits,
                                    erased_parameters=args.erased_parameters, assume_peer_ready=args.assume_peer_ready,
                                    run_peers=args.run_peers, timer_clock=args.timer_clock, counter_step=args.counter_step,
                                    controller_init=args.controller_init, peripheral_reset=args.peripheral_reset,
                                    adc_clock=args.adc_clock, adc_idle=args.adc_idle, adc_sample=args.adc_sample,
                                    runtime_peers=args.runtime_peers,runtime_irqs=args.runtime_irqs,
                                    serial_clock_word=args.serial_clock_word,controller_input_bits=args.controller_input_bits,
                                    gpio_inputs={int(k,0):int(v,0) for k,v in (s.split('=',1) for s in args.gpio_pin)},
                                    input_counter=args.input_counter,alex_peer=args.alex_peer)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    if args.snapshot: state.save_snapshot(args.snapshot)
    last = next(e['result'] for e in reversed(report['events']) if e['kind']=='execution')
    print(json.dumps({'instructions': state.steps, 'pc': report['final_pc'],
                      'last': last['status'], 'fault': last['fault']}, indent=2))


if __name__ == '__main__':
    main()
