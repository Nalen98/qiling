#!/usr/bin/env python3
# 
# Cross Platform and Multi Architecture Advanced Binary Emulation Framework
# Built on top of Unicorn emulator (www.unicorn-engine.org) 

from qiling.const import *
from qiling.exception import *


def align(size, unit):
    return (size // unit + (1 if size % unit else 0)) * unit


# A Simple Heap Implementation
class Chunk():
    def __init__(self, address, size):
        self.inuse = True
        self.address = address
        self.size = size

    @staticmethod
    def compare(chunk):
        return chunk.size


class QlMemoryManager:
    def __init__(self, ql):
        self.ql = ql
        #self.chunks = []
        #self.start_address = start_address
        #self.end_address = end_address
        # unicorn needs 0x1000
        self.page_size = 0x1000
        # current alloced memory size
        self.current_alloc = 0
        # curent use memory size
        self.current_use = 0
    
    def read(self, addr: int, size: int) -> bytearray:
        return self.ql.uc.mem_read(addr, size)

    def write(self, addr: int, data: bytes) -> None:
        return self.ql.uc.mem_write(addr, data)

    def _is_mapped(self, address):    
        for address_start, address_end, perm, info in self.ql.map_info:
            if (
                address >= address_start
                and address < address_end
            ):
                return False

        for region in list(self.ql.uc.mem_regions()):
            if address >= region[0] and address < region[1]:
                return False
        return True

class Heap:
    def __init__(self, ql, start_address, end_address):
        self.ql = ql
        self.chunks = []
        self.start_address = start_address
        self.end_address = end_address
        # unicorn needs 0x1000
        self.page_size = 0x1000
        # current alloced memory size
        self.current_alloc = 0
        # curent use memory size
        self.current_use = 0

    def mem_alloc(self, size):
        if self.ql.arch == QL_X86:
            size = align(size, 4)
        elif self.ql.arch == QL_X8664:
            size = align(size, 8)
        else:
            raise QlErrorArch("[!] Unknown ql.arch")

        # Find the heap chunks that best matches size 
        self.chunks.sort(key=Chunk.compare)
        for chunk in self.chunks:
            if chunk.inuse is False and chunk.size > size:
                chunk.inuse = True
                return chunk.address

        chunk = None
        # If we need mem_map new memory
        if self.current_use + size > self.current_alloc:
            real_size = align(size, self.page_size)
            # If the heap is not enough
            if self.start_address + self.current_use + real_size > self.end_address:
                return 0
            self.ql.uc.mem_map(self.start_address + self.current_alloc, real_size)
            chunk = Chunk(self.start_address + self.current_use, size)
            self.current_alloc += real_size
            self.current_use += size
            self.chunks.append(chunk)
        else:
            chunk = Chunk(self.start_address + self.current_use, size)
            self.current_use += size
            self.chunks.append(chunk)

        chunk.inuse = True
        # print("heap.mem_alloc addresss: " + hex(chunk.address))
        return chunk.address

    def mem_size(self, addr):
        for chunk in self.chunks:
            if addr == chunk.address and chunk.inuse:
                return chunk.size
        return 0

    def mem_free(self, addr):
        for chunk in self.chunks:
            if addr == chunk.address and chunk.inuse:
                chunk.inuse = False
                return True
        return False
