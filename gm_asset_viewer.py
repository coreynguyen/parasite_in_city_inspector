#!/usr/bin/env python3
"""
Game Maker Studio Asset Viewer v5.0
Optimized: Removed debug output, cached tile rendering, baked room images

Requirements:
    pip install Pillow pygame
"""

import struct
import os
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple
from io import BytesIO
import tempfile

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("WARNING: Pillow not installed. pip install Pillow")

try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    HAS_PYGAME = True
except:
    HAS_PYGAME = False
    print("WARNING: pygame not installed. pip install pygame")


# =============================================================================
# DARK THEME
# =============================================================================

class Colors:
    BG = '#1e1e1e'
    BG2 = '#252526'
    BG3 = '#2d2d2d'
    BG4 = '#3c3c3c'
    FG = '#d4d4d4'
    FG_DIM = '#808080'
    ACCENT = '#0078d4'
    SELECT = '#094771'
    BORDER = '#3c3c3c'
    CANVAS = '#111111'
    ERROR = '#f44747'
    SUCCESS = '#4ec9b0'


def setup_dark_theme(root):
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    style.configure('.', background=Colors.BG, foreground=Colors.FG,
                   fieldbackground=Colors.BG2, bordercolor=Colors.BORDER)
    style.configure('TFrame', background=Colors.BG)
    style.configure('TLabel', background=Colors.BG, foreground=Colors.FG)
    style.configure('TLabelframe', background=Colors.BG, foreground=Colors.FG)
    style.configure('TLabelframe.Label', background=Colors.BG, foreground=Colors.FG)
    style.configure('TButton', background=Colors.BG3, foreground=Colors.FG, padding=5)
    style.map('TButton', background=[('active', Colors.BG4), ('pressed', Colors.ACCENT)])
    style.configure('TEntry', fieldbackground=Colors.BG2, foreground=Colors.FG)
    style.configure('TSpinbox', fieldbackground=Colors.BG2, foreground=Colors.FG)
    style.configure('TNotebook', background=Colors.BG, bordercolor=Colors.BORDER)
    style.configure('TNotebook.Tab', background=Colors.BG2, foreground=Colors.FG, padding=[12, 4])
    style.map('TNotebook.Tab', background=[('selected', Colors.BG), ('active', Colors.BG3)])
    style.configure('Treeview', background=Colors.BG, foreground=Colors.FG,
                   fieldbackground=Colors.BG, bordercolor=Colors.BORDER)
    style.map('Treeview', background=[('selected', Colors.SELECT)])
    style.configure('Treeview.Heading', background=Colors.BG2, foreground=Colors.FG)
    style.configure('TScrollbar', background=Colors.BG3, troughcolor=Colors.BG2,
                   bordercolor=Colors.BORDER, arrowcolor=Colors.FG)
    style.configure('TProgressbar', background=Colors.ACCENT, troughcolor=Colors.BG2)
    style.configure('Horizontal.TScale', background=Colors.BG, troughcolor=Colors.BG2)
    
    root.configure(bg=Colors.BG)
    root.option_add('*TCombobox*Listbox.background', Colors.BG2)
    root.option_add('*TCombobox*Listbox.foreground', Colors.FG)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ChunkID:
    FORM = 0x4D524F46; GEN8 = 0x384E4547; SOND = 0x444E4F53; SPRT = 0x54525053
    BGND = 0x444E4742; OBJT = 0x544A424F; ROOM = 0x4D4F4F52; TPAG = 0x47415054
    STRG = 0x47525453; TXTR = 0x52545854; AUDO = 0x4F445541
    FONT = 0x544E4F46; PATH = 0x48544150; SCPT = 0x54504353; SHDR = 0x52444853
    TMLN = 0x4E4C4D54; FUNC = 0x434E5546; VARI = 0x49524156; CODE = 0x45444F43
    OPTN = 0x4E54504F; EXTN = 0x4E545845; AGRP = 0x50524741; TGIN = 0x4E494754
    
    NAMES = {0x4D524F46: "FORM", 0x384E4547: "GEN8", 0x4E54504F: "OPTN", 0x4E545845: "EXTN",
             0x444E4F53: "SOND", 0x54525053: "SPRT", 0x444E4742: "BGND", 0x48544150: "PATH",
             0x54504353: "SCPT", 0x52444853: "SHDR", 0x544E4F46: "FONT", 0x4E4C4D54: "TMLN",
             0x544A424F: "OBJT", 0x4D4F4F52: "ROOM", 0x4C464144: "DAFL", 0x47415054: "TPAG",
             0x45444F43: "CODE", 0x49524156: "VARI", 0x434E5546: "FUNC", 0x47525453: "STRG",
             0x52545854: "TXTR", 0x4F445541: "AUDO", 0x50524741: "AGRP", 0x4E494754: "TGIN"}


@dataclass
class Chunk:
    name: str; offset: int; size: int; data_start: int

@dataclass
class TPAGEntry:
    src_x: int; src_y: int; src_w: int; src_h: int
    tgt_x: int; tgt_y: int; tgt_w: int; tgt_h: int
    bound_w: int; bound_h: int; tex_id: int

@dataclass
class Sprite:
    index: int; name: str; width: int; height: int
    origin_x: int; origin_y: int
    frames: List[TPAGEntry] = field(default_factory=list)

@dataclass
class SoundDef:
    index: int; name: str; type_str: str; file_str: str
    volume: float; pitch: float; audio_id: int

@dataclass
class GameObject:
    index: int; name: str; sprite_index: int
    visible: bool; solid: bool; depth: int
    parent_index: int; mask_index: int

@dataclass
class RoomInst:
    x: int; y: int; obj_idx: int; inst_id: int

@dataclass
class RoomBgDef:
    visible: bool
    foreground: bool
    bg_index: int
    x: int
    y: int
    tile_h: bool
    tile_v: bool
    stretch: bool

@dataclass
class RoomTile:
    x: int
    y: int
    bg_index: int
    src_x: int
    src_y: int
    width: int
    height: int
    depth: int
    inst_id: int = 0
    scale_x: float = 1.0
    scale_y: float = 1.0
    color: int = 0xFFFFFFFF

@dataclass
class Room:
    index: int; name: str; width: int; height: int
    speed: int; color: int
    instances: List[RoomInst] = field(default_factory=list)
    bg_defs: List[RoomBgDef] = field(default_factory=list)
    tiles: List[RoomTile] = field(default_factory=list)

@dataclass
class Background:
    index: int; name: str; tpage: Optional[TPAGEntry] = None

@dataclass
class GameInfo:
    name: str; game_id: int

@dataclass
class FontGlyph:
    char: int
    x: int; y: int; w: int; h: int
    shift: int; offset: int

@dataclass 
class Font:
    index: int; name: str
    display_name: str
    size: float
    bold: bool; italic: bool
    range_start: int; range_end: int
    tpage: Optional[TPAGEntry] = None
    glyphs: List[FontGlyph] = field(default_factory=list)

@dataclass
class PathPoint:
    x: float; y: float; speed: float

@dataclass
class Path:
    index: int; name: str
    smooth: bool; closed: bool
    precision: int
    points: List[PathPoint] = field(default_factory=list)

@dataclass
class Script:
    index: int; name: str; code_id: int

@dataclass
class Shader:
    index: int; name: str
    type_str: str
    vertex_code: str
    fragment_code: str

@dataclass
class Extension:
    index: int; name: str; class_name: str

@dataclass
class Timeline:
    index: int; name: str; moment_count: int


# =============================================================================
# DATA.WIN PARSER
# =============================================================================

class DataWin:
    def __init__(self, path: str):
        with open(path, 'rb') as f:
            self.data = f.read()
        self.size = len(self.data)
        self.chunks: Dict[int, Chunk] = {}
        self._parse()
    
    def _parse(self):
        if self.u32(0) != ChunkID.FORM:
            raise ValueError("Invalid data.win")
        pos = 8
        while pos < self.size - 8:
            cid, sz = self.u32(pos), self.u32(pos + 4)
            name = ChunkID.NAMES.get(cid, struct.pack('<I', cid).decode('ascii', errors='replace'))
            self.chunks[cid] = Chunk(name, pos, sz, pos + 8)
            pos += 8 + sz
    
    def u16(self, o): return struct.unpack_from('<H', self.data, o)[0]
    def i16(self, o): return struct.unpack_from('<h', self.data, o)[0]
    def i32(self, o): return struct.unpack_from('<i', self.data, o)[0]
    def u32(self, o): return struct.unpack_from('<I', self.data, o)[0]
    def f32(self, o): return struct.unpack_from('<f', self.data, o)[0]
    def get_bytes(self, o, n): return self.data[o:o+n]
    
    def c_str(self, o, max_len=200):
        if o == 0 or o >= self.size: return ""
        end = self.data.find(b'\x00', o, o + max_len)
        return self.data[o:end].decode('utf-8', errors='replace') if end > o else ""


class GameExtractor:
    def __init__(self, dw: DataWin):
        self.dw = dw
        self.info: Optional[GameInfo] = None
        self.sprites: List[Sprite] = []
        self.sounds: List[SoundDef] = []
        self.objects: List[GameObject] = []
        self.rooms: List[Room] = []
        self.backgrounds: List[Background] = []
        self.textures: List[bytes] = []
        self.audio: Dict[int, bytes] = {}
        self.sprite_map: Dict[int, Sprite] = {}
        self.object_map: Dict[int, GameObject] = {}
        # New data types
        self.fonts: List[Font] = []
        self.paths: List[Path] = []
        self.scripts: List[Script] = []
        self.shaders: List[Shader] = []
        self.extensions: List[Extension] = []
        self.timelines: List[Timeline] = []
        self.strings: List[str] = []  # String table
    
    def extract_all(self, cb=None):
        steps = [self._gen8, self._strings, self._sprites, self._sounds, self._audio,
                 self._objects, self._rooms, self._backgrounds, self._textures,
                 self._fonts, self._paths, self._scripts, self._shaders, 
                 self._extensions, self._timelines]
        for i, fn in enumerate(steps):
            if cb: cb(f"Loading...", (i+1)/len(steps))
            fn()
    
    def _gen8(self):
        if ChunkID.GEN8 not in self.dw.chunks: return
        off = self.dw.chunks[ChunkID.GEN8].data_start
        name_ptr = self.dw.u32(off + 4)
        self.info = GameInfo(self.dw.c_str(name_ptr) if name_ptr else "", self.dw.u32(off + 20))
    
    def _sprites(self):
        if ChunkID.SPRT not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.SPRT]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 64: continue
            
            name_ptr = self.dw.u32(ptr)
            name = self.dw.c_str(name_ptr) if name_ptr else f"sprite_{i}"
            w, h = self.dw.u32(ptr+4), self.dw.u32(ptr+8)
            ox, oy = self.dw.i32(ptr+0x30), self.dw.i32(ptr+0x34)
            fc = self.dw.u32(ptr+0x38)
            
            frames = []
            if fc < 5000:
                for j in range(fc):
                    tp = self.dw.u32(ptr + 0x3C + j*4)
                    if tp and tp < self.dw.size - 22:
                        tpe = TPAGEntry(
                            self.dw.u16(tp), self.dw.u16(tp+2), self.dw.u16(tp+4), self.dw.u16(tp+6),
                            self.dw.u16(tp+8), self.dw.u16(tp+10), self.dw.u16(tp+12), self.dw.u16(tp+14),
                            self.dw.u16(tp+16), self.dw.u16(tp+18), self.dw.u16(tp+20))
                        if tpe.src_w > 0 and tpe.src_h > 0:
                            frames.append(tpe)
            
            spr = Sprite(i, name, w, h, ox, oy, frames)
            self.sprites.append(spr)
            self.sprite_map[i] = spr
    
    def _sounds(self):
        if ChunkID.SOND not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.SOND]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 32: continue
            name_ptr = self.dw.u32(ptr)
            type_ptr = self.dw.u32(ptr + 8)
            file_ptr = self.dw.u32(ptr + 12)
            self.sounds.append(SoundDef(
                i, self.dw.c_str(name_ptr) if name_ptr else f"sound_{i}",
                self.dw.c_str(type_ptr) if type_ptr else "",
                self.dw.c_str(file_ptr) if file_ptr else "",
                self.dw.f32(ptr+16), self.dw.f32(ptr+20), self.dw.i32(ptr+28)))
    
    def _audio(self):
        if ChunkID.AUDO not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.AUDO]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 4: continue
            length = self.dw.u32(ptr)
            if 0 < length < 50000000 and ptr + 4 + length <= self.dw.size:
                self.audio[i] = self.dw.get_bytes(ptr + 4, length)
    
    def _objects(self):
        if ChunkID.OBJT not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.OBJT]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 32: continue
            name_ptr = self.dw.u32(ptr)
            obj = GameObject(
                i, self.dw.c_str(name_ptr) if name_ptr else f"object_{i}",
                self.dw.i32(ptr+4), bool(self.dw.u32(ptr+8)), bool(self.dw.u32(ptr+12)),
                self.dw.i32(ptr+16), self.dw.i32(ptr+24), self.dw.i32(ptr+28))
            self.objects.append(obj)
            self.object_map[i] = obj
    
    def _rooms(self):
        if ChunkID.ROOM not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.ROOM]
        off, count = c.data_start, self.dw.u32(c.data_start)
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 100: continue
            
            name_ptr = self.dw.u32(ptr)
            width = self.dw.u32(ptr + 0x08)
            height = self.dw.u32(ptr + 0x0C)
            speed = self.dw.u32(ptr + 0x10)
            color = self.dw.u32(ptr + 0x18)
            
            bg_defs = []
            bg_list_ptr = self.dw.u32(ptr + 0x28)
            if bg_list_ptr and bg_list_ptr < self.dw.size - 4:
                bg_count = self.dw.u32(bg_list_ptr)
                for j in range(min(bg_count, 8)):
                    bp = self.dw.u32(bg_list_ptr + 4 + j*4)
                    if bp and bp < self.dw.size - 32:
                        bg_defs.append(RoomBgDef(
                            visible=bool(self.dw.u32(bp)),
                            foreground=bool(self.dw.u32(bp + 4)),
                            bg_index=self.dw.i32(bp + 8),
                            x=self.dw.i32(bp + 0x0C),
                            y=self.dw.i32(bp + 0x10),
                            tile_h=bool(self.dw.u32(bp + 0x14)),
                            tile_v=bool(self.dw.u32(bp + 0x18)),
                            stretch=bool(self.dw.u32(bp + 0x24))
                        ))
            
            instances = []
            inst_ptr = self.dw.u32(ptr + 0x30)
            if inst_ptr and inst_ptr < self.dw.size - 4:
                ic = self.dw.u32(inst_ptr)
                for j in range(min(ic, 10000)):
                    ip = self.dw.u32(inst_ptr + 4 + j*4)
                    if ip and ip < self.dw.size - 16:
                        instances.append(RoomInst(
                            self.dw.i32(ip), self.dw.i32(ip+4),
                            self.dw.i32(ip+8), self.dw.u32(ip+12)))
            
            room_name = self.dw.c_str(name_ptr) if name_ptr else f"room_{i}"
            tiles = []
            tile_ptr = self.dw.u32(ptr + 0x34)
            if tile_ptr and tile_ptr < self.dw.size - 4:
                tc = self.dw.u32(tile_ptr)
                for j in range(min(tc, 50000)):
                    tp = self.dw.u32(tile_ptr + 4 + j*4)
                    if tp and tp < self.dw.size - 0x30:
                        tiles.append(RoomTile(
                            x=self.dw.i32(tp),
                            y=self.dw.i32(tp + 4),
                            bg_index=self.dw.i32(tp + 8),
                            src_x=self.dw.i32(tp + 0x0C),
                            src_y=self.dw.i32(tp + 0x10),
                            width=self.dw.i32(tp + 0x14),
                            height=self.dw.i32(tp + 0x18),
                            depth=self.dw.i32(tp + 0x1C),
                            inst_id=self.dw.u32(tp + 0x20),
                            scale_x=self.dw.f32(tp + 0x24),
                            scale_y=self.dw.f32(tp + 0x28),
                            color=self.dw.u32(tp + 0x2C)
                        ))
            
            self.rooms.append(Room(
                i, room_name, width, height, speed, color, instances, bg_defs, tiles))
    
    def _backgrounds(self):
        if ChunkID.BGND not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.BGND]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 20: continue
            name_ptr = self.dw.u32(ptr)
            name = self.dw.c_str(name_ptr) if name_ptr else f"bg_{i}"
            tp_ptr = self.dw.u32(ptr + 16) if ptr + 20 <= self.dw.size else 0
            tpage = None
            if tp_ptr and tp_ptr < self.dw.size - 22:
                tpage = TPAGEntry(
                    self.dw.u16(tp_ptr), self.dw.u16(tp_ptr+2), self.dw.u16(tp_ptr+4), self.dw.u16(tp_ptr+6),
                    self.dw.u16(tp_ptr+8), self.dw.u16(tp_ptr+10), self.dw.u16(tp_ptr+12), self.dw.u16(tp_ptr+14),
                    self.dw.u16(tp_ptr+16), self.dw.u16(tp_ptr+18), self.dw.u16(tp_ptr+20))
            self.backgrounds.append(Background(i, name, tpage))
    
    def _textures(self):
        if ChunkID.TXTR not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.TXTR]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            entry = self.dw.u32(off + 4 + i*4)
            if entry and entry < self.dw.size - 8:
                data_ptr = self.dw.u32(entry + 4)
                if data_ptr and data_ptr < self.dw.size:
                    png = self._extract_png(data_ptr)
                    self.textures.append(png)
                else:
                    self.textures.append(b'')
            else:
                self.textures.append(b'')
    
    def _extract_png(self, off):
        if self.dw.data[off:off+8] != b'\x89PNG\r\n\x1a\n':
            return b''
        pos = off + 8
        while pos < self.dw.size - 12:
            chunk_len = struct.unpack('>I', self.dw.data[pos:pos+4])[0]
            chunk_type = self.dw.data[pos+4:pos+8]
            pos += 12 + chunk_len
            if chunk_type == b'IEND':
                return self.dw.data[off:pos]
        return b''
    
    def _strings(self):
        """Parse string table"""
        if ChunkID.STRG not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.STRG]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(min(count, 100000)):
            ptr = self.dw.u32(off + 4 + i*4)
            if ptr and ptr < self.dw.size - 4:
                str_len = self.dw.u32(ptr)
                if str_len < 10000 and ptr + 4 + str_len <= self.dw.size:
                    try:
                        s = self.dw.data[ptr+4:ptr+4+str_len].decode('utf-8', errors='replace')
                        self.strings.append(s)
                    except:
                        self.strings.append("")
                else:
                    self.strings.append("")
            else:
                self.strings.append("")
    
    def _fonts(self):
        """Parse font definitions"""
        if ChunkID.FONT not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.FONT]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 48: continue
            
            name_ptr = self.dw.u32(ptr)
            display_ptr = self.dw.u32(ptr + 4)
            size = self.dw.f32(ptr + 8) if ptr + 12 <= self.dw.size else 12.0
            bold = bool(self.dw.u32(ptr + 12)) if ptr + 16 <= self.dw.size else False
            italic = bool(self.dw.u32(ptr + 16)) if ptr + 20 <= self.dw.size else False
            range_start = self.dw.u16(ptr + 20) if ptr + 22 <= self.dw.size else 32
            range_end = self.dw.u16(ptr + 24) if ptr + 26 <= self.dw.size else 127
            
            # TPAG pointer at offset 28
            tp_ptr = self.dw.u32(ptr + 28) if ptr + 32 <= self.dw.size else 0
            tpage = None
            if tp_ptr and tp_ptr < self.dw.size - 22:
                tpage = TPAGEntry(
                    self.dw.u16(tp_ptr), self.dw.u16(tp_ptr+2), self.dw.u16(tp_ptr+4), self.dw.u16(tp_ptr+6),
                    self.dw.u16(tp_ptr+8), self.dw.u16(tp_ptr+10), self.dw.u16(tp_ptr+12), self.dw.u16(tp_ptr+14),
                    self.dw.u16(tp_ptr+16), self.dw.u16(tp_ptr+18), self.dw.u16(tp_ptr+20))
            
            # Parse glyphs
            glyphs = []
            glyph_ptr = self.dw.u32(ptr + 44) if ptr + 48 <= self.dw.size else 0
            if glyph_ptr and glyph_ptr < self.dw.size - 4:
                glyph_count = self.dw.u32(glyph_ptr)
                for j in range(min(glyph_count, 1000)):
                    gp = self.dw.u32(glyph_ptr + 4 + j*4)
                    if gp and gp < self.dw.size - 28:
                        glyphs.append(FontGlyph(
                            char=self.dw.u16(gp),
                            x=self.dw.u16(gp + 2),
                            y=self.dw.u16(gp + 4),
                            w=self.dw.u16(gp + 6),
                            h=self.dw.u16(gp + 8),
                            shift=self.dw.u16(gp + 10),
                            offset=self.dw.i16(gp + 12)
                        ))
            
            self.fonts.append(Font(
                i, self.dw.c_str(name_ptr) if name_ptr else f"font_{i}",
                self.dw.c_str(display_ptr) if display_ptr else "",
                size, bold, italic, range_start, range_end, tpage, glyphs
            ))
    
    def _paths(self):
        """Parse movement paths"""
        if ChunkID.PATH not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.PATH]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 20: continue
            
            name_ptr = self.dw.u32(ptr)
            smooth = bool(self.dw.u32(ptr + 4))
            closed = bool(self.dw.u32(ptr + 8))
            precision = self.dw.u32(ptr + 12)
            
            points = []
            point_count = self.dw.u32(ptr + 16) if ptr + 20 <= self.dw.size else 0
            point_off = ptr + 20
            for j in range(min(point_count, 10000)):
                if point_off + 12 <= self.dw.size:
                    points.append(PathPoint(
                        x=self.dw.f32(point_off),
                        y=self.dw.f32(point_off + 4),
                        speed=self.dw.f32(point_off + 8)
                    ))
                    point_off += 12
            
            self.paths.append(Path(
                i, self.dw.c_str(name_ptr) if name_ptr else f"path_{i}",
                smooth, closed, precision, points
            ))
    
    def _scripts(self):
        """Parse script names"""
        if ChunkID.SCPT not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.SCPT]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 8: continue
            
            name_ptr = self.dw.u32(ptr)
            code_id = self.dw.i32(ptr + 4) if ptr + 8 <= self.dw.size else -1
            
            self.scripts.append(Script(
                i, self.dw.c_str(name_ptr) if name_ptr else f"script_{i}",
                code_id
            ))
    
    def _shaders(self):
        """Parse shaders"""
        if ChunkID.SHDR not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.SHDR]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 16: continue
            
            name_ptr = self.dw.u32(ptr)
            type_ptr = self.dw.u32(ptr + 4) if ptr + 8 <= self.dw.size else 0
            vertex_ptr = self.dw.u32(ptr + 8) if ptr + 12 <= self.dw.size else 0
            frag_ptr = self.dw.u32(ptr + 12) if ptr + 16 <= self.dw.size else 0
            
            self.shaders.append(Shader(
                i, self.dw.c_str(name_ptr) if name_ptr else f"shader_{i}",
                self.dw.c_str(type_ptr) if type_ptr else "",
                self.dw.c_str(vertex_ptr) if vertex_ptr else "",
                self.dw.c_str(frag_ptr) if frag_ptr else ""
            ))
    
    def _extensions(self):
        """Parse extensions"""
        if ChunkID.EXTN not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.EXTN]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 8: continue
            
            name_ptr = self.dw.u32(ptr)
            class_ptr = self.dw.u32(ptr + 4) if ptr + 8 <= self.dw.size else 0
            
            self.extensions.append(Extension(
                i, self.dw.c_str(name_ptr) if name_ptr else f"ext_{i}",
                self.dw.c_str(class_ptr) if class_ptr else ""
            ))
    
    def _timelines(self):
        """Parse timelines"""
        if ChunkID.TMLN not in self.dw.chunks: return
        c = self.dw.chunks[ChunkID.TMLN]
        off, count = c.data_start, self.dw.u32(c.data_start)
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 8: continue
            
            name_ptr = self.dw.u32(ptr)
            moment_count = self.dw.u32(ptr + 4) if ptr + 8 <= self.dw.size else 0
            
            self.timelines.append(Timeline(
                i, self.dw.c_str(name_ptr) if name_ptr else f"timeline_{i}",
                moment_count
            ))


# =============================================================================
# ZOOMABLE CANVAS WITH ZOOM-TO-CURSOR
# =============================================================================

class ImageCanvas(tk.Canvas):
    def __init__(self, parent, **kw):
        kw.setdefault('bg', Colors.CANVAS)
        kw.setdefault('highlightthickness', 0)
        super().__init__(parent, **kw)
        
        self.pil_image: Optional[Image.Image] = None
        self.tk_image = None
        self.zoom = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._drag_data = None
        
        self.bind('<MouseWheel>', self._wheel)
        self.bind('<Button-4>', lambda e: self._wheel_linux(e, 1))
        self.bind('<Button-5>', lambda e: self._wheel_linux(e, -1))
        self.bind('<ButtonPress-1>', self._drag_start)
        self.bind('<B1-Motion>', self._drag_move)
        self.bind('<ButtonRelease-1>', self._drag_end)
        self.bind('<Configure>', self._on_resize)
        self.bind('<Double-Button-1>', self._reset_view)
    
    def set_image(self, img: Optional[Image.Image], fit=True):
        self.pil_image = img
        if img and fit:
            self.after(10, self._fit_image)
        else:
            self._redraw()
    
    def _fit_image(self):
        if not self.pil_image:
            return
        cw = max(1, self.winfo_width())
        ch = max(1, self.winfo_height())
        iw, ih = self.pil_image.width, self.pil_image.height
        self.zoom = min(cw / iw, ch / ih) * 0.95
        self.zoom = max(0.1, min(self.zoom, 8.0))
        self.offset_x = 0
        self.offset_y = 0
        self._redraw()
    
    def clear(self):
        self.pil_image = None
        self.tk_image = None
        self.delete('all')
    
    def _redraw(self):
        self.delete('all')
        if not self.pil_image:
            return
        
        cw, ch = self.winfo_width(), self.winfo_height()
        dw = max(1, int(self.pil_image.width * self.zoom))
        dh = max(1, int(self.pil_image.height * self.zoom))
        
        resample = Image.Resampling.NEAREST if self.zoom >= 1 else Image.Resampling.BILINEAR
        scaled = self.pil_image.resize((dw, dh), resample)
        self.tk_image = ImageTk.PhotoImage(scaled)
        
        x = cw / 2 + self.offset_x
        y = ch / 2 + self.offset_y
        self.create_image(x, y, image=self.tk_image, anchor='center')
        
        info = f"{self.pil_image.width}×{self.pil_image.height}  {self.zoom:.1f}x"
        self.create_text(8, 8, text=info, fill=Colors.FG_DIM, anchor='nw', font=('Consolas', 9))
    
    def _wheel(self, e):
        self._do_zoom(e.x, e.y, 1.15 if e.delta > 0 else 1/1.15)
    
    def _wheel_linux(self, e, direction):
        self._do_zoom(e.x, e.y, 1.15 if direction > 0 else 1/1.15)
    
    def _do_zoom(self, mx, my, factor):
        if not self.pil_image:
            return
        
        old_zoom = self.zoom
        self.zoom = max(0.05, min(50, self.zoom * factor))
        
        cw, ch = self.winfo_width(), self.winfo_height()
        rel_x = mx - cw / 2 - self.offset_x
        rel_y = my - ch / 2 - self.offset_y
        
        scale = self.zoom / old_zoom
        self.offset_x -= rel_x * (scale - 1)
        self.offset_y -= rel_y * (scale - 1)
        
        self._redraw()
    
    def _drag_start(self, e):
        self._drag_data = (e.x, e.y, self.offset_x, self.offset_y)
    
    def _drag_move(self, e):
        if self._drag_data:
            sx, sy, ox, oy = self._drag_data
            self.offset_x = ox + (e.x - sx)
            self.offset_y = oy + (e.y - sy)
            self._redraw()
    
    def _drag_end(self, e):
        self._drag_data = None
    
    def _on_resize(self, e):
        if self.pil_image:
            self._redraw()
    
    def _reset_view(self, e):
        if self.pil_image:
            self._fit_image()


# =============================================================================
# ANIMATION WIDGET
# =============================================================================

class AnimWidget(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.frames: List[Image.Image] = []
        self.idx = 0
        self.playing = False
        self.after_id = None
        
        self.canvas = ImageCanvas(self)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        ctrl = ttk.Frame(self)
        ctrl.pack(fill=tk.X, pady=5, padx=5)
        
        self.play_btn = ttk.Button(ctrl, text="▶ Play", width=8, command=self._toggle)
        self.play_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(ctrl, text="◀", width=3, command=self._prev).pack(side=tk.LEFT, padx=1)
        ttk.Button(ctrl, text="▶", width=3, command=self._next).pack(side=tk.LEFT, padx=1)
        
        self.lbl = ttk.Label(ctrl, text="0/0", width=10)
        self.lbl.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(ctrl, text="FPS:").pack(side=tk.LEFT, padx=(10, 2))
        self.fps_var = tk.IntVar(value=6)
        fps_spin = ttk.Spinbox(ctrl, from_=1, to=60, textvariable=self.fps_var, width=4)
        fps_spin.pack(side=tk.LEFT)
    
    def set_frames(self, frames: List[Image.Image], autoplay=True):
        self._stop()
        self.frames = frames
        self.idx = 0
        if frames:
            self.canvas.set_image(frames[0], fit=True)
            self.lbl.config(text=f"1/{len(frames)}")
            if autoplay and len(frames) > 1:
                self._play()
        else:
            self.canvas.clear()
            self.lbl.config(text="0/0")
    
    def clear(self):
        self._stop()
        self.frames = []
        self.canvas.clear()
        self.lbl.config(text="0/0")
    
    def _toggle(self):
        if self.playing:
            self._stop()
        else:
            self._play()
    
    def _play(self):
        if not self.frames:
            return
        self.playing = True
        self.play_btn.config(text="⏸ Pause")
        self._animate()
    
    def _stop(self):
        self.playing = False
        self.play_btn.config(text="▶ Play")
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
    
    def _animate(self):
        if not self.playing or not self.frames:
            return
        self.idx = (self.idx + 1) % len(self.frames)
        self.canvas.set_image(self.frames[self.idx], fit=False)
        self.lbl.config(text=f"{self.idx+1}/{len(self.frames)}")
        fps = max(1, self.fps_var.get())
        self.after_id = self.after(int(1000 / fps), self._animate)
    
    def _prev(self):
        if self.frames:
            self.idx = (self.idx - 1) % len(self.frames)
            self.canvas.set_image(self.frames[self.idx], fit=False)
            self.lbl.config(text=f"{self.idx+1}/{len(self.frames)}")
    
    def _next(self):
        if self.frames:
            self.idx = (self.idx + 1) % len(self.frames)
            self.canvas.set_image(self.frames[self.idx], fit=False)
            self.lbl.config(text=f"{self.idx+1}/{len(self.frames)}")


# =============================================================================
# AUDIO WIDGET
# =============================================================================

class AudioWidget(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.data = None
        self.temp_file = None
        self.playing = False
        
        self.info_lbl = ttk.Label(self, text="No audio", font=('Consolas', 11))
        self.info_lbl.pack(pady=20)
        
        self.fmt_lbl = ttk.Label(self, text="", foreground=Colors.FG_DIM)
        self.fmt_lbl.pack(pady=5)
        
        ctrl = ttk.Frame(self)
        ctrl.pack(pady=10)
        
        self.play_btn = ttk.Button(ctrl, text="▶ Play", width=10, command=self._toggle)
        self.play_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(ctrl, text="⏹ Stop", width=10, command=self._stop).pack(side=tk.LEFT, padx=5)
        
        self.status_lbl = ttk.Label(self, text="")
        self.status_lbl.pack(pady=10)
        
        if not HAS_PYGAME:
            self.status_lbl.config(text="pygame not installed", foreground=Colors.ERROR)
    
    def set_audio(self, data: bytes, name: str, snd: SoundDef, autoplay=True):
        self._stop()
        self.data = data
        
        fmt = "Unknown"
        if data[:4] == b'OggS': fmt = "OGG"
        elif data[:4] == b'RIFF': fmt = "WAV"
        elif data[:3] == b'ID3' or data[:2] == b'\xff\xfb': fmt = "MP3"
        
        self.info_lbl.config(text=f"🔊 {name}")
        self.fmt_lbl.config(text=f"{fmt} • {len(data):,} bytes • Vol: {snd.volume:.2f}")
        self.status_lbl.config(text="Ready", foreground=Colors.FG)
        
        if autoplay and HAS_PYGAME:
            self._play()
    
    def clear(self):
        self._stop()
        self.data = None
        self.info_lbl.config(text="No audio")
        self.fmt_lbl.config(text="")
        self.status_lbl.config(text="")
    
    def _toggle(self):
        if self.playing:
            self._stop()
        else:
            self._play()
    
    def _play(self):
        if not HAS_PYGAME or not self.data:
            return
        try:
            ext = '.ogg' if self.data[:4] == b'OggS' else '.wav' if self.data[:4] == b'RIFF' else '.mp3'
            self.temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            self.temp_file.write(self.data)
            self.temp_file.close()
            
            pygame.mixer.music.load(self.temp_file.name)
            pygame.mixer.music.play()
            self.playing = True
            self.play_btn.config(text="⏸ Pause")
            self.status_lbl.config(text="Playing...", foreground=Colors.SUCCESS)
            self._check()
        except Exception as e:
            self.status_lbl.config(text=str(e), foreground=Colors.ERROR)
    
    def _stop(self):
        if HAS_PYGAME:
            pygame.mixer.music.stop()
        self.playing = False
        self.play_btn.config(text="▶ Play")
        self.status_lbl.config(text="Stopped", foreground=Colors.FG)
        if self.temp_file:
            try: os.unlink(self.temp_file.name)
            except: pass
            self.temp_file = None
    
    def _check(self):
        if self.playing:
            if not pygame.mixer.music.get_busy():
                self._stop()
            else:
                self.after(100, self._check)


# =============================================================================
# DETAILS TEXT WIDGET
# =============================================================================

class DetailsText(tk.Text):
    def __init__(self, parent):
        super().__init__(parent, wrap=tk.WORD, font=('Consolas', 10),
                        bg=Colors.BG2, fg=Colors.FG, insertbackground=Colors.FG,
                        relief=tk.FLAT, padx=10, pady=10)
    
    def set_text(self, text: str):
        self.config(state=tk.NORMAL)
        self.delete('1.0', tk.END)
        self.insert('1.0', text)
        self.config(state=tk.DISABLED)
    
    def clear(self):
        self.config(state=tk.NORMAL)
        self.delete('1.0', tk.END)
        self.config(state=tk.DISABLED)


# =============================================================================
# ROOM RENDERER - OPTIMIZED WITH CACHING
# =============================================================================

class RoomRenderer:
    """Cached room rendering with tileset image caching"""
    
    def __init__(self, extractor: GameExtractor, textures: Dict[int, Image.Image]):
        self.ext = extractor
        self.textures = textures
        
        # Cache tileset images (bg_index -> full tileset image)
        self._tileset_cache: Dict[int, Image.Image] = {}
        
        # Cache rendered rooms (room_index, filter_hash) -> (image, tile_rects)
        self._room_cache: Dict[Tuple, Tuple[Image.Image, List]] = {}
        
        self._build_tileset_cache()
    
    def _build_tileset_cache(self):
        """Pre-extract all tileset/background images"""
        for bg in self.ext.backgrounds:
            if bg.tpage and bg.tpage.tex_id in self.textures:
                tpe = bg.tpage
                tex = self.textures[tpe.tex_id]
                if (tpe.src_x + tpe.src_w <= tex.width and 
                    tpe.src_y + tpe.src_h <= tex.height):
                    self._tileset_cache[bg.index] = tex.crop((
                        tpe.src_x, tpe.src_y, 
                        tpe.src_x + tpe.src_w, tpe.src_y + tpe.src_h
                    ))
    
    def get_tileset(self, bg_index: int) -> Optional[Image.Image]:
        return self._tileset_cache.get(bg_index)
    
    def get_tile_image(self, tile: RoomTile) -> Optional[Image.Image]:
        """Extract tile from cached tileset"""
        tileset = self._tileset_cache.get(tile.bg_index)
        if not tileset:
            return None
        
        tw, th = tile.width, tile.height
        if tw <= 0 or th <= 0:
            return None
        
        # Try relative coords (within tileset)
        if (tile.src_x >= 0 and tile.src_y >= 0 and
            tile.src_x + tw <= tileset.width and tile.src_y + th <= tileset.height):
            return tileset.crop((tile.src_x, tile.src_y, tile.src_x + tw, tile.src_y + th))
        
        # Try with texture atlas fallback
        bg = self.ext.backgrounds[tile.bg_index] if tile.bg_index < len(self.ext.backgrounds) else None
        if bg and bg.tpage and bg.tpage.tex_id in self.textures:
            tpe = bg.tpage
            tex = self.textures[tpe.tex_id]
            abs_x = tpe.src_x + tile.src_x
            abs_y = tpe.src_y + tile.src_y
            if (abs_x >= 0 and abs_y >= 0 and 
                abs_x + tw <= tex.width and abs_y + th <= tex.height):
                return tex.crop((abs_x, abs_y, abs_x + tw, abs_y + th))
        
        return None
    
    def clear_cache(self):
        self._room_cache.clear()
    
    def render_room(self, room: Room, show_bg=True, show_tiles=True, show_inst=True,
                   show_hidden=False, depth_min=-999999999, depth_max=999999999,
                   highlight_tile_idx=None) -> Tuple[Optional[Image.Image], List]:
        """
        Render room to single baked image.
        Returns (image, tile_screen_rects) for click detection.
        """
        if not HAS_PIL or room.width <= 0 or room.height <= 0:
            return None, []
        
        # Create cache key from filter settings
        cache_key = (room.index, show_bg, show_tiles, show_inst, show_hidden, 
                    depth_min, depth_max, highlight_tile_idx)
        
        if cache_key in self._room_cache:
            return self._room_cache[cache_key]
        
        # Always render at true 1:1 - no scaling
        w, h = room.width, room.height
        scale = 1.0
        
        tile_rects = []
        
        # Background color
        bg_color = ((room.color >> 16) & 0xFF, (room.color >> 8) & 0xFF, room.color & 0xFF, 255)
        img = Image.new('RGBA', (w, h), bg_color)
        
        # Draw non-foreground backgrounds
        if show_bg:
            self._draw_backgrounds(img, room, scale, foreground=False)
        
        # Collect drawable elements
        draw_list = []
        
        if show_tiles:
            for i, tile in enumerate(room.tiles):
                if depth_min <= tile.depth <= depth_max:
                    draw_list.append(('tile', tile.depth, tile, i))
        
        if show_inst:
            for i, inst in enumerate(room.instances):
                obj = self.ext.object_map.get(inst.obj_idx)
                if obj and (obj.visible or show_hidden):
                    if depth_min <= obj.depth <= depth_max:
                        draw_list.append(('inst', obj.depth, (obj, inst), 100000 + i))
        
        # Sort: higher depth = behind (drawn first), then by original index
        draw_list.sort(key=lambda x: (-x[1], x[3]))
        
        # Draw all elements
        for item_type, depth, item, orig_idx in draw_list:
            if item_type == 'tile':
                tile = item
                tile_img = self.get_tile_image(tile)
                if not tile_img:
                    continue
                
                # Apply flips
                if tile.scale_x < 0:
                    tile_img = tile_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                if tile.scale_y < 0:
                    tile_img = tile_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                
                # Apply scaling
                final_w = int(abs(tile.scale_x) * tile.width * scale)
                final_h = int(abs(tile.scale_y) * tile.height * scale)
                if final_w <= 0 or final_h <= 0:
                    continue
                if final_w != tile_img.width or final_h != tile_img.height:
                    tile_img = tile_img.resize((final_w, final_h), Image.Resampling.NEAREST)
                
                # Calculate position (flips shift the position)
                dx = int(tile.x * scale)
                dy = int(tile.y * scale)
                if tile.scale_x < 0:
                    dx = int((tile.x - tile.width * abs(tile.scale_x)) * scale)
                if tile.scale_y < 0:
                    dy = int((tile.y - tile.height * abs(tile.scale_y)) * scale)
                
                try:
                    img.paste(tile_img, (dx, dy), tile_img if tile_img.mode == 'RGBA' else None)
                    tile_rects.append(((dx, dy, dx + final_w, dy + final_h), tile, orig_idx))
                    
                    # Highlight selected tile
                    if highlight_tile_idx == orig_idx:
                        draw = ImageDraw.Draw(img)
                        draw.rectangle([dx, dy, dx + final_w - 1, dy + final_h - 1], 
                                       outline=(0, 255, 255, 255), width=4)
                        draw.rectangle([dx + 4, dy + 4, dx + final_w - 5, dy + final_h - 5], 
                                       outline=(255, 255, 0, 255), width=2)
                except:
                    pass
                    
            elif item_type == 'inst':
                obj, inst = item
                if obj.sprite_index < 0:
                    continue
                spr = self.ext.sprite_map.get(obj.sprite_index)
                if not spr or not spr.frames:
                    continue
                
                frame_img = self._get_sprite_frame(spr.frames[0], spr.width, spr.height)
                if not frame_img:
                    continue
                
                x = int(inst.x * scale) - int(spr.origin_x * scale)
                y = int(inst.y * scale) - int(spr.origin_y * scale)
                
                if scale != 1.0:
                    frame_img = frame_img.resize(
                        (max(1, int(frame_img.width * scale)),
                         max(1, int(frame_img.height * scale))),
                        Image.Resampling.NEAREST)
                try:
                    img.paste(frame_img, (x, y), frame_img)
                except:
                    pass
        
        # Draw foreground backgrounds
        if show_bg:
            self._draw_backgrounds(img, room, scale, foreground=True)
        
        # Cache result (but not if highlighting - that changes frequently)
        if highlight_tile_idx is None:
            self._room_cache[cache_key] = (img, tile_rects)
        
        return img, tile_rects
    
    def _draw_backgrounds(self, img: Image.Image, room: Room, scale: float, foreground: bool):
        """Draw room backgrounds"""
        w, h = img.width, img.height
        
        for bg_def in room.bg_defs:
            if not bg_def.visible or bg_def.foreground != foreground or bg_def.bg_index < 0:
                continue
            
            bg_img = self._tileset_cache.get(bg_def.bg_index)
            if not bg_img:
                continue
            
            if scale != 1.0:
                bg_img = bg_img.resize(
                    (max(1, int(bg_img.width * scale)), max(1, int(bg_img.height * scale))),
                    Image.Resampling.NEAREST)
            
            bx, by = int(bg_def.x * scale), int(bg_def.y * scale)
            
            if bg_def.stretch:
                bg_img = bg_img.resize((w, h), Image.Resampling.BILINEAR)
                img.paste(bg_img, (0, 0), bg_img if bg_img.mode == 'RGBA' else None)
            elif bg_def.tile_h or bg_def.tile_v:
                bw, bh = bg_img.width, bg_img.height
                if bw > 0 and bh > 0:
                    for ty in range(by, h if bg_def.tile_v else by + bh, bh):
                        for tx in range(bx, w if bg_def.tile_h else bx + bw, bw):
                            try:
                                img.paste(bg_img, (tx, ty), bg_img if bg_img.mode == 'RGBA' else None)
                            except:
                                pass
            else:
                try:
                    img.paste(bg_img, (bx, by), bg_img if bg_img.mode == 'RGBA' else None)
                except:
                    pass
    
    def _get_sprite_frame(self, tpe: TPAGEntry, sprite_w: int, sprite_h: int) -> Optional[Image.Image]:
        """Extract sprite frame from texture atlas"""
        if tpe.tex_id not in self.textures:
            return None
        tex = self.textures[tpe.tex_id]
        
        if (tpe.src_x < 0 or tpe.src_y < 0 or tpe.src_w <= 0 or tpe.src_h <= 0 or
            tpe.src_x + tpe.src_w > tex.width or tpe.src_y + tpe.src_h > tex.height):
            return None
        
        try:
            crop = tex.crop((tpe.src_x, tpe.src_y, tpe.src_x + tpe.src_w, tpe.src_y + tpe.src_h))
            if sprite_w > 0 and sprite_h > 0:
                full = Image.new('RGBA', (sprite_w, sprite_h), (0, 0, 0, 0))
                full.paste(crop, (tpe.tgt_x, tpe.tgt_y))
                return full
            return crop
        except:
            return None


# =============================================================================
# MAIN APPLICATION
# =============================================================================

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("GM Asset Viewer")
        self.root.geometry("1400x900")
        
        setup_dark_theme(root)
        
        self.dw: Optional[DataWin] = None
        self.ext: Optional[GameExtractor] = None
        self.textures: Dict[int, Image.Image] = {}
        self.renderer: Optional[RoomRenderer] = None
        
        self._current_room: Optional[Room] = None
        self._room_tiles_screen: List = []
        self._selected_tile_idx: Optional[int] = None
        self._last_filter_state = None
        
        self._build_ui()
        self._build_menu()
    
    def _build_menu(self):
        menubar = tk.Menu(self.root, bg=Colors.BG2, fg=Colors.FG, 
                         activebackground=Colors.ACCENT, activeforeground=Colors.FG,
                         relief=tk.FLAT, borderwidth=0)
        
        file_menu = tk.Menu(menubar, tearoff=0, bg=Colors.BG2, fg=Colors.FG,
                           activebackground=Colors.ACCENT)
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Export All...", command=self._export_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        export_menu = tk.Menu(menubar, tearoff=0, bg=Colors.BG2, fg=Colors.FG,
                             activebackground=Colors.ACCENT)
        export_menu.add_command(label="Sprites...", command=lambda: self._export("sprites"))
        export_menu.add_command(label="Audio...", command=lambda: self._export("audio"))
        export_menu.add_command(label="Textures...", command=lambda: self._export("textures"))
        export_menu.add_command(label="Rooms (JSON)...", command=lambda: self._export("rooms"))
        export_menu.add_command(label="Objects (JSON)...", command=lambda: self._export("objects"))
        menubar.add_cascade(label="Export", menu=export_menu)
        
        self.root.config(menu=menubar)
        self.root.bind('<Control-o>', lambda e: self.open_file())
    
    def _build_ui(self):
        pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left - tree
        left = ttk.Frame(pane)
        pane.add(left, weight=1)
        
        search_frm = ttk.Frame(left)
        search_frm.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frm, text="🔍").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frm, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        search_entry.bind('<KeyRelease>', self._on_search)
        ttk.Button(search_frm, text="✕", width=2, command=self._clear_search).pack(side=tk.LEFT)
        
        tree_frm = ttk.Frame(left)
        tree_frm.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(tree_frm, selectmode='browse')
        self.tree.heading('#0', text='Assets', anchor='w')
        scrollbar = ttk.Scrollbar(tree_frm, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        self.tree.bind('<Double-1>', self._on_dblclick)
        
        # Right - preview
        right = ttk.Frame(pane)
        pane.add(right, weight=3)
        
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Details tab
        self.details_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.details_frame, text='📄 Details')
        self.details_text = DetailsText(self.details_frame)
        self.details_text.pack(fill=tk.BOTH, expand=True)
        
        # Preview frames
        self.image_frame = ttk.Frame(self.notebook)
        self.image_canvas = ImageCanvas(self.image_frame)
        self.image_canvas.pack(fill=tk.BOTH, expand=True)
        
        self.anim_frame = ttk.Frame(self.notebook)
        self.anim_widget = AnimWidget(self.anim_frame)
        self.anim_widget.pack(fill=tk.BOTH, expand=True)
        
        self.audio_frame = ttk.Frame(self.notebook)
        self.audio_widget = AudioWidget(self.audio_frame)
        self.audio_widget.pack(fill=tk.BOTH, expand=True, padx=50, pady=50)
        
        # Room frame
        self.room_frame = ttk.Frame(self.notebook)
        
        # Top control bar - layer toggles
        room_ctrl = ttk.Frame(self.room_frame)
        room_ctrl.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(room_ctrl, text="Show:").pack(side=tk.LEFT, padx=(0, 5))
        
        self.show_room_bg = tk.BooleanVar(value=True)
        ttk.Checkbutton(room_ctrl, text="Backgrounds", variable=self.show_room_bg,
                       command=self._refresh_room).pack(side=tk.LEFT, padx=2)
        
        self.show_room_tiles = tk.BooleanVar(value=True)
        ttk.Checkbutton(room_ctrl, text="Tiles", variable=self.show_room_tiles,
                       command=self._refresh_room).pack(side=tk.LEFT, padx=2)
        
        self.show_room_inst = tk.BooleanVar(value=True)
        ttk.Checkbutton(room_ctrl, text="Instances", variable=self.show_room_inst,
                       command=self._refresh_room).pack(side=tk.LEFT, padx=2)
        
        self.show_room_hidden = tk.BooleanVar(value=False)
        ttk.Checkbutton(room_ctrl, text="Hidden", variable=self.show_room_hidden,
                       command=self._refresh_room).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(room_ctrl, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Label(room_ctrl, text="Depth ≥").pack(side=tk.LEFT)
        self.depth_min_var = tk.StringVar(value="-999999999")
        ttk.Entry(room_ctrl, textvariable=self.depth_min_var, width=12).pack(side=tk.LEFT, padx=2)
        
        ttk.Label(room_ctrl, text="≤").pack(side=tk.LEFT)
        self.depth_max_var = tk.StringVar(value="999999999")
        ttk.Entry(room_ctrl, textvariable=self.depth_max_var, width=12).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(room_ctrl, text="Apply", command=self._refresh_room).pack(side=tk.LEFT, padx=5)
        
        # Second control bar - view and export
        room_ctrl2 = ttk.Frame(self.room_frame)
        room_ctrl2.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        ttk.Label(room_ctrl2, text="View:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(room_ctrl2, text="1:1 (100%)", command=self._view_room_1to1).pack(side=tk.LEFT, padx=2)
        ttk.Button(room_ctrl2, text="Fit", command=self._view_room_fit).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(room_ctrl2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        ttk.Button(room_ctrl2, text="📷 Export PNG (1:1)", command=self._export_room_png).pack(side=tk.LEFT, padx=2)
        
        # Zoom indicator label
        self.room_zoom_label = ttk.Label(room_ctrl2, text="Zoom: 100%", foreground=Colors.FG_DIM)
        self.room_zoom_label.pack(side=tk.RIGHT, padx=10)
        
        self.room_canvas = ImageCanvas(self.room_frame)
        self.room_canvas.pack(fill=tk.BOTH, expand=True)
        self.room_canvas.bind('<Button-3>', self._on_room_click)
        # Use add='+' to ADD to existing zoom handlers, not replace them
        self.room_canvas.bind('<MouseWheel>', self._on_room_zoom, add='+')
        self.room_canvas.bind('<Button-4>', self._on_room_zoom, add='+')
        self.room_canvas.bind('<Button-5>', self._on_room_zoom, add='+')
        
        self.room_hint = ttk.Label(self.room_frame, 
            text="💡 Right-click tile to select • Scroll to zoom • Drag to pan • Double-click to reset",
            font=('Segoe UI', 9))
        self.room_hint.pack(side=tk.BOTTOM, pady=2)
        
        # Status bar
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT, padx=5, pady=2)
        
        self.progress = ttk.Progressbar(status_frame, maximum=1.0, length=200)
    
    def _show_preview_tab(self, tab_name: Optional[str]):
        for t in list(self.notebook.tabs())[1:]:
            self.notebook.forget(t)
        
        if tab_name == 'image':
            self.notebook.add(self.image_frame, text='🖼️ Image')
            self.notebook.select(1)
        elif tab_name == 'anim':
            self.notebook.add(self.anim_frame, text='🎬 Animation')
            self.notebook.select(1)
        elif tab_name == 'audio':
            self.notebook.add(self.audio_frame, text='🔊 Audio')
            self.notebook.select(1)
        elif tab_name == 'room':
            self.notebook.add(self.room_frame, text='🏠 Room')
            self.notebook.select(1)
        else:
            self.notebook.select(0)
    
    def _clear_previews(self):
        self.image_canvas.clear()
        self.anim_widget.clear()
        self.audio_widget.clear()
        self.room_canvas.clear()
    
    def open_file(self, path: str = None):
        if not path:
            path = filedialog.askopenfilename(
                title="Open data.win",
                filetypes=[("Game Maker data", "*.win"), ("All files", "*.*")])
        if not path:
            return
        
        self.status_var.set(f"Loading {os.path.basename(path)}...")
        self.progress.pack(side=tk.RIGHT, padx=5, pady=2)
        self.root.update()
        
        try:
            self.dw = DataWin(path)
            self.ext = GameExtractor(self.dw)
            
            def prog(msg, pct):
                self.status_var.set(msg)
                self.progress['value'] = pct
                self.root.update()
            
            self.ext.extract_all(prog)
            self._load_textures()
            
            # Create optimized renderer
            self.renderer = RoomRenderer(self.ext, self.textures)
            
            self._populate_tree()
            
            name = self.ext.info.name if self.ext.info else os.path.basename(path)
            self.root.title(f"GM Asset Viewer - {name}")
            self.status_var.set(f"Loaded {self.dw.size:,} bytes")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_var.set("Error")
        finally:
            self.progress.pack_forget()
    
    def _load_textures(self):
        self.textures.clear()
        if not HAS_PIL or not self.ext:
            return
        for i, data in enumerate(self.ext.textures):
            if data:
                try:
                    self.textures[i] = Image.open(BytesIO(data)).convert('RGBA')
                except:
                    pass
    
    def _get_sprite_frame(self, tpe: TPAGEntry, sprite_w: int = 0, sprite_h: int = 0) -> Optional[Image.Image]:
        if tpe.tex_id not in self.textures:
            return None
        tex = self.textures[tpe.tex_id]
        
        if (tpe.src_x < 0 or tpe.src_y < 0 or tpe.src_w <= 0 or tpe.src_h <= 0 or
            tpe.src_x + tpe.src_w > tex.width or tpe.src_y + tpe.src_h > tex.height):
            return None
        
        try:
            crop = tex.crop((tpe.src_x, tpe.src_y, tpe.src_x + tpe.src_w, tpe.src_y + tpe.src_h))
            if sprite_w > 0 and sprite_h > 0:
                full = Image.new('RGBA', (sprite_w, sprite_h), (0, 0, 0, 0))
                full.paste(crop, (tpe.tgt_x, tpe.tgt_y))
                return full
            return crop
        except:
            return None
    
    def _get_sprite_frames(self, spr: Sprite) -> List[Image.Image]:
        frames = []
        for tpe in spr.frames:
            frame = self._get_sprite_frame(tpe, spr.width, spr.height)
            if frame:
                frames.append(frame)
        return frames
    
    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.ext:
            return
        
        if self.ext.info:
            self.tree.insert('', 'end', text=f"📋 {self.ext.info.name or 'Game'}", values=('info',))
        
        if self.ext.sprites:
            node = self.tree.insert('', 'end', text=f"🎨 Sprites ({len(self.ext.sprites)})")
            for s in self.ext.sprites:
                self.tree.insert(node, 'end',
                    text=f"{s.name} ({s.width}×{s.height}, {len(s.frames)}f)",
                    values=('sprite', s.index))
        
        if self.ext.sounds:
            node = self.tree.insert('', 'end', text=f"🔊 Sounds ({len(self.ext.sounds)})")
            for s in self.ext.sounds:
                icon = "🔈" if s.audio_id in self.ext.audio else "❌"
                self.tree.insert(node, 'end', text=f"{icon} {s.name}", values=('sound', s.index))
        
        if self.ext.objects:
            node = self.tree.insert('', 'end', text=f"📦 Objects ({len(self.ext.objects)})")
            for o in self.ext.objects:
                spr_name = ""
                if o.sprite_index >= 0 and o.sprite_index in self.ext.sprite_map:
                    spr_name = f" → {self.ext.sprite_map[o.sprite_index].name}"
                self.tree.insert(node, 'end', text=f"{o.name}{spr_name}", values=('object', o.index))
        
        if self.ext.rooms:
            rooms_node = self.tree.insert('', 'end', text=f"🏠 Rooms ({len(self.ext.rooms)})")
            for r in self.ext.rooms:
                room_node = self.tree.insert(rooms_node, 'end',
                    text=f"{r.name} ({r.width}×{r.height})",
                    values=('room', r.index))
                
                visible_bgs = [bg for bg in r.bg_defs if bg.visible and bg.bg_index >= 0]
                if r.bg_defs:
                    bg_node = self.tree.insert(room_node, 'end', 
                        text=f"🌄 Backgrounds ({len(visible_bgs)} visible / {len(r.bg_defs)})")
                    for i, bg in enumerate(r.bg_defs):
                        if bg.bg_index >= 0:
                            bg_name = f"bg_{bg.bg_index}"
                            if bg.bg_index < len(self.ext.backgrounds):
                                bg_name = self.ext.backgrounds[bg.bg_index].name
                            vis = "✓" if bg.visible else "✗"
                            fg = "FG" if bg.foreground else "BG"
                            self.tree.insert(bg_node, 'end',
                                text=f"{vis} [{i}] {fg} {bg_name} @ ({bg.x},{bg.y})",
                                values=('room_bg', r.index, i, bg.bg_index))
                
                if r.tiles:
                    tile_node = self.tree.insert(room_node, 'end',
                        text=f"🧱 Tiles ({len(r.tiles)})")
                    sorted_tiles = sorted(enumerate(r.tiles), key=lambda x: (x[1].y, x[1].x))
                    for j, tile in sorted_tiles[:100]:
                        bg_name = f"tileset_{tile.bg_index}"
                        if 0 <= tile.bg_index < len(self.ext.backgrounds):
                            bg_name = self.ext.backgrounds[tile.bg_index].name
                        flip = ""
                        if tile.scale_x < 0: flip += "↔"
                        if tile.scale_y < 0: flip += "↕"
                        self.tree.insert(tile_node, 'end',
                            text=f"[{tile.inst_id}] ({tile.x},{tile.y}) {bg_name}{flip}",
                            values=('room_tile', r.index, j))
                    if len(r.tiles) > 100:
                        self.tree.insert(tile_node, 'end', text=f"... +{len(r.tiles)-100} more")
                
                if r.instances:
                    inst_node = self.tree.insert(room_node, 'end',
                        text=f"📦 Instances ({len(r.instances)})")
                    for j, inst in enumerate(r.instances[:100]):
                        obj_name = f"obj_{inst.obj_idx}"
                        vis_icon = ""
                        if inst.obj_idx in self.ext.object_map:
                            obj = self.ext.object_map[inst.obj_idx]
                            obj_name = obj.name
                            vis_icon = "" if obj.visible else " 👻"
                        self.tree.insert(inst_node, 'end',
                            text=f"({inst.x},{inst.y}) {obj_name}{vis_icon}",
                            values=('room_inst', r.index, j))
                    if len(r.instances) > 100:
                        self.tree.insert(inst_node, 'end', text=f"... +{len(r.instances)-100} more")
        
        if self.ext.textures:
            node = self.tree.insert('', 'end', text=f"🎞 Textures ({len(self.ext.textures)})")
            for i, data in enumerate(self.ext.textures):
                dim = ""
                if i in self.textures:
                    img = self.textures[i]
                    dim = f" {img.width}×{img.height}"
                self.tree.insert(node, 'end', text=f"texture_{i}.png{dim}", values=('texture', i))
        
        if self.ext.backgrounds:
            node = self.tree.insert('', 'end', text=f"🌄 Backgrounds ({len(self.ext.backgrounds)})")
            for b in self.ext.backgrounds:
                self.tree.insert(node, 'end', text=f"{b.name}", values=('background', b.index))
        
        # Fonts
        if self.ext.fonts:
            node = self.tree.insert('', 'end', text=f"🔤 Fonts ({len(self.ext.fonts)})")
            for f in self.ext.fonts:
                style = ""
                if f.bold: style += "B"
                if f.italic: style += "I"
                style_str = f" [{style}]" if style else ""
                self.tree.insert(node, 'end', 
                    text=f"{f.name} ({f.display_name}, {f.size:.0f}pt{style_str})",
                    values=('font', f.index))
        
        # Paths
        if self.ext.paths:
            node = self.tree.insert('', 'end', text=f"📐 Paths ({len(self.ext.paths)})")
            for p in self.ext.paths:
                flags = []
                if p.smooth: flags.append("smooth")
                if p.closed: flags.append("closed")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                self.tree.insert(node, 'end',
                    text=f"{p.name} ({len(p.points)} pts{flag_str})",
                    values=('path', p.index))
        
        # Scripts
        if self.ext.scripts:
            node = self.tree.insert('', 'end', text=f"📜 Scripts ({len(self.ext.scripts)})")
            for s in self.ext.scripts:
                self.tree.insert(node, 'end', text=f"{s.name}", values=('script', s.index))
        
        # Shaders
        if self.ext.shaders:
            node = self.tree.insert('', 'end', text=f"✨ Shaders ({len(self.ext.shaders)})")
            for s in self.ext.shaders:
                self.tree.insert(node, 'end', text=f"{s.name} ({s.type_str})", values=('shader', s.index))
        
        # Timelines
        if self.ext.timelines:
            node = self.tree.insert('', 'end', text=f"⏱️ Timelines ({len(self.ext.timelines)})")
            for t in self.ext.timelines:
                self.tree.insert(node, 'end', 
                    text=f"{t.name} ({t.moment_count} moments)",
                    values=('timeline', t.index))
        
        # Extensions
        if self.ext.extensions:
            node = self.tree.insert('', 'end', text=f"🔌 Extensions ({len(self.ext.extensions)})")
            for e in self.ext.extensions:
                self.tree.insert(node, 'end', text=f"{e.name}", values=('extension', e.index))
        
        # Chunk list (raw data view)
        if self.dw.chunks:
            node = self.tree.insert('', 'end', text=f"📦 Raw Chunks ({len(self.dw.chunks)})")
            for cid, chunk in sorted(self.dw.chunks.items(), key=lambda x: x[1].offset):
                self.tree.insert(node, 'end', 
                    text=f"{chunk.name} @ 0x{chunk.offset:08X} ({chunk.size:,} bytes)",
                    values=('chunk', cid))
    
    def _on_search(self, event=None):
        """Filter tree based on search text"""
        query = self.search_var.get().lower().strip()
        if not query:
            # Show all items
            self._set_all_visible(self.tree.get_children(), True)
            return
        
        # Hide non-matching items
        for parent in self.tree.get_children():
            self._filter_tree_item(parent, query)
    
    def _filter_tree_item(self, item, query):
        """Recursively filter tree items"""
        text = self.tree.item(item, 'text').lower()
        children = self.tree.get_children(item)
        
        # Check if this item matches
        matches = query in text
        
        # Check if any children match
        child_matches = False
        for child in children:
            if self._filter_tree_item(child, query):
                child_matches = True
        
        # Show if this item or any children match
        visible = matches or child_matches
        
        if visible:
            # Expand parents to show matching items
            self.tree.item(item, open=True)
        
        return visible
    
    def _set_all_visible(self, items, visible):
        """Recursively set visibility of all items"""
        for item in items:
            self._set_all_visible(self.tree.get_children(item), visible)
    
    def _clear_search(self):
        """Clear search and show all items"""
        self.search_var.set("")
        self._set_all_visible(self.tree.get_children(), True)
        # Collapse all
        for item in self.tree.get_children():
            self.tree.item(item, open=False)
    
    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        
        vals = self.tree.item(sel[0], 'values')
        if not vals:
            return
        
        self._clear_previews()
        
        if vals[0] == 'info':
            self._show_info()
        elif vals[0] == 'room_bg' and len(vals) >= 4:
            room_idx, bg_slot, bg_index = int(vals[1]), int(vals[2]), int(vals[3])
            self._show_room_bg(room_idx, bg_slot, bg_index)
        elif vals[0] == 'room_tile' and len(vals) >= 3:
            room_idx, tile_idx = int(vals[1]), int(vals[2])
            self._show_room_tile(room_idx, tile_idx)
        elif vals[0] == 'room_inst' and len(vals) >= 3:
            room_idx, inst_idx = int(vals[1]), int(vals[2])
            self._show_room_instance(room_idx, inst_idx)
        elif len(vals) >= 2:
            item_type, item_id = vals[0], int(vals[1])
            
            if item_type == 'sprite':
                self._show_sprite(item_id)
            elif item_type == 'sound':
                self._show_sound(item_id)
            elif item_type == 'object':
                self._show_object(item_id)
            elif item_type == 'room':
                self._show_room(item_id)
            elif item_type == 'texture':
                self._show_texture(item_id)
            elif item_type == 'background':
                self._show_background(item_id)
            elif item_type == 'font':
                self._show_font(item_id)
            elif item_type == 'path':
                self._show_path(item_id)
            elif item_type == 'script':
                self._show_script(item_id)
            elif item_type == 'shader':
                self._show_shader(item_id)
            elif item_type == 'timeline':
                self._show_timeline(item_id)
            elif item_type == 'extension':
                self._show_extension(item_id)
            elif item_type == 'chunk':
                self._show_chunk(item_id)
    
    def _on_dblclick(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], 'values')
        if not vals or len(vals) < 2:
            return
        
        item_type, item_id = vals[0], int(vals[1])
        
        if item_type == 'texture':
            self._export_texture(item_id)
        elif item_type == 'sprite':
            self._export_sprite(item_id)
        elif item_type == 'sound':
            self._export_sound(item_id)
    
    def _show_info(self):
        if not self.ext or not self.ext.info:
            return
        
        text = f"""GAME INFORMATION
{'═' * 50}

Name:      {self.ext.info.name}
Game ID:   {self.ext.info.game_id}

ASSET STATISTICS
{'─' * 50}
File Size:    {self.dw.size:,} bytes
Sprites:      {len(self.ext.sprites)}
Sounds:       {len(self.ext.sounds)}
Objects:      {len(self.ext.objects)}
Rooms:        {len(self.ext.rooms)}
Textures:     {len(self.ext.textures)}
Backgrounds:  {len(self.ext.backgrounds)}
Fonts:        {len(self.ext.fonts)}
Paths:        {len(self.ext.paths)}
Scripts:      {len(self.ext.scripts)}
Shaders:      {len(self.ext.shaders)}
Timelines:    {len(self.ext.timelines)}
Extensions:   {len(self.ext.extensions)}
Strings:      {len(self.ext.strings)}

CHUNKS IN FILE
{'─' * 50}
"""
        for cid, chunk in sorted(self.dw.chunks.items(), key=lambda x: x[1].offset):
            text += f"  {chunk.name}  @ 0x{chunk.offset:08X}  {chunk.size:>12,} bytes\n"
        
        self.details_text.set_text(text)
        self._show_preview_tab(None)
    
    def _show_sprite(self, idx: int):
        spr = self.ext.sprite_map.get(idx)
        if not spr:
            self.details_text.set_text("Sprite not found")
            self._show_preview_tab(None)
            return
        
        text = f"""SPRITE: {spr.name}
{'─' * 50}

Index:      {spr.index}
Size:       {spr.width} × {spr.height}
Origin:     ({spr.origin_x}, {spr.origin_y})
Frames:     {len(spr.frames)}

FRAME DATA:
"""
        for i, f in enumerate(spr.frames[:10]):
            text += f"  [{i}] tex:{f.tex_id} src:({f.src_x},{f.src_y}) {f.src_w}×{f.src_h}"
            text += f" → tgt:({f.tgt_x},{f.tgt_y}) {f.tgt_w}×{f.tgt_h}\n"
        if len(spr.frames) > 10:
            text += f"  ... +{len(spr.frames)-10} more frames\n"
        
        text += "\nDouble-click to export all frames."
        
        self.details_text.set_text(text)
        
        frames = self._get_sprite_frames(spr)
        if frames:
            self.anim_widget.set_frames(frames, autoplay=True)
            self._show_preview_tab('anim')
        else:
            self.details_text.set_text(text + "\n\n⚠ No frames could be extracted")
            self._show_preview_tab(None)
    
    def _show_sound(self, idx: int):
        snd = next((s for s in self.ext.sounds if s.index == idx), None)
        if not snd:
            self.details_text.set_text("Sound not found")
            self._show_preview_tab(None)
            return
        
        has_data = snd.audio_id in self.ext.audio
        
        text = f"""SOUND: {snd.name}
{'─' * 50}

Index:      {snd.index}
Type:       {snd.type_str}
File:       {snd.file_str}
Volume:     {snd.volume:.2f}
Pitch:      {snd.pitch:.2f}
Audio ID:   {snd.audio_id}
Has Data:   {'✓' if has_data else '✗'}
"""
        if has_data:
            data = self.ext.audio[snd.audio_id]
            text += f"Data Size:  {len(data):,} bytes\n"
        
        text += "\nDouble-click to export."
        
        self.details_text.set_text(text)
        
        if has_data:
            self.audio_widget.set_audio(self.ext.audio[snd.audio_id], snd.name, snd, autoplay=True)
            self._show_preview_tab('audio')
        else:
            self._show_preview_tab(None)
    
    def _show_object(self, idx: int):
        obj = self.ext.object_map.get(idx)
        if not obj:
            self.details_text.set_text("Object not found")
            self._show_preview_tab(None)
            return
        
        spr_name = "None"
        if obj.sprite_index >= 0 and obj.sprite_index in self.ext.sprite_map:
            spr_name = self.ext.sprite_map[obj.sprite_index].name
        
        parent_name = "None"
        if obj.parent_index >= 0 and obj.parent_index in self.ext.object_map:
            parent_name = self.ext.object_map[obj.parent_index].name
        
        text = f"""OBJECT: {obj.name}
{'─' * 50}

Index:      {obj.index}
Sprite:     {spr_name} [{obj.sprite_index}]
Visible:    {'✓' if obj.visible else '✗'}
Solid:      {'✓' if obj.solid else '✗'}
Depth:      {obj.depth}
Parent:     {parent_name} [{obj.parent_index}]
Mask:       {obj.mask_index}
"""
        
        self.details_text.set_text(text)
        
        if obj.sprite_index >= 0 and obj.sprite_index in self.ext.sprite_map:
            spr = self.ext.sprite_map[obj.sprite_index]
            frames = self._get_sprite_frames(spr)
            if frames:
                self.anim_widget.set_frames(frames, autoplay=True)
                self._show_preview_tab('anim')
                return
        
        self._show_preview_tab(None)
    
    def _show_room(self, idx: int):
        room = next((r for r in self.ext.rooms if r.index == idx), None)
        if not room:
            self.details_text.set_text("Room not found")
            self._show_preview_tab(None)
            return
        
        self._current_room = room
        self._selected_tile_idx = None
        
        # Clear render cache when switching rooms
        if self.renderer:
            self.renderer.clear_cache()
        
        visible_inst = sum(1 for inst in room.instances 
                         if inst.obj_idx in self.ext.object_map 
                         and self.ext.object_map[inst.obj_idx].visible)
        hidden_inst = len(room.instances) - visible_inst
        visible_bgs = [bg for bg in room.bg_defs if bg.visible and bg.bg_index >= 0]
        
        text = f"""ROOM: {room.name}
{'─' * 50}

Index:      {room.index}
Size:       {room.width} × {room.height} pixels (1:1 render)
Speed:      {room.speed} fps
Color:      #{room.color:06X}

LAYER COUNTS:
  Backgrounds:  {len(visible_bgs)} visible / {len(room.bg_defs)} total
  Tiles:        {len(room.tiles)}
  Instances:    {visible_inst} visible / {hidden_inst} hidden

CONTROLS:
  • Use checkboxes to toggle layers
  • "1:1 (100%)" shows true pixel size
  • "Export PNG" saves full resolution image
  • Right-click tiles to inspect
"""
        
        self.details_text.set_text(text)
        
        if HAS_PIL:
            self._refresh_room(fit=True)
            self._update_room_zoom_label()
            self._show_preview_tab('room')
        else:
            self._show_preview_tab(None)
    
    def _get_filter_state(self):
        """Get current filter settings as tuple for comparison"""
        try:
            depth_min = int(self.depth_min_var.get())
        except:
            depth_min = -999999999
        try:
            depth_max = int(self.depth_max_var.get())
        except:
            depth_max = 999999999
        
        return (
            self.show_room_bg.get(),
            self.show_room_tiles.get(),
            self.show_room_inst.get(),
            self.show_room_hidden.get(),
            depth_min,
            depth_max
        )
    
    def _refresh_room(self, fit=False):
        """Refresh room render - uses cached image if filters unchanged"""
        if not self._current_room or not HAS_PIL or not self.renderer:
            return
        
        show_bg, show_tiles, show_inst, show_hidden, depth_min, depth_max = self._get_filter_state()
        
        img, self._room_tiles_screen = self.renderer.render_room(
            self._current_room,
            show_bg=show_bg,
            show_tiles=show_tiles,
            show_inst=show_inst,
            show_hidden=show_hidden,
            depth_min=depth_min,
            depth_max=depth_max,
            highlight_tile_idx=self._selected_tile_idx
        )
        
        if img:
            self.room_canvas.set_image(img, fit=fit)
            self._update_room_zoom_label()
    
    def _on_room_click(self, event):
        """Handle right-click on room canvas to select tile"""
        if not self._current_room or not self._room_tiles_screen:
            return
        
        canvas = self.room_canvas
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        
        click_x = event.x - cw/2 - canvas.offset_x
        click_y = event.y - ch/2 - canvas.offset_y
        
        img_x = click_x / canvas.zoom
        img_y = click_y / canvas.zoom
        
        if canvas.pil_image:
            img_x += canvas.pil_image.width / 2
            img_y += canvas.pil_image.height / 2
        
        clicked_tile = None
        clicked_idx = None
        for rect, tile, idx in reversed(self._room_tiles_screen):
            x1, y1, x2, y2 = rect
            if x1 <= img_x <= x2 and y1 <= img_y <= y2:
                clicked_tile = tile
                clicked_idx = idx
                break
        
        if clicked_tile:
            self._selected_tile_idx = clicked_idx
            
            bg_name = f"tileset_{clicked_tile.bg_index}"
            if 0 <= clicked_tile.bg_index < len(self.ext.backgrounds):
                bg_name = self.ext.backgrounds[clicked_tile.bg_index].name
            
            flip = ""
            if clicked_tile.scale_x < 0: flip += "↔"
            if clicked_tile.scale_y < 0: flip += "↕"
            
            self.status_var.set(
                f"Selected: [{clicked_tile.inst_id}] ({clicked_tile.x},{clicked_tile.y}) "
                f"{bg_name} depth:{clicked_tile.depth} {flip}"
            )
            
            self._show_room_tile(self._current_room.index, clicked_idx)
            self._refresh_room()
    
    def _on_room_zoom(self, event):
        """Update zoom label when zooming"""
        self.root.after(10, self._update_room_zoom_label)
    
    def _update_room_zoom_label(self):
        """Update the zoom percentage label"""
        if hasattr(self, 'room_zoom_label') and self.room_canvas.pil_image:
            zoom_pct = self.room_canvas.zoom * 100
            self.room_zoom_label.config(text=f"Zoom: {zoom_pct:.0f}%")
    
    def _view_room_1to1(self):
        """Set room view to exactly 1:1 (100% zoom)"""
        if not self.room_canvas.pil_image:
            return
        self.room_canvas.zoom = 1.0
        self.room_canvas.offset_x = 0
        self.room_canvas.offset_y = 0
        self.room_canvas._redraw()
        self._update_room_zoom_label()
    
    def _view_room_fit(self):
        """Fit room to canvas"""
        if not self.room_canvas.pil_image:
            return
        self.room_canvas._fit_image()
        self._update_room_zoom_label()
    
    def _export_room_png(self):
        """Export the current room as a 1:1 PNG file"""
        if not self._current_room or not self.renderer:
            messagebox.showwarning("Export", "No room selected")
            return
        
        # Render at true 1:1 without any highlight
        show_bg, show_tiles, show_inst, show_hidden, depth_min, depth_max = self._get_filter_state()
        
        self.status_var.set("Rendering room at 1:1...")
        self.root.update()
        
        try:
            img, _ = self.renderer.render_room(
                self._current_room,
                show_bg=show_bg,
                show_tiles=show_tiles,
                show_inst=show_inst,
                show_hidden=show_hidden,
                depth_min=depth_min,
                depth_max=depth_max,
                highlight_tile_idx=None  # No highlight for export
            )
            
            if not img:
                messagebox.showerror("Export", "Failed to render room")
                return
            
            # Ask for save location
            default_name = f"{self._current_room.name}_1to1.png"
            path = filedialog.asksaveasfilename(
                defaultextension=".png",
                initialfile=default_name,
                filetypes=[("PNG files", "*.png"), ("All files", "*.*")]
            )
            
            if path:
                img.save(path, "PNG")
                self.status_var.set(f"Exported {img.width}×{img.height} room to {os.path.basename(path)}")
                messagebox.showinfo("Export", f"Room exported successfully!\n\nSize: {img.width} × {img.height} pixels\nFile: {os.path.basename(path)}")
            else:
                self.status_var.set("Export cancelled")
                
        except Exception as e:
            messagebox.showerror("Export Error", str(e))
            self.status_var.set("Export failed")
    
    def _show_room_bg(self, room_idx: int, bg_slot: int, bg_index: int):
        room = next((r for r in self.ext.rooms if r.index == room_idx), None)
        if not room or bg_slot >= len(room.bg_defs):
            self.details_text.set_text("Background not found")
            self._show_preview_tab(None)
            return
        
        bg_def = room.bg_defs[bg_slot]
        bg_name = f"bg_{bg_index}"
        if 0 <= bg_index < len(self.ext.backgrounds):
            bg_name = self.ext.backgrounds[bg_index].name
        
        text = f"""ROOM BACKGROUND LAYER
{'─' * 50}

Room:       {room.name}
Slot:       {bg_slot}
Background: {bg_name} [index: {bg_index}]

PROPERTIES:
  Visible:    {'✓' if bg_def.visible else '✗'}
  Foreground: {'✓' if bg_def.foreground else '✗'}
  Position:   ({bg_def.x}, {bg_def.y})
  Tile H:     {'✓' if bg_def.tile_h else '✗'}
  Tile V:     {'✓' if bg_def.tile_v else '✗'}
  Stretch:    {'✓' if bg_def.stretch else '✗'}
"""
        
        self.details_text.set_text(text)
        
        if self.renderer and 0 <= bg_index < len(self.ext.backgrounds):
            img = self.renderer.get_tileset(bg_index)
            if img:
                self.image_canvas.set_image(img, fit=True)
                self._show_preview_tab('image')
                return
        
        self._show_preview_tab(None)
    
    def _show_room_tile(self, room_idx: int, tile_idx: int):
        room = next((r for r in self.ext.rooms if r.index == room_idx), None)
        if not room or tile_idx >= len(room.tiles):
            self.details_text.set_text("Tile not found")
            self._show_preview_tab(None)
            return
        
        tile = room.tiles[tile_idx]
        bg_name = f"tileset_{tile.bg_index}"
        if 0 <= tile.bg_index < len(self.ext.backgrounds):
            bg_name = self.ext.backgrounds[tile.bg_index].name
        
        flip_h = "✓ FLIP" if tile.scale_x < 0 else ""
        flip_v = "✓ FLIP" if tile.scale_y < 0 else ""
        
        text = f"""ROOM TILE
{'─' * 50}

Room:       {room.name}
Tile Index: {tile_idx}
Instance:   {tile.inst_id}

TILE PROPERTIES:
  Position:   ({tile.x}, {tile.y})
  Size:       {tile.width} × {tile.height}
  Depth:      {tile.depth}
  Tileset:    {bg_name} [index: {tile.bg_index}]
  Source:     ({tile.src_x}, {tile.src_y})

TRANSFORMS:
  Scale X:    {tile.scale_x:.2f} {flip_h}
  Scale Y:    {tile.scale_y:.2f} {flip_v}
  Color:      #{tile.color:08X}
"""
        
        self.details_text.set_text(text)
        
        tile_img = None
        if self.renderer:
            tile_img = self.renderer.get_tile_image(tile)
            if tile_img:
                if tile.scale_x < 0:
                    tile_img = tile_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                if tile.scale_y < 0:
                    tile_img = tile_img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        
        if tile_img:
            self.image_canvas.set_image(tile_img, fit=True)
            self._show_preview_tab('image')
        else:
            self._show_preview_tab(None)
    
    def _show_room_instance(self, room_idx: int, inst_idx: int):
        room = next((r for r in self.ext.rooms if r.index == room_idx), None)
        if not room or inst_idx >= len(room.instances):
            self.details_text.set_text("Instance not found")
            self._show_preview_tab(None)
            return
        
        inst = room.instances[inst_idx]
        obj = self.ext.object_map.get(inst.obj_idx)
        
        obj_name = f"object_{inst.obj_idx}"
        spr_name = "None"
        spr = None
        
        if obj:
            obj_name = obj.name
            if obj.sprite_index >= 0 and obj.sprite_index in self.ext.sprite_map:
                spr = self.ext.sprite_map[obj.sprite_index]
                spr_name = spr.name
        
        text = f"""ROOM INSTANCE
{'─' * 50}

Room:       {room.name}
Instance:   {inst_idx} (ID: {inst.inst_id})

PROPERTIES:
  Position:   ({inst.x}, {inst.y})
  Object:     {obj_name} [index: {inst.obj_idx}]
"""
        
        if obj:
            text += f"""
OBJECT PROPERTIES:
  Sprite:     {spr_name} [{obj.sprite_index}]
  Visible:    {'✓' if obj.visible else '✗'}
  Solid:      {'✓' if obj.solid else '✗'}
  Depth:      {obj.depth}
"""
        
        self.details_text.set_text(text)
        
        if spr:
            frames = self._get_sprite_frames(spr)
            if frames:
                self.anim_widget.set_frames(frames, autoplay=True)
                self._show_preview_tab('anim')
                return
        
        self._show_preview_tab(None)
    
    def _show_texture(self, idx: int):
        text = f"""TEXTURE: texture_{idx}.png
{'─' * 50}

"""
        if idx in self.textures:
            img = self.textures[idx]
            data_size = len(self.ext.textures[idx]) if idx < len(self.ext.textures) else 0
            text += f"""Dimensions:  {img.width} × {img.height}
Data Size:   {data_size:,} bytes
Mode:        {img.mode}

Double-click to export.
"""
            self.details_text.set_text(text)
            self.image_canvas.set_image(img, fit=True)
            self._show_preview_tab('image')
        else:
            text += "⚠ Texture data not available."
            self.details_text.set_text(text)
            self._show_preview_tab(None)
    
    def _show_background(self, idx: int):
        bg = next((b for b in self.ext.backgrounds if b.index == idx), None)
        if not bg:
            self.details_text.set_text("Background not found")
            self._show_preview_tab(None)
            return
        
        text = f"""BACKGROUND: {bg.name}
{'─' * 50}

Index:  {bg.index}
"""
        
        if bg.tpage:
            text += f"""
Texture ID:  {bg.tpage.tex_id}
Source:      ({bg.tpage.src_x}, {bg.tpage.src_y}) {bg.tpage.src_w}×{bg.tpage.src_h}
"""
        
        self.details_text.set_text(text)
        
        if self.renderer:
            img = self.renderer.get_tileset(idx)
            if img:
                self.image_canvas.set_image(img, fit=True)
                self._show_preview_tab('image')
                return
        
        self._show_preview_tab(None)
    
    def _show_font(self, idx: int):
        font = next((f for f in self.ext.fonts if f.index == idx), None)
        if not font:
            self.details_text.set_text("Font not found")
            self._show_preview_tab(None)
            return
        
        style = []
        if font.bold: style.append("Bold")
        if font.italic: style.append("Italic")
        style_str = ", ".join(style) if style else "Regular"
        
        text = f"""FONT: {font.name}
{'─' * 50}

Index:        {font.index}
Display Name: {font.display_name}
Size:         {font.size:.1f} pt
Style:        {style_str}
Char Range:   {font.range_start} - {font.range_end} ({font.range_end - font.range_start + 1} chars)
Glyphs:       {len(font.glyphs)}
"""
        
        if font.tpage:
            text += f"""
TEXTURE:
  Texture ID: {font.tpage.tex_id}
  Source:     ({font.tpage.src_x}, {font.tpage.src_y}) {font.tpage.src_w}×{font.tpage.src_h}
"""
        
        if font.glyphs:
            text += f"\nGLYPH SAMPLES (first 20):\n"
            for g in font.glyphs[:20]:
                char = chr(g.char) if 32 <= g.char < 127 else f"\\x{g.char:02X}"
                text += f"  '{char}' ({g.char}): pos=({g.x},{g.y}) size={g.w}×{g.h} shift={g.shift}\n"
            if len(font.glyphs) > 20:
                text += f"  ... +{len(font.glyphs)-20} more glyphs\n"
        
        self.details_text.set_text(text)
        
        # Try to show font texture
        if font.tpage and font.tpage.tex_id in self.textures:
            tpe = font.tpage
            tex = self.textures[tpe.tex_id]
            if (tpe.src_x + tpe.src_w <= tex.width and tpe.src_y + tpe.src_h <= tex.height):
                img = tex.crop((tpe.src_x, tpe.src_y, tpe.src_x + tpe.src_w, tpe.src_y + tpe.src_h))
                self.image_canvas.set_image(img, fit=True)
                self._show_preview_tab('image')
                return
        
        self._show_preview_tab(None)
    
    def _show_path(self, idx: int):
        path = next((p for p in self.ext.paths if p.index == idx), None)
        if not path:
            self.details_text.set_text("Path not found")
            self._show_preview_tab(None)
            return
        
        flags = []
        if path.smooth: flags.append("Smooth")
        if path.closed: flags.append("Closed")
        
        text = f"""PATH: {path.name}
{'─' * 50}

Index:      {path.index}
Smooth:     {'✓' if path.smooth else '✗'}
Closed:     {'✓' if path.closed else '✗'}
Precision:  {path.precision}
Points:     {len(path.points)}
"""
        
        if path.points:
            # Calculate bounds
            xs = [p.x for p in path.points]
            ys = [p.y for p in path.points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            text += f"""
BOUNDS:
  X: {min_x:.1f} to {max_x:.1f} (width: {max_x - min_x:.1f})
  Y: {min_y:.1f} to {max_y:.1f} (height: {max_y - min_y:.1f})

POINTS:
"""
            for i, pt in enumerate(path.points[:30]):
                text += f"  [{i}] ({pt.x:.1f}, {pt.y:.1f}) speed={pt.speed:.2f}\n"
            if len(path.points) > 30:
                text += f"  ... +{len(path.points)-30} more points\n"
            
            # Draw path visualization
            if HAS_PIL and len(path.points) >= 2:
                padding = 20
                w = int(max_x - min_x + padding * 2)
                h = int(max_y - min_y + padding * 2)
                if w > 0 and h > 0:
                    # Ensure minimum size
                    w = max(100, min(800, w))
                    h = max(100, min(800, h))
                    scale = min(800 / max(w, 1), 800 / max(h, 1), 1.0)
                    w, h = int(w * scale), int(h * scale)
                    
                    img = Image.new('RGBA', (w, h), (30, 30, 30, 255))
                    draw = ImageDraw.Draw(img)
                    
                    # Draw path
                    scaled_points = []
                    for pt in path.points:
                        px = int((pt.x - min_x + padding) * scale)
                        py = int((pt.y - min_y + padding) * scale)
                        scaled_points.append((px, py))
                    
                    if len(scaled_points) >= 2:
                        # Draw lines
                        for i in range(len(scaled_points) - 1):
                            draw.line([scaled_points[i], scaled_points[i+1]], fill=(100, 200, 255), width=2)
                        if path.closed and len(scaled_points) >= 2:
                            draw.line([scaled_points[-1], scaled_points[0]], fill=(100, 200, 255), width=2)
                        
                        # Draw points
                        for i, pt in enumerate(scaled_points):
                            color = (255, 100, 100) if i == 0 else (100, 255, 100) if i == len(scaled_points)-1 else (255, 255, 100)
                            draw.ellipse([pt[0]-4, pt[1]-4, pt[0]+4, pt[1]+4], fill=color)
                    
                    self.image_canvas.set_image(img, fit=True)
                    self._show_preview_tab('image')
                    self.details_text.set_text(text)
                    return
        
        self.details_text.set_text(text)
        self._show_preview_tab(None)
    
    def _show_script(self, idx: int):
        script = next((s for s in self.ext.scripts if s.index == idx), None)
        if not script:
            self.details_text.set_text("Script not found")
            self._show_preview_tab(None)
            return
        
        text = f"""SCRIPT: {script.name}
{'─' * 50}

Index:    {script.index}
Code ID:  {script.code_id}

Note: Script bytecode is stored in the CODE chunk.
Decompilation requires additional tools like UndertaleModTool.
"""
        
        self.details_text.set_text(text)
        self._show_preview_tab(None)
    
    def _show_shader(self, idx: int):
        shader = next((s for s in self.ext.shaders if s.index == idx), None)
        if not shader:
            self.details_text.set_text("Shader not found")
            self._show_preview_tab(None)
            return
        
        text = f"""SHADER: {shader.name}
{'─' * 50}

Index:  {shader.index}
Type:   {shader.type_str}

═══ VERTEX SHADER ═══
{shader.vertex_code[:2000] if shader.vertex_code else '(empty)'}
{'... (truncated)' if len(shader.vertex_code) > 2000 else ''}

═══ FRAGMENT SHADER ═══
{shader.fragment_code[:2000] if shader.fragment_code else '(empty)'}
{'... (truncated)' if len(shader.fragment_code) > 2000 else ''}
"""
        
        self.details_text.set_text(text)
        self._show_preview_tab(None)
    
    def _show_timeline(self, idx: int):
        timeline = next((t for t in self.ext.timelines if t.index == idx), None)
        if not timeline:
            self.details_text.set_text("Timeline not found")
            self._show_preview_tab(None)
            return
        
        text = f"""TIMELINE: {timeline.name}
{'─' * 50}

Index:    {timeline.index}
Moments:  {timeline.moment_count}

Note: Timeline moment actions are stored as GML bytecode.
"""
        
        self.details_text.set_text(text)
        self._show_preview_tab(None)
    
    def _show_extension(self, idx: int):
        ext = next((e for e in self.ext.extensions if e.index == idx), None)
        if not ext:
            self.details_text.set_text("Extension not found")
            self._show_preview_tab(None)
            return
        
        text = f"""EXTENSION: {ext.name}
{'─' * 50}

Index:       {ext.index}
Class Name:  {ext.class_name}
"""
        
        self.details_text.set_text(text)
        self._show_preview_tab(None)
    
    def _show_chunk(self, cid: int):
        if cid not in self.dw.chunks:
            self.details_text.set_text("Chunk not found")
            self._show_preview_tab(None)
            return
        
        chunk = self.dw.chunks[cid]
        
        # Get hex dump of first 256 bytes
        data_start = chunk.data_start
        data_end = min(data_start + 256, data_start + chunk.size)
        hex_lines = []
        for i in range(data_start, data_end, 16):
            row_bytes = self.dw.data[i:min(i+16, data_end)]
            hex_part = ' '.join(f'{b:02X}' for b in row_bytes)
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row_bytes)
            hex_lines.append(f"  {i:08X}  {hex_part:<48}  {ascii_part}")
        
        text = f"""CHUNK: {chunk.name}
{'─' * 50}

Offset:     0x{chunk.offset:08X}
Size:       {chunk.size:,} bytes
Data Start: 0x{chunk.data_start:08X}

HEX DUMP (first 256 bytes):
{'─' * 70}
"""
        text += '\n'.join(hex_lines)
        
        if chunk.size > 256:
            text += f"\n  ... +{chunk.size - 256:,} more bytes"
        
        self.details_text.set_text(text)
        self._show_preview_tab(None)
    
    def _export_texture(self, idx: int):
        if idx >= len(self.ext.textures):
            return
        data = self.ext.textures[idx]
        if not data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", initialfile=f"texture_{idx}.png")
        if path:
            with open(path, 'wb') as f:
                f.write(data)
            self.status_var.set(f"Exported {os.path.basename(path)}")
    
    def _export_sprite(self, idx: int):
        spr = self.ext.sprite_map.get(idx)
        if not spr or not HAS_PIL:
            return
        folder = filedialog.askdirectory(title=f"Export {spr.name}")
        if not folder:
            return
        out = Path(folder) / spr.name
        out.mkdir(exist_ok=True)
        frames = self._get_sprite_frames(spr)
        for i, f in enumerate(frames):
            f.save(out / f"frame_{i:04d}.png")
        self.status_var.set(f"Exported {len(frames)} frames")
    
    def _export_sound(self, idx: int):
        snd = next((s for s in self.ext.sounds if s.index == idx), None)
        if not snd or snd.audio_id not in self.ext.audio:
            return
        data = self.ext.audio[snd.audio_id]
        ext = '.ogg' if data[:4] == b'OggS' else '.wav' if data[:4] == b'RIFF' else '.mp3'
        path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=f"{snd.name}{ext}")
        if path:
            with open(path, 'wb') as f:
                f.write(data)
            self.status_var.set(f"Exported {os.path.basename(path)}")
    
    def _export(self, category: str):
        if not self.ext:
            return
        folder = filedialog.askdirectory(title=f"Export {category}")
        if not folder:
            return
        out = Path(folder)
        
        try:
            if category == "textures":
                (out / "textures").mkdir(exist_ok=True)
                for i, data in enumerate(self.ext.textures):
                    if data:
                        with open(out / "textures" / f"texture_{i}.png", 'wb') as f:
                            f.write(data)
            elif category == "sprites" and HAS_PIL:
                sprites_dir = out / "sprites"
                sprites_dir.mkdir(exist_ok=True)
                for spr in self.ext.sprites:
                    frames = self._get_sprite_frames(spr)
                    if frames:
                        spr_dir = sprites_dir / spr.name
                        spr_dir.mkdir(exist_ok=True)
                        for i, f in enumerate(frames):
                            f.save(spr_dir / f"frame_{i:04d}.png")
            elif category == "audio":
                audio_dir = out / "audio"
                audio_dir.mkdir(exist_ok=True)
                id_to_name = {s.audio_id: s.name for s in self.ext.sounds if s.audio_id >= 0}
                for aid, data in self.ext.audio.items():
                    name = id_to_name.get(aid, f"audio_{aid}")
                    ext = '.ogg' if data[:4] == b'OggS' else '.wav' if data[:4] == b'RIFF' else '.bin'
                    with open(audio_dir / f"{name}{ext}", 'wb') as f:
                        f.write(data)
            elif category == "rooms":
                rooms_dir = out / "rooms"
                rooms_dir.mkdir(exist_ok=True)
                for r in self.ext.rooms:
                    with open(rooms_dir / f"{r.name}.json", 'w') as f:
                        json.dump(asdict(r), f, indent=2)
            elif category == "objects":
                with open(out / "objects.json", 'w') as f:
                    json.dump([asdict(o) for o in self.ext.objects], f, indent=2)
            
            messagebox.showinfo("Success", f"Exported {category}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def _export_all(self):
        if not self.ext:
            return
        folder = filedialog.askdirectory(title="Export all")
        if not folder:
            return
        for cat in ["textures", "sprites", "audio", "rooms", "objects"]:
            try:
                self._export(cat)
            except:
                pass
        messagebox.showinfo("Done", f"Exported to {folder}")


def main():
    root = tk.Tk()
    app = App(root)
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        root.after(100, lambda: app.open_file(sys.argv[1]))
    root.mainloop()


if __name__ == '__main__':
    main()