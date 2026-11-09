# Copyright 2026 fishku (original contributions)
# SPDX-License-Identifier: Apache-2.0
# Scope and third-party exceptions: see RIGHTS-AND-PROVENANCE.md.
"""Guard against executing staged firmware before a witnessed loader copy."""
import sys
import struct
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))

from penf_boot_sd_preparation import protect_unloaded_sections, sections, preparation_calls, CALL_SEQUENCE
from penf_emulator import BASE, firmware, Region
from penf_probe import ProbeState
from penf_boot_sd_constructor_memory import SDConstructorMemoryPeer
from penf_boot_sd_client import SDClientPeer
from penf_boot_sd_filesystem import SDFilesystemPeer
from penf_probe import CALLER


class ResidencyTests(unittest.TestCase):
    def test_worker_native_prologue_and_return_convention(self):
        s=self.fixture()
        s.regions.append(Region('prepared_calls',CALL_SEQUENCE,preparation_calls()+b'\xcb','rx'))
        s.regs.update(pc=CALL_SEQUENCE,d2=0x12,d3=0x34,a2=0x56,a3=0x78)
        initial=dict(s.regs)
        r=s.run({0x600421e6},limit=20)
        self.assertEqual(r['status'],'breakpoint')
        self.assertEqual(s.regs['sp'],initial['sp']-24)
        # Only test the native ABI: explicitly omit the worker body here.
        s.regs.update(pc=0x60042287,d2=1,d3=2,a2=3,a3=4)
        r=s.run({CALL_SEQUENCE+6},limit=10)
        self.assertEqual(r['status'],'breakpoint')
        for key in ('sp','d2','d3','a2','a3'):
            self.assertEqual(s.regs[key],initial[key])

    def fixture(self):
        s=ProbeState(0x60b1cbb5,0,0,b'x',{})
        s.regs['pc']=0x60b1cbb5
        return s

    def test_unloaded_client_cannot_execute(self):
        s=self.fixture()
        guarded=protect_unloaded_sections(s)
        self.assertEqual([x['id'] for x in guarded],[1,2,3,4,5,6,8])
        with self.assertRaises(ValueError):s.read(0x60b1cbb5,1)
        before=s.steps
        r=s.run(set(),limit=1)
        self.assertNotEqual(r['status'],'instruction_limit')
        self.assertEqual(s.steps,before)
        self.assertIsNotNone(r['fault'])

    def test_only_exact_observed_copy_admits_section(self):
        for size_delta,admitted in ((-1,False),(0,True),(1,False)):
            with self.subTest(size_delta=size_delta):
                s=self.fixture();sec=sections()[4]
                s.events.append(dict(kind='model',name='decoded logical flash read',
                    destination=hex(sec['start']+0x40000000),bytes=sec['end']-sec['start']+size_delta))
                guarded=protect_unloaded_sections(s)
                self.assertEqual(5 not in [x['id'] for x in guarded],admitted)
                if admitted:self.assertEqual(s.read(0x60b1cbb5,2),b'\xcf\xf0')
                else:
                    with self.assertRaises(ValueError):s.read(0x60b1cbb5,1)

    def test_loader_copy_restores_only_requested_section(self):
        s=self.fixture();protect_unloaded_sections(s);sec=sections()[4]
        data=firmware()[sec['start']-BASE:sec['end']-BASE]
        s.ram('explicit_test_copy',sec['start']+0x40000000,data,executable=True)
        self.assertEqual(s.read(0x60b1cbb5,2),b'\xcf\xf0')
        self.assertEqual(s.read(0xa0b1cbb5,2),b'\xcf\xf0')
        with self.assertRaises(ValueError):s.read(0x60598a2c,1)
        self.assertEqual(s.read(0x600421e1,2),b'\xcf\xf0')


class AllocationGuardTests(unittest.TestCase):
    def returned(self,size,slot=1,bit=True):
        base,stride,bitmap=(0x614d9000,2112,0xa1c556cc) if size<=2048 else (
            0x6122a540,16448,0xa1c556b4)
        address=base+slot*stride
        s=ProbeState(0x600233f9,0,4,b'x',dict(a0=address))
        self.assertEqual(s.run({0x600233f9},limit=1)['completed'],1)
        s.ram('explicit_bitmap_fixture',bitmap+4*(slot//32),struct.pack('<I',(1<<(slot%32)) if bit else 0))
        p=SDConstructorMemoryPeer('bulk','next',0);p.preparation_state='setup'
        p.constructor_allocation=(size,s.regs['sp'])
        return s,p,address

    def test_exact_extent_aliases_and_native_overflow_stop(self):
        for size in (129,2048,2049,16384):
            with self.subTest(size=size):
                s,p,address=self.returned(size)
                self.assertTrue(p.handle(s,p.hooks,None))
                self.assertEqual(s.read(address,size),b'\xa5'*size)
                s.write(address+0x40000000,b'\x13')
                self.assertEqual(s.read(address,1),b'\x13')
                s.regs.update(pc=0x60951727,a1=address+size,d0=0)
                r=s.run(set(),limit=1)
                self.assertEqual(r['status'],'memory_fault')
                self.assertEqual(r['fault']['access'],'write')

    def test_clear_allocation_bit_and_unaligned_address_rejected(self):
        for wrong_pointer in (False,True):
            s,p,address=self.returned(256,bit=wrong_pointer)
            if wrong_pointer:s.regs['a0']+=4
            self.assertFalse(p.handle(s,p.hooks,None))
            self.assertFalse(any(r.name.startswith('sd_constructor_allocation_') for r in s.regions))

    def test_free_of_either_alias_stops_before_native_free(self):
        for alias in (0,0x40000000):
            s,p,address=self.returned(256)
            self.assertTrue(p.handle(s,p.hooks,None))
            s.regs.update(pc=0x600233fc,a0=address+alias)
            before=s.steps
            self.assertFalse(p.handle(s,p.hooks,None))
            self.assertEqual(s.steps,before)


class SDClientTests(unittest.TestCase):
    def test_initial_watchdog_is_owned_by_existing_boot_model(self):
        p=SDClientPeer('bulk','next',0)
        self.assertNotIn(0x60022720,p.hooks)
        self.assertNotIn(0x6002274b,p.hooks)

    def test_sd_watchdog_native_mask_command_and_return(self):
        s=ProbeState(0x60b1e1f1,0,4,b'x',dict(d0=0))
        s.register(0x98e0008c,'rw',0xaaaaabff)
        s.register(0x98e000a4,'rw',0)
        # SD task-state observation requires its real pinned TCB state slot.
        s.ram('explicit_running_SD_state',0x61824edc,b'\x01\0')
        p=SDClientPeer('bulk','next',0);p.sd_running=True
        p.hooks.update((0x60022720,0x6002274b,0x60022755))
        for _ in range(8):
            r=s.run(p.hooks|{CALLER+7},limit=100)
            self.assertEqual(r['status'],'breakpoint')
            if s.regs['pc']==CALLER+7:break
            self.assertTrue(p.handle(s,p.hooks,None))
        self.assertEqual(s.regs['pc'],CALLER+7)
        self.assertEqual(int.from_bytes(s.read(0x98e0008c,4),'little'),0xaaaaabc0)
        self.assertEqual(s.read(0x98e000a4,4),bytes(4))
        self.assertEqual([r.permissions for r in s.regions if r.address in (0x98e0008c,0x98e000a4)],['w','w'])

    def test_native_physical_pool_slot_and_bitmap(self):
        for cursor,slot in ((3,4),(176,177),(177,0)):
            with self.subTest(cursor=cursor):
                s=ProbeState(0x60023682,0,0,b'x',{})
                s.regions.append(Region('native_calls_fixture',CALL_SEQUENCE,
                    b'\xfc\xff'+struct.pack('<i',0x60023682-CALL_SEQUENCE)+b'\xcb','rx'))
                s.regs['pc']=CALL_SEQUENCE
                s.ram('explicit_pool_cursor',0xa1c554c8,struct.pack('<I',cursor))
                s.ram('explicit_pool_bitmap',0xa1c5569c,bytes(24))
                r=s.run({CALL_SEQUENCE+6},limit=2000)
                self.assertEqual(r['status'],'breakpoint')
                self.assertEqual(s.regs['a0'],0xa1221fc0+slot*192)
                self.assertEqual(int.from_bytes(s.read(0xa1c5569c,24),'little'),1<<slot)


class FilesystemWorkspaceTests(unittest.TestCase):
    def test_native_physical_free_clears_only_its_slot(self):
        for target,base,stride,bitmap in ((0x60023881,0xa1221fc0,192,0xa1c5569c),
                                         (0x60023943,0xa142c540,16448,0xa1c556c4)):
            with self.subTest(target=hex(target)):
                s=ProbeState(target,0,0,b'x',dict(a0=base+5*stride))
                s.regions.append(Region('native_calls_fixture',CALL_SEQUENCE,
                    b'\xfc\xff'+struct.pack('<i',target-CALL_SEQUENCE)+b'\xcb','rx'))
                s.regs['pc']=CALL_SEQUENCE
                s.ram('explicit_pool_bitmap',bitmap,struct.pack('<I',(1<<4)|(1<<5)))
                r=s.run({CALL_SEQUENCE+6},limit=200)
                self.assertEqual(r['status'],'breakpoint')
                self.assertEqual(int.from_bytes(s.read(bitmap,4),'little'),1<<4)

    def test_native_filelog_header_selection(self):
        for flag,size,expected in ((255,65535,0x6059a778),(1,47480,0x6059a7d7),
                                   (1,47479,0x6059a778),(0,47480,0x6059a778)):
            with self.subTest(flag=flag,size=size):
                s=ProbeState(0x6059a72f,0x80,12,b'x',{})
                data=bytearray(b'\xff'*47616);data[9]=flag
                struct.pack_into('<H',data,10,size)
                s.ram('explicit_filelog',0xa2f03c00,data)
                s.ram('explicit_filelog_globals',0xa1c87d0c,bytes(48))
                r=s.run({0x6059a778,0x6059a7d7},limit=100)
                self.assertEqual(r['status'],'breakpoint')
                self.assertEqual(s.regs['pc'],expected)

    def test_native_physical_16k_pool_and_bitmap(self):
        for cursor,slot in ((3,4),(41,42),(42,0)):
            with self.subTest(cursor=cursor):
                s=ProbeState(0x60023733,0,0,b'x',{})
                s.regions.append(Region('native_calls_fixture',CALL_SEQUENCE,
                    b'\xfc\xff'+struct.pack('<i',0x60023733-CALL_SEQUENCE)+b'\xcb','rx'))
                s.regs['pc']=CALL_SEQUENCE
                s.ram('explicit_pool_cursor',0xa1c554c8,struct.pack('<I',cursor))
                s.ram('explicit_pool_bitmap',0xa1c556c4,bytes(8))
                r=s.run({CALL_SEQUENCE+6},limit=2000)
                self.assertEqual(r['status'],'breakpoint')
                self.assertEqual(s.regs['a0'],0xa142c540+slot*16448)
                self.assertEqual(int.from_bytes(s.read(0xa1c556c4,8),'little'),1<<slot)

    def test_workspace_cannot_replace_mutable_state(self):
        s=ProbeState(0x6058ffbc,0,20,b'x',{})
        p=SDFilesystemPeer('bulk','next',0)
        self.assertTrue(p.map_workspace(s,'test',0xa1e43c00,8192))
        s.write(0xa1e43c00,b'\x99')
        self.assertFalse(p.map_workspace(s,'test_overlap',0x61e43c00,8192))
        self.assertEqual(s.read(0xa1e43c00,1),b'\x99')

    def test_native_getter_and_selective_workspace_clear(self):
        s=ProbeState(0x6058ffbc,0,20,b'x',{})
        s.ram('explicit_workspace_pointer_slot',0x618c0ff0,bytes(4))
        p=SDFilesystemPeer('bulk','next',0);p.filesystem_phase='initializing'
        result=s.run({0x6058ffc6},limit=30)
        self.assertEqual(result['status'],'breakpoint')
        self.assertTrue(p.handle(s,p.hooks,None))
        result=s.run({CALLER+7},limit=60)
        self.assertEqual(result['status'],'breakpoint')
        self.assertEqual(s.read(0xa1e43c00,8160),b'\xa5'*8160)
        self.assertEqual(s.read(0xa1e45be0,16),bytes(16))
        self.assertEqual(s.read(0x61e45bf0,16),b'\xa5'*16)
        with self.assertRaises(ValueError):s.read(0xa1e45c00,1)


if __name__=='__main__':unittest.main()
