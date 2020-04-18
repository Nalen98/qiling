#!/usr/bin/env python3
#
# Cross Platform and Multi Architecture Advanced Binary Emulation Framework
# Built on top of Unicorn emulator (www.unicorn-engine.org)

import traceback

from unicorn import *
from unicorn.x86_const import *
from unicorn.arm64_const import *

from qiling.arch.x86 import *

from qiling.const import *
from qiling.os.const import *
from qiling.os.posix.posix import QlOsPosix

from .utils import *
from .kernel_func import *
from .thread import *
from .subsystems import *
from .task import *
from .mach_port import *
from .const import *

class QlOsMacos(QlOsPosix):
    def __init__(self, ql):
        super(QlOsMacos, self).__init__(ql)
        self.ql = ql
        self.ql.os = self

        self.load()


    def load(self):
        """
        initiate UC needs to be in loader,
        or else it will kill execve
        """
        self.ql.uc = self.ql.arch.init_uc

        if self.ql.archtype== QL_ARCH.ARM64:
            self.QL_MACOS_PREDEFINE_STACKADDRESS        = 0x0000000160503000
            self.QL_MACOS_PREDEFINE_STACKSIZE           = 0x21000
            self.QL_MACOS_PREDEFINE_MMAPADDRESS         = 0x7ffbf0100000
            self.QL_MACOS_PREDEFINE_VMMAP_TRAP_ADDRESS  = 0x4000000f4000
        elif  self.ql.archtype== QL_ARCH.X8664:
            self.QL_MACOS_PREDEFINE_STACKADDRESS        = 0x7ffcf0000000
            self.QL_MACOS_PREDEFINE_STACKSIZE           = 0x19a00000
            self.QL_MACOS_PREDEFINE_MMAPADDRESS         = 0x7ffbf0100000
            self.QL_MACOS_PREDEFINE_VMMAP_TRAP_ADDRESS  = 0x4000000f4000

        if self.ql.shellcoder and not self.ql.stack_address and not self.ql.stack_size:
            self.stack_address = 0x1000000
            self.stack_size = 10 * 1024 * 1024
        
        elif not self.ql.shellcoder and not self.ql.stack_address and not self.ql.stack_size:
                self.stack_address = self.QL_MACOS_PREDEFINE_STACKADDRESS
                self.stack_size = self.QL_MACOS_PREDEFINE_STACKSIZE
        
        elif self.ql.stack_address and self.ql.stack_size:
            self.stack_address = self.ql.stack_address
            self.stack_address = self.ql.stack_size


        self.macho_task = MachoTask()
        self.macho_fs = FileSystem(self.ql)
        self.macho_mach_port = MachPort(2187)
        self.macho_port_manager = MachPortManager(self.ql, self.macho_mach_port)
        self.macho_host_server = MachHostServer(self.ql)
        self.macho_task_server = MachTaskServer(self.ql)
        self.ql.mem.map(self.stack_address, self.stack_size, info="[stack]")

        if self.ql.shellcoder:    
            self.stack_address = self.stack_address  + 0x200000 - 0x1000
            self.ql.mem.write(self.stack_address, self.ql.shellcoder)
        else:
            self.ql.macho_vmmap_end = self.QL_MACOS_PREDEFINE_VMMAP_TRAP_ADDRESS
            self.stack_sp = self.QL_MACOS_PREDEFINE_STACKADDRESS + self.QL_MACOS_PREDEFINE_STACKSIZE
            self.envs = env_dict_to_array(self.ql.env)
            self.apples = ql_real_to_vm_abspath(self.ql, self.ql.path)


    def hook_syscall(self, intno= None, int = None):
        return self.load_syscall()


    def run(self):
        if self.ql.archtype== QL_ARCH.ARM64:
            self.ql.register(UC_ARM64_REG_SP, self.ql.loader.stack_address)
            self.ql.arch.enable_vfp()
            self.ql.hook_intr(self.hook_syscall)

        elif self.ql.archtype== QL_ARCH.X8664:
            self.ql.register(UC_X86_REG_RSP, self.ql.loader.stack_address)
            self.ql.hook_insn(self.hook_syscall, UC_X86_INS_SYSCALL)

        if  self.ql.archtype== QL_ARCH.X8664:
            self.gdtm = GDTManager(self.ql)
            ql_x86_register_cs(self)
            ql_x86_register_ds_ss_es(self)
        
        self.macho_task.min_offset = page_align_end(self.ql.loader.vm_end_addr, PAGE_SIZE)
        self.setup_output()
        
        # FIXME: Not working due to overlarge mapping, need to fix it
        # vm_shared_region_enter(self.ql)
        
        map_commpage(self.ql)
        
        self.thread_management = QlMachoThreadManagement(self.ql)
        self.macho_thread = QlMachoThread(self.ql)
        self.thread_management.cur_thread = self.macho_thread

        # load_commpage not wroking with ARM64, yet
        if  self.ql.archtype== QL_ARCH.X8664:
            load_commpage(self.ql)

        if (self.ql.until_addr == 0):
            self.ql.until_addr = self.QL_EMU_END
        try:
            if self.ql.shellcoder:
                self.ql.emu_start(self.ql.stack_address, (self.ql.stack_address + len(self.ql.shellcoder)))
            else:
                self.ql.emu_start(self.ql.loader.entry_point, self.ql.until_addr, self.ql.timeout)
        except UcError:
            if self.ql.output in (QL_OUTPUT.DEBUG, QL_OUTPUT.DUMP):
                self.ql.nprint("[+] PC= " + hex(self.ql.reg.pc))
                self.ql.mem.show_mapinfo()
                buf = self.ql.mem.read(self.ql.reg.pc, 8)
                self.ql.nprint("[+] ", [hex(_) for _ in buf])
                ql_hook_code_disasm(self.ql, self.ql.reg.pc, 64)
            raise QlErrorExecutionStop("[!] Execution Terminated")

        if self.ql.internal_exception != None:
            raise self.ql.internal_exception
