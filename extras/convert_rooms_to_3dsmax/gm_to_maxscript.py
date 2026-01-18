#!/usr/bin/env python3
"""
Game Maker Room to MaxScript Converter
Reads data.win and generates MaxScript files to reconstruct rooms in 3ds Max

This bridges the gm_asset_viewer's data parsing with StageEditor's build system.
"""

import struct
import os
import sys
import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# =============================================================================
# CONFIGURATION
# =============================================================================

# Paths - update these to match your setup
DEFAULT_SPRITE_PATH = r"G:\SteamLibrary\steamapps\common\Parasites In the City\sprites"
DEFAULT_DATA_WIN = r"G:\SteamLibrary\steamapps\common\Parasites In the City\data.win"
DEFAULT_OUTPUT_DIR = r"E:\MaxScripts\ParasiteRooms"


# =============================================================================
# DATA STRUCTURES (matching gm_asset_viewer.py)
# =============================================================================

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
class GameObject:
    index: int; name: str; sprite_index: int
    visible: bool; solid: bool; depth: int
    parent_index: int; mask_index: int

@dataclass
class RoomInst:
    x: int; y: int; obj_idx: int; inst_id: int
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    color: int = 0xFFFFFFFF

@dataclass
class RoomBgDef:
    visible: bool; foreground: bool; bg_index: int
    x: int; y: int; tile_h: bool; tile_v: bool; stretch: bool

@dataclass
class RoomTile:
    x: int; y: int; bg_index: int
    src_x: int; src_y: int
    width: int; height: int; depth: int
    inst_id: int = 0
    scale_x: float = 1.0; scale_y: float = 1.0
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


# =============================================================================
# DATA.WIN PARSER
# =============================================================================

class ChunkID:
    FORM = 0x4D524F46; GEN8 = 0x384E4547; SOND = 0x444E4F53; SPRT = 0x54525053
    BGND = 0x444E4742; OBJT = 0x544A424F; ROOM = 0x4D4F4F52; TPAG = 0x47415054
    STRG = 0x47525453; TXTR = 0x52545854; AUDO = 0x4F445541


class DataWin:
    def __init__(self, path: str):
        with open(path, 'rb') as f:
            self.data = f.read()
        self.size = len(self.data)
        self.chunks: Dict[int, tuple] = {}
        self._parse()
    
    def _parse(self):
        if self.u32(0) != ChunkID.FORM:
            raise ValueError("Invalid data.win")
        pos = 8
        while pos < self.size - 8:
            cid, sz = self.u32(pos), self.u32(pos + 4)
            self.chunks[cid] = (pos, sz, pos + 8)  # offset, size, data_start
            pos += 8 + sz
    
    def u16(self, o): return struct.unpack_from('<H', self.data, o)[0]
    def i32(self, o): return struct.unpack_from('<i', self.data, o)[0]
    def u32(self, o): return struct.unpack_from('<I', self.data, o)[0]
    def f32(self, o): return struct.unpack_from('<f', self.data, o)[0]
    
    def c_str(self, o, max_len=200):
        if o == 0 or o >= self.size: return ""
        end = self.data.find(b'\x00', o, o + max_len)
        return self.data[o:end].decode('utf-8', errors='replace') if end > o else ""


class GameExtractor:
    """Extracts game data from data.win"""
    
    def __init__(self, dw: DataWin):
        self.dw = dw
        self.sprites: List[Sprite] = []
        self.objects: List[GameObject] = []
        self.rooms: List[Room] = []
        self.backgrounds: List[Background] = []
        self.sprite_map: Dict[int, Sprite] = {}
        self.object_map: Dict[int, GameObject] = {}
        self.bg_map: Dict[int, Background] = {}
    
    def extract_all(self, verbose=False):
        if verbose: print("Extracting sprites...")
        self._sprites()
        if verbose: print(f"  Found {len(self.sprites)} sprites")
        
        if verbose: print("Extracting objects...")
        self._objects()
        if verbose: print(f"  Found {len(self.objects)} objects")
        
        if verbose: print("Extracting backgrounds...")
        self._backgrounds()
        if verbose: print(f"  Found {len(self.backgrounds)} backgrounds")
        
        if verbose: print("Extracting rooms...")
        self._rooms()
        if verbose: print(f"  Found {len(self.rooms)} rooms")
    
    def _sprites(self):
        if ChunkID.SPRT not in self.dw.chunks: return
        _, _, off = self.dw.chunks[ChunkID.SPRT]
        count = self.dw.u32(off)
        
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
    
    def _objects(self):
        if ChunkID.OBJT not in self.dw.chunks: return
        _, _, off = self.dw.chunks[ChunkID.OBJT]
        count = self.dw.u32(off)
        
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
    
    def _backgrounds(self):
        if ChunkID.BGND not in self.dw.chunks: return
        _, _, off = self.dw.chunks[ChunkID.BGND]
        count = self.dw.u32(off)
        
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
            bg = Background(i, name, tpage)
            self.backgrounds.append(bg)
            self.bg_map[i] = bg
    
    def _rooms(self):
        if ChunkID.ROOM not in self.dw.chunks: return
        _, _, off = self.dw.chunks[ChunkID.ROOM]
        count = self.dw.u32(off)
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i*4)
            if not ptr or ptr >= self.dw.size - 100: continue
            
            name_ptr = self.dw.u32(ptr)
            width = self.dw.u32(ptr + 0x08)
            height = self.dw.u32(ptr + 0x0C)
            speed = self.dw.u32(ptr + 0x10)
            color = self.dw.u32(ptr + 0x18)
            
            # Background definitions
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
            
            # Instances
            instances = []
            inst_ptr = self.dw.u32(ptr + 0x30)
            if inst_ptr and inst_ptr < self.dw.size - 4:
                ic = self.dw.u32(inst_ptr)
                for j in range(min(ic, 10000)):
                    ip = self.dw.u32(inst_ptr + 4 + j*4)
                    if ip and ip < self.dw.size - 16:
                        # Check if we have extended instance data
                        x = self.dw.i32(ip)
                        y = self.dw.i32(ip+4)
                        obj_idx = self.dw.i32(ip+8)
                        inst_id = self.dw.u32(ip+12)
                        
                        # Try to read scale/rotation if available
                        scale_x = 1.0
                        scale_y = 1.0
                        rotation = 0.0
                        color = 0xFFFFFFFF
                        
                        # Some GMS versions have extended instance data
                        if ip + 32 <= self.dw.size:
                            try:
                                scale_x = self.dw.f32(ip + 16)
                                scale_y = self.dw.f32(ip + 20)
                                # Validate scales
                                if abs(scale_x) > 100 or abs(scale_y) > 100:
                                    scale_x = 1.0
                                    scale_y = 1.0
                            except:
                                pass
                        
                        instances.append(RoomInst(x, y, obj_idx, inst_id, scale_x, scale_y, rotation, color))
            
            # Tiles
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


# =============================================================================
# SPRITE FOLDER MAPPER
# =============================================================================

class SpriteFolderMapper:
    """Maps sprite names to actual folder paths in the decompiled sprites directory"""
    
    def __init__(self, sprite_base_path: str):
        self.base_path = Path(sprite_base_path)
        self.sprite_folders: Dict[str, Path] = {}
        self.missing_assets: Dict[str, int] = {}  # Track missing assets and count
        self._scan_folders()
    
    def _scan_folders(self):
        """Scan sprite directory for available sprite folders"""
        if not self.base_path.exists():
            print(f"WARNING: Sprite path does not exist: {self.base_path}")
            return
        
        for folder in self.base_path.iterdir():
            if folder.is_dir():
                name = folder.name
                self.sprite_folders[name] = folder
                self.sprite_folders[name.lower()] = folder  # Also lowercase
                # Also index without common prefixes
                for prefix in ['sp_', 'spr_', 'sprite_', 'bg_', 'bkg_', 'back_']:
                    if name.lower().startswith(prefix):
                        base_name = name[len(prefix):]
                        self.sprite_folders[base_name] = folder
                        self.sprite_folders[base_name.lower()] = folder
    
    def find_sprite_path(self, sprite_name: str) -> Optional[str]:
        """Find the first frame image path for a sprite name"""
        # Try exact match first
        if sprite_name in self.sprite_folders:
            return self._get_first_frame(self.sprite_folders[sprite_name])
        
        # Try lowercase
        sprite_lower = sprite_name.lower()
        if sprite_lower in self.sprite_folders:
            return self._get_first_frame(self.sprite_folders[sprite_lower])
        
        # Try with common prefixes
        for prefix in ['sp_', 'spr_', 'sprite_', 'back_', 'bg_', 'bkg_', '']:
            test_name = prefix + sprite_name
            if test_name in self.sprite_folders:
                return self._get_first_frame(self.sprite_folders[test_name])
            if test_name.lower() in self.sprite_folders:
                return self._get_first_frame(self.sprite_folders[test_name.lower()])
        
        # Try fuzzy matching for backgrounds (e.g., back_map2_1 -> back_map2_f1)
        fuzzy_result = self._fuzzy_match(sprite_name)
        if fuzzy_result:
            return fuzzy_result
        
        # Track missing
        self.missing_assets[sprite_name] = self.missing_assets.get(sprite_name, 0) + 1
        return None
    
    def _fuzzy_match(self, name: str) -> Optional[str]:
        """Try fuzzy matching for common naming variations"""
        name_lower = name.lower()
        
        import re
        
        # Pattern 1: back_map2_1 -> back_map2_f1 (insert 'f' before final number)
        # Only for pattern: back_mapN_M where N and M are single digits
        match = re.match(r'^back_map(\d)_(\d)$', name_lower)
        if match:
            map_num, tile_num = match.groups()
            test_name = f"back_map{map_num}_f{tile_num}"
            if test_name in self.sprite_folders:
                return self._get_first_frame(self.sprite_folders[test_name])
        
        # Pattern 2: back_mapX_Y -> sp_mapX_Y (replace back_ with sp_)
        # Be strict - only replace prefix, keep rest identical
        if name_lower.startswith('back_'):
            sp_name = 'sp_' + name_lower[5:]
            if sp_name in self.sprite_folders:
                return self._get_first_frame(self.sprite_folders[sp_name])
        
        # Pattern 3: back_map_X -> sp_map_X (for things like back_map_bridge)
        if name_lower.startswith('back_map_'):
            sp_name = 'sp_map_' + name_lower[9:]
            if sp_name in self.sprite_folders:
                return self._get_first_frame(self.sprite_folders[sp_name])
        
        # Pattern 4: back_mapN_suffix -> sp_mapN_suffix 
        # e.g., back_map5_floor_1 -> sp_map5_floor_1 or sp_map5_1
        match = re.match(r'^back_map(\d+)_(.+)$', name_lower)
        if match:
            map_num, suffix = match.groups()
            # Try direct replacement
            test_name = f"sp_map{map_num}_{suffix}"
            if test_name in self.sprite_folders:
                return self._get_first_frame(self.sprite_folders[test_name])
            # Try stripping middle part (e.g., floor_1 -> 1)
            suffix_match = re.search(r'(\d+)$', suffix)
            if suffix_match:
                final_num = suffix_match.group(1)
                test_name = f"sp_map{map_num}_{final_num}"
                if test_name in self.sprite_folders:
                    return self._get_first_frame(self.sprite_folders[test_name])
        
        return None
    
    def find_background_path(self, bg_name: str) -> Optional[str]:
        """Find the image path for a background"""
        return self.find_sprite_path(bg_name)
    
    def _get_first_frame(self, folder: Path) -> Optional[str]:
        """Get the path to the first frame (index 0) in a sprite folder"""
        # Look for files like spritename_0.png, spritename_00.png, frame_0.png, etc.
        patterns = [
            '*_0.png', '*_00.png', '*_000.png',
            '*_0.jpg', '*_00.jpg',
            'frame_0*.png', 'frame_0*.jpg',
            '*.png', '*.jpg'  # Fallback to any image
        ]
        
        for pattern in patterns:
            matches = list(folder.glob(pattern))
            if matches:
                # Sort and return the first one
                matches.sort(key=lambda p: p.name)
                return str(matches[0])
        
        return None
    
    def get_missing_report(self) -> str:
        """Generate a report of missing assets"""
        if not self.missing_assets:
            return "No missing assets."
        
        lines = ["Missing Assets Report:", "=" * 50]
        sorted_missing = sorted(self.missing_assets.items(), key=lambda x: -x[1])
        for name, count in sorted_missing:
            lines.append(f"  {name}: {count} references")
        
        lines.append("")
        lines.append("Available folders with similar names:")
        for missing_name in list(self.missing_assets.keys())[:10]:
            similar = self._find_similar_folders(missing_name)
            if similar:
                lines.append(f"  {missing_name} -> maybe: {', '.join(similar[:3])}")
        
        return "\n".join(lines)
    
    def _find_similar_folders(self, name: str) -> List[str]:
        """Find folders with similar names"""
        name_lower = name.lower()
        similar = []
        
        # Extract core parts
        parts = name_lower.replace('back_', '').replace('sp_', '').split('_')
        if parts:
            core = parts[0]
            for folder_name in self.sprite_folders.keys():
                if core in folder_name.lower() and folder_name not in similar:
                    similar.append(folder_name)
        
        return similar[:5]


# =============================================================================
# LAYER MAPPING
# =============================================================================

class LayerMapper:
    """
    Maps Game Maker depth values to the 5-layer system used in StageEditor.
    
    In Game Maker:
    - Lower depth values are drawn ON TOP (closer to player)
    - Higher depth values are drawn BEHIND (further from player)
    - Typical range: -1000 to 10000+
    
    StageEditor layers:
    - -2: Far back (deepest background)
    - -1: Behind player
    -  0: With player (same depth)
    - +1: In front of player
    - +2: Overlay (closest to camera)
    
    Z positions in 3ds Max (for visual representation):
    - Layer -2: Z = -20 (furthest back)
    - Layer -1: Z = -10
    - Layer  0: Z = 0
    - Layer +1: Z = 10
    - Layer +2: Z = 20 (closest)
    """
    
    def __init__(self, depth_ranges: Optional[Dict[str, Tuple[int, int]]] = None):
        # Default depth ranges for Parasite in City
        # These can be customized based on analyzing the game's actual depth values
        self.depth_ranges = depth_ranges or {
            'layer_2':  (5000, 100000),   # Far backgrounds (high depth)
            'layer_1':  (1000, 4999),      # Background elements
            'layer_0':  (-500, 999),       # Main gameplay layer
            'layer_m1': (-2000, -501),     # Foreground elements
            'layer_m2': (-100000, -2001),  # Overlay/effects (low depth)
        }
        
        # Track depth statistics for auto-calibration
        self.min_depth = float('inf')
        self.max_depth = float('-inf')
        self.depth_histogram: Dict[int, int] = {}
    
    def record_depth(self, depth: int):
        """Record a depth value for statistics"""
        self.min_depth = min(self.min_depth, depth)
        self.max_depth = max(self.max_depth, depth)
        
        # Bucket into ranges for histogram
        bucket = (depth // 100) * 100
        self.depth_histogram[bucket] = self.depth_histogram.get(bucket, 0) + 1
    
    def depth_to_layer(self, depth: int) -> int:
        """Convert Game Maker depth to 5-layer system"""
        if depth >= self.depth_ranges['layer_2'][0]:
            return -2  # Far back
        elif depth >= self.depth_ranges['layer_1'][0]:
            return -1  # Behind player
        elif depth >= self.depth_ranges['layer_0'][0]:
            return 0   # With player
        elif depth >= self.depth_ranges['layer_m1'][0]:
            return 1   # In front
        else:
            return 2   # Overlay
    
    def layer_to_z(self, layer: int) -> float:
        """Convert layer to Z position in 3ds Max"""
        return layer * -10.0  # Inverted because Max uses different coordinate system
    
    def get_statistics(self) -> str:
        """Return depth statistics as string"""
        if self.min_depth == float('inf'):
            return "No depth data recorded"
        
        lines = [
            f"Depth range: {self.min_depth} to {self.max_depth}",
            "Depth distribution:"
        ]
        
        # Sort buckets and show top entries
        sorted_buckets = sorted(self.depth_histogram.items())
        for bucket, count in sorted_buckets[:20]:
            lines.append(f"  {bucket:6d} - {bucket+99:6d}: {count}")
        
        if len(sorted_buckets) > 20:
            lines.append(f"  ... and {len(sorted_buckets) - 20} more ranges")
        
        return "\n".join(lines)


# =============================================================================
# MAXSCRIPT GENERATOR
# =============================================================================

class MaxScriptGenerator:
    """Generates MaxScript files to reconstruct rooms in 3ds Max"""
    
    def __init__(self, sprite_mapper: SpriteFolderMapper, layer_mapper: LayerMapper,
                 sprite_base_path: str):
        self.sprite_mapper = sprite_mapper
        self.layer_mapper = layer_mapper
        self.sprite_base_path = sprite_base_path.replace('\\', '\\\\')
    
    def generate_room_script(self, room: Room, extractor: GameExtractor) -> str:
        """Generate MaxScript to recreate a room"""
        lines = []
        
        # Header
        lines.append(f"-- Room: {room.name}")
        lines.append(f"-- Size: {room.width} x {room.height}")
        lines.append(f"-- Tiles: {len(room.tiles)}, Instances: {len(room.instances)}")
        lines.append("-- Generated by GM to MaxScript Converter")
        lines.append("")
        lines.append("gc()")
        lines.append("clearlistener()")
        lines.append("")
        lines.append("-- Sprite base path")
        lines.append(f'global SE_SpritePath = @"{self.sprite_base_path}\\\\"')
        lines.append("")
        
        # Helper function for creating textured planes
        lines.append(self._generate_helper_functions())
        lines.append("")
        
        # Create a layer for organization
        lines.append(f'-- Create room container')
        lines.append(f'roomContainer = Dummy pos:[0,0,0] name:"ROOM_{room.name}"')
        lines.append(f'roomContainer.boxsize = [{room.width/10}, {room.height/10}, 1]')
        lines.append("")
        
        # Process background definitions
        if room.bg_defs:
            lines.append("-- Background Definitions")
            for idx, bg_def in enumerate(room.bg_defs):
                if bg_def.visible and bg_def.bg_index >= 0:
                    bg = extractor.bg_map.get(bg_def.bg_index)
                    if bg:
                        lines.extend(self._generate_background(bg_def, bg, idx))
            lines.append("")
        
        # Collect and sort all visual elements by depth
        elements = []
        
        # Add tiles
        for idx, tile in enumerate(room.tiles):
            self.layer_mapper.record_depth(tile.depth)
            elements.append(('tile', idx, tile, tile.depth))
        
        # Add instances
        for idx, inst in enumerate(room.instances):
            obj = extractor.object_map.get(inst.obj_idx)
            if obj:
                self.layer_mapper.record_depth(obj.depth)
                elements.append(('instance', idx, inst, obj.depth))
        
        # Sort by depth (higher depth = further back = drawn first)
        elements.sort(key=lambda x: -x[3])
        
        # Generate code for each element
        lines.append("-- Room elements (sorted by depth)")
        
        for elem_type, idx, elem, depth in elements:
            layer = self.layer_mapper.depth_to_layer(depth)
            z_pos = self.layer_mapper.layer_to_z(layer)
            
            if elem_type == 'tile':
                bg = extractor.bg_map.get(elem.bg_index)
                if bg:
                    lines.extend(self._generate_tile(elem, bg, idx, layer, z_pos))
            else:
                obj = extractor.object_map.get(elem.obj_idx)
                if obj:
                    sprite = extractor.sprite_map.get(obj.sprite_index)
                    lines.extend(self._generate_instance(elem, obj, sprite, idx, layer, z_pos))
        
        # Parent all to room container
        lines.append("")
        lines.append("-- Parent all decor to room container")
        lines.append('for o in objects where (getUserProp o "roomElement") == "1" do (')
        lines.append('    o.parent = roomContainer')
        lines.append(')')
        lines.append("")
        lines.append("-- Zoom extents")
        lines.append("max zoomext sel")
        lines.append("")
        lines.append(f'format "Room {room.name} loaded: % tiles, % instances\\n" {len(room.tiles)} {len(room.instances)}')
        
        return "\n".join(lines)
    
    def _generate_helper_functions(self) -> str:
        """Generate helper functions for the MaxScript"""
        return '''
-- Helper: Create textured plane with alpha
-- Position is the CENTER of the plane (3ds Max pivot is at center)
-- If width/height are 0, read from bitmap; otherwise use specified values
fn createDecorPlane filePath pos:[0,0,0] width:0 height:0 scaleX:1.0 scaleY:1.0 = (
    if not (doesFileExist filePath) do (
        format "Missing sprite: %\\n" filePath
        return undefined
    )
    
    local map = Bitmaptexture fileName:filePath
    local w = width
    local h = height
    
    -- Only read from bitmap if dimensions not specified (0)
    if w == 0 or h == 0 do (
        try ( 
            w = map.bitmap.width
            h = map.bitmap.height 
        ) catch (
            w = 100
            h = 100
        )
    )
    
    local p = Plane width:w length:h lengthsegs:1 widthsegs:1 pos:pos
    
    -- Apply material with alpha
    p.material = StandardMaterial name:(getFilenameFile filePath)
    p.material.diffuseMap = map
    p.material.diffuseMap.alphaSource = 2
    
    local map2 = Bitmaptexture fileName:filePath
    p.material.opacityMap = map2
    p.material.opacityMap.monoOutput = 1
    p.material.opacityMap.preMultAlpha = off
    p.material.opacityMap.rgbOutput = 1
    p.material.opacityMap.alphaSource = 0
    p.material.selfIllumAmount = 100
    p.material.twoSided = true
    
    try ( close map.bitmap ) catch ()
    showTextureMap p.material true
    
    -- Apply scale (negative for flip)
    if scaleX != 1.0 or scaleY != 1.0 do (
        p.scale = [scaleX, scaleY, 1.0]
    )
    
    p
)

-- Helper: Find sprite file in folder
fn findSpriteFile spriteName = (
    local basePath = SE_SpritePath + spriteName + "\\\\"
    if doesFileExist basePath then (
        local files = getFiles (basePath + "*.png")
        if files.count > 0 then (
            sort files
            return files[1]
        )
        files = getFiles (basePath + "*.jpg")
        if files.count > 0 then (
            sort files
            return files[1]
        )
    )
    -- Try without folder (single image)
    local direct = SE_SpritePath + spriteName + ".png"
    if doesFileExist direct do return direct
    direct = SE_SpritePath + spriteName + ".jpg"
    if doesFileExist direct do return direct
    undefined
)
'''
    
    def _generate_tile(self, tile: RoomTile, bg: Background, idx: int, 
                       layer: int, z_pos: float) -> List[str]:
        """Generate MaxScript code for a tile"""
        lines = []
        
        # Game Maker tile position = TOP-LEFT corner
        # 3ds Max Plane pivot = CENTER
        # So we add half-dimensions to convert top-left to center
        # Y is flipped: GM Y+ is down, Max Y+ is up
        x = tile.x + tile.width / 2.0
        y = -(tile.y + tile.height / 2.0)
        
        # Handle flipping (negative scale)
        scale_x = tile.scale_x if abs(tile.scale_x) <= 10 else 1.0
        scale_y = tile.scale_y if abs(tile.scale_y) <= 10 else 1.0
        
        # Find sprite path and get the RESOLVED folder name
        sprite_path = self.sprite_mapper.find_sprite_path(bg.name)
        
        if sprite_path:
            # Extract actual folder name from resolved path
            resolved_folder = Path(sprite_path).parent.name
            
            lines.append(f"-- Tile {idx}: {bg.name} -> {resolved_folder} at ({tile.x}, {tile.y}) size:{tile.width}x{tile.height} depth={tile.depth} layer={layer}")
            lines.append(f'tileSprite = findSpriteFile "{resolved_folder}"')
            lines.append(f'if tileSprite != undefined then (')
            lines.append(f'    tileObj = createDecorPlane tileSprite pos:[{x}, {y}, {z_pos}] width:{tile.width} height:{tile.height} scaleX:{scale_x:.2f} scaleY:{scale_y:.2f}')
            lines.append(f'    if tileObj != undefined do (')
            lines.append(f'        tileObj.name = "TILE_{idx}_{resolved_folder}"')
            lines.append(f'        tileObj.wirecolor = color 180 130 255')
            lines.append(f'        setUserProp tileObj "entityType" "decor"')
            lines.append(f'        setUserProp tileObj "layer" "{layer}"')
            lines.append(f'        setUserProp tileObj "gmDepth" "{tile.depth}"')
            lines.append(f'        setUserProp tileObj "gmBackground" "{bg.name}"')
            lines.append(f'        setUserProp tileObj "roomElement" "1"')
            lines.append(f'        setUserProp tileObj "flipX" "{1 if scale_x < 0 else 0}"')
            lines.append(f'        setUserProp tileObj "flipY" "{1 if scale_y < 0 else 0}"')
            lines.append(f'    )')
            lines.append(f')')
            lines.append("")
        else:
            lines.append(f"-- MISSING Tile {idx}: {bg.name} (sprite not found)")
            lines.append("")
        
        return lines
    
    def _generate_instance(self, inst: RoomInst, obj: GameObject, 
                           sprite: Optional[Sprite], idx: int, 
                           layer: int, z_pos: float) -> List[str]:
        """Generate MaxScript code for an instance"""
        lines = []
        
        scale_x = inst.scale_x if abs(inst.scale_x) <= 10 else 1.0
        scale_y = inst.scale_y if abs(inst.scale_y) <= 10 else 1.0
        
        sprite_name = sprite.name if sprite else None
        
        # Calculate position accounting for sprite origin
        # In GM: instance position is where sprite ORIGIN is placed
        # In Max: plane position is the CENTER
        # So we need to offset from origin to center
        if sprite:
            # Offset from sprite origin to sprite center
            offset_x = sprite.width / 2 - sprite.origin_x
            offset_y = sprite.height / 2 - sprite.origin_y
            x = inst.x + offset_x
            y = -(inst.y + offset_y)  # Flip Y for Max
        else:
            x = inst.x
            y = -inst.y
        
        # Determine entity type based on object name
        entity_type = self._classify_object(obj.name)
        
        if sprite_name:
            sprite_path = self.sprite_mapper.find_sprite_path(sprite_name)
            
            # Get resolved folder name
            resolved_folder = Path(sprite_path).parent.name if sprite_path else sprite_name
            
            lines.append(f"-- Instance {idx}: {obj.name} ({sprite_name} -> {resolved_folder}) at ({inst.x}, {inst.y}) depth={obj.depth}")
            
            if sprite_path or entity_type != "decor":
                lines.append(f'instSprite = findSpriteFile "{resolved_folder}"')
                lines.append(f'if instSprite != undefined then (')
                
                # Get sprite dimensions - use local inside the if block
                if sprite:
                    lines.append(f'    instObj = createDecorPlane instSprite pos:[{x}, {y}, {z_pos}] width:{sprite.width} height:{sprite.height} scaleX:{scale_x:.2f} scaleY:{scale_y:.2f}')
                else:
                    lines.append(f'    instObj = createDecorPlane instSprite pos:[{x}, {y}, {z_pos}] scaleX:{scale_x:.2f} scaleY:{scale_y:.2f}')
                
                lines.append(f'    if instObj != undefined do (')
                lines.append(f'        instObj.name = "INST_{idx}_{obj.name}"')
                lines.append(f'        setUserProp instObj "entityType" "{entity_type}"')
                lines.append(f'        setUserProp instObj "objectName" "{obj.name}"')
                lines.append(f'        setUserProp instObj "layer" "{layer}"')
                lines.append(f'        setUserProp instObj "gmDepth" "{obj.depth}"')
                lines.append(f'        setUserProp instObj "roomElement" "1"')
                
                # Set wirecolor based on type
                color = self._get_entity_color(entity_type)
                lines.append(f'        instObj.wirecolor = color {color[0]} {color[1]} {color[2]}')
                
                # Store flip info
                if scale_x < 0:
                    lines.append(f'        setUserProp instObj "flipX" "1"')
                if scale_y < 0:
                    lines.append(f'        setUserProp instObj "flipY" "1"')
                
                lines.append(f'    )')
                lines.append(f') else (')
                lines.append(f'    -- Create placeholder (no local needed at script level)')
                lines.append(f'    ph = Dummy pos:[{inst.x}, {-inst.y}, {z_pos}] name:"MISSING_{obj.name}"')
                lines.append(f'    ph.boxsize = [50, 50, 10]')
                lines.append(f'    setUserProp ph "entityType" "{entity_type}"')
                lines.append(f'    setUserProp ph "objectName" "{obj.name}"')
                lines.append(f'    setUserProp ph "roomElement" "1"')
                lines.append(f')')
                lines.append("")
            else:
                lines.append(f"-- MISSING Instance {idx}: {obj.name} ({sprite_name})")
                lines.append("")
        else:
            # No sprite - create Dummy at instance position (no local at top level)
            lines.append(f"-- Instance {idx}: {obj.name} (no sprite) at ({inst.x}, {inst.y})")
            lines.append(f'instObj = Dummy pos:[{inst.x}, {-inst.y}, {z_pos}] name:"INST_{idx}_{obj.name}"')
            lines.append(f'instObj.boxsize = [30, 30, 10]')
            lines.append(f'setUserProp instObj "entityType" "{entity_type}"')
            lines.append(f'setUserProp instObj "objectName" "{obj.name}"')
            lines.append(f'setUserProp instObj "roomElement" "1"')
            color = self._get_entity_color(entity_type)
            lines.append(f'instObj.wirecolor = color {color[0]} {color[1]} {color[2]}')
            lines.append("")
        
        return lines
    
    def _generate_background(self, bg_def: RoomBgDef, bg: Background, 
                             idx: int) -> List[str]:
        """Generate MaxScript code for a room background"""
        lines = []
        
        layer = 2 if bg_def.foreground else -2
        z_pos = self.layer_mapper.layer_to_z(layer)
        
        # Find resolved folder name
        sprite_path = self.sprite_mapper.find_sprite_path(bg.name)
        resolved_folder = Path(sprite_path).parent.name if sprite_path else bg.name
        
        # Background position in GM is top-left, flip Y for Max
        # For backgrounds, we don't know dimensions until we load the image,
        # so position will be at origin point (will read size from bitmap)
        lines.append(f"-- Background {idx}: {bg.name} -> {resolved_folder} at ({bg_def.x}, {bg_def.y})")
        lines.append(f'bgSprite = findSpriteFile "{resolved_folder}"')
        lines.append(f'if bgSprite != undefined then (')
        lines.append(f'    bgObj = createDecorPlane bgSprite pos:[{bg_def.x}, {-bg_def.y}, {z_pos}]')
        lines.append(f'    if bgObj != undefined do (')
        lines.append(f'        bgObj.name = "BG_{idx}_{resolved_folder}"')
        lines.append(f'        bgObj.wirecolor = color 100 100 100')
        lines.append(f'        setUserProp bgObj "entityType" "background"')
        lines.append(f'        setUserProp bgObj "layer" "{layer}"')
        lines.append(f'        setUserProp bgObj "gmBackground" "{bg.name}"')
        lines.append(f'        setUserProp bgObj "roomElement" "1"')
        lines.append(f'        setUserProp bgObj "tileH" "{1 if bg_def.tile_h else 0}"')
        lines.append(f'        setUserProp bgObj "tileV" "{1 if bg_def.tile_v else 0}"')
        lines.append(f'    )')
        lines.append(f')')
        lines.append("")
        
        return lines
    
    def _classify_object(self, name: str) -> str:
        """Classify an object into entity types based on its name"""
        name_lower = name.lower()
        
        # Player
        if 'player' in name_lower or name_lower.startswith('obj_player'):
            return 'player'
        
        # Enemies
        if 'enemy' in name_lower or 'monster' in name_lower or 'parasite' in name_lower:
            return 'enemy'
        
        # Collision / Platforms
        if 'col_' in name_lower or 'collision' in name_lower:
            if 'wall' in name_lower:
                return 'wall'
            return 'platform'
        
        if 'platform' in name_lower or 'floor' in name_lower or 'ground' in name_lower:
            return 'platform'
        
        if 'wall' in name_lower:
            return 'wall'
        
        # Interactive elements
        if 'door' in name_lower:
            return 'door'
        if 'switch' in name_lower or 'lever' in name_lower or 'button' in name_lower:
            return 'switch'
        if 'item' in name_lower or 'pickup' in name_lower or 'health' in name_lower or 'ammo' in name_lower:
            return 'item'
        if 'crate' in name_lower or 'box' in name_lower:
            return 'crate'
        if 'checkpoint' in name_lower or 'save' in name_lower:
            return 'checkpoint'
        
        # Hazards
        if 'spike' in name_lower or 'hazard' in name_lower or 'trap' in name_lower or 'hurt' in name_lower:
            return 'hazard'
        
        # Zones
        if 'trigger' in name_lower or 'zone' in name_lower:
            return 'trigger'
        if 'death' in name_lower or 'kill' in name_lower:
            return 'area_death'
        if 'exit' in name_lower or 'goal' in name_lower:
            return 'area_exit'
        
        # Effects
        if 'emitter' in name_lower or 'particle' in name_lower or 'effect' in name_lower:
            return 'emitter'
        if 'light' in name_lower:
            return 'light'
        
        # Default to decor
        return 'decor'
    
    def _get_entity_color(self, entity_type: str) -> Tuple[int, int, int]:
        """Get wirecolor for entity type"""
        colors = {
            'platform':    (56, 86, 164),
            'wall':        (217, 227, 174),
            'grab':        (255, 255, 0),
            'player':      (0, 255, 0),
            'enemy':       (255, 100, 100),
            'item':        (0, 255, 128),
            'crate':       (139, 90, 43),
            'door':        (100, 80, 60),
            'switch':      (255, 200, 0),
            'emitter':     (14, 255, 2),
            'light':       (255, 200, 100),
            'camera':      (100, 150, 255),
            'checkpoint':  (0, 200, 255),
            'area_death':  (255, 0, 0),
            'area_exit':   (0, 255, 0),
            'hazard':      (255, 50, 0),
            'trigger':     (255, 255, 100),
            'background':  (100, 100, 100),
            'decor':       (180, 130, 255),
        }
        return colors.get(entity_type, (180, 130, 255))


# =============================================================================
# MAIN CONVERTER
# =============================================================================

class RoomConverter:
    """Main converter class"""
    
    def __init__(self, data_win_path: str, sprite_path: str, output_dir: str):
        self.data_win_path = data_win_path
        self.sprite_path = sprite_path
        self.output_dir = Path(output_dir)
        
        self.dw: Optional[DataWin] = None
        self.extractor: Optional[GameExtractor] = None
        self.sprite_mapper: Optional[SpriteFolderMapper] = None
        self.layer_mapper: Optional[LayerMapper] = None
        self.generator: Optional[MaxScriptGenerator] = None
    
    def load(self, verbose=True):
        """Load and parse data.win"""
        if verbose:
            print(f"Loading {self.data_win_path}...")
        
        self.dw = DataWin(self.data_win_path)
        self.extractor = GameExtractor(self.dw)
        self.extractor.extract_all(verbose=verbose)
        
        if verbose:
            print(f"Scanning sprite folders in {self.sprite_path}...")
        self.sprite_mapper = SpriteFolderMapper(self.sprite_path)
        if verbose:
            print(f"  Found {len(self.sprite_mapper.sprite_folders)} sprite folders")
        
        self.layer_mapper = LayerMapper()
        self.generator = MaxScriptGenerator(
            self.sprite_mapper, self.layer_mapper, self.sprite_path)
    
    def list_rooms(self) -> List[str]:
        """List all room names"""
        if not self.extractor:
            return []
        return [r.name for r in self.extractor.rooms]
    
    def get_room_info(self, room_name: str) -> Optional[str]:
        """Get detailed info about a room"""
        if not self.extractor:
            return None
        
        room = next((r for r in self.extractor.rooms if r.name == room_name), None)
        if not room:
            return None
        
        lines = [
            f"Room: {room.name}",
            f"Index: {room.index}",
            f"Size: {room.width} x {room.height}",
            f"Speed: {room.speed}",
            f"Background color: #{room.color:08X}",
            f"Background defs: {len(room.bg_defs)}",
            f"Instances: {len(room.instances)}",
            f"Tiles: {len(room.tiles)}",
        ]
        
        # Depth analysis
        if room.tiles:
            depths = sorted(set(t.depth for t in room.tiles))
            lines.append(f"Tile depths: {len(depths)} unique values")
            if len(depths) <= 10:
                lines.append(f"  Values: {depths}")
            else:
                lines.append(f"  Range: {min(depths)} to {max(depths)}")
        
        return "\n".join(lines)
    
    def convert_room(self, room_name: str, verbose=True) -> Optional[str]:
        """Convert a single room to MaxScript"""
        if not self.extractor or not self.generator:
            return None
        
        room = next((r for r in self.extractor.rooms if r.name == room_name), None)
        if not room:
            if verbose:
                print(f"Room not found: {room_name}")
            return None
        
        if verbose:
            print(f"Converting room: {room.name}")
            print(f"  Size: {room.width}x{room.height}")
            print(f"  Tiles: {len(room.tiles)}")
            print(f"  Instances: {len(room.instances)}")
        
        script = self.generator.generate_room_script(room, self.extractor)
        
        # Write to file
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{room.name}.ms"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(script)
        
        if verbose:
            print(f"  Saved to: {output_path}")
            print(f"  Depth stats: {self.layer_mapper.min_depth} to {self.layer_mapper.max_depth}")
        
        return str(output_path)
    
    def convert_all_rooms(self, verbose=True) -> List[str]:
        """Convert all rooms to MaxScript"""
        if not self.extractor:
            return []
        
        output_paths = []
        for room in self.extractor.rooms:
            path = self.convert_room(room.name, verbose=verbose)
            if path:
                output_paths.append(path)
        
        # Print missing assets report
        if verbose and self.sprite_mapper.missing_assets:
            print("\n" + self.sprite_mapper.get_missing_report())
        
        return output_paths
    
    def generate_asset_report(self) -> str:
        """Generate a detailed report of all assets and their mapping status"""
        if not self.extractor:
            return "No data loaded"
        
        lines = []
        lines.append("=" * 60)
        lines.append("ASSET MAPPING REPORT")
        lines.append("=" * 60)
        
        # Backgrounds
        lines.append("\n--- BACKGROUNDS (used by tiles) ---")
        for bg in self.extractor.backgrounds:
            sprite_path = self.sprite_mapper.find_sprite_path(bg.name)
            status = "✓ FOUND" if sprite_path else "✗ MISSING"
            mapped_to = Path(sprite_path).parent.name if sprite_path else ""
            lines.append(f"  [{bg.index:3d}] {bg.name:30s} {status} {mapped_to}")
        
        # Sprites used by objects
        lines.append("\n--- SPRITES (used by objects) ---")
        seen_sprites = set()
        for obj in self.extractor.objects:
            if obj.sprite_index >= 0 and obj.sprite_index not in seen_sprites:
                seen_sprites.add(obj.sprite_index)
                spr = self.extractor.sprite_map.get(obj.sprite_index)
                if spr:
                    sprite_path = self.sprite_mapper.find_sprite_path(spr.name)
                    status = "✓ FOUND" if sprite_path else "✗ MISSING"
                    lines.append(f"  [{spr.index:3d}] {spr.name:30s} {status}")
        
        # Summary
        lines.append("\n--- SUMMARY ---")
        bg_found = sum(1 for bg in self.extractor.backgrounds 
                      if self.sprite_mapper.find_sprite_path(bg.name))
        bg_total = len(self.extractor.backgrounds)
        lines.append(f"  Backgrounds: {bg_found}/{bg_total} found")
        
        spr_found = sum(1 for spr in self.extractor.sprites 
                       if self.sprite_mapper.find_sprite_path(spr.name))
        spr_total = len(self.extractor.sprites)
        lines.append(f"  Sprites: {spr_found}/{spr_total} found")
        
        return "\n".join(lines)
    
    def generate_mapping_file(self, output_path: Optional[str] = None) -> str:
        """Generate an editable mapping file for manual name corrections"""
        if not self.extractor:
            return ""
        
        if not output_path:
            output_path = str(self.output_dir / "asset_mapping.txt")
        
        lines = []
        lines.append("# Asset Name Mapping File")
        lines.append("# Format: original_name = mapped_folder_name")
        lines.append("# Lines starting with # are comments")
        lines.append("# Edit the right side to map to your extracted folder names")
        lines.append("")
        lines.append("# === BACKGROUNDS ===")
        
        for bg in self.extractor.backgrounds:
            found_path = self.sprite_mapper.find_sprite_path(bg.name)
            if found_path:
                mapped = Path(found_path).parent.name
                lines.append(f"{bg.name} = {mapped}")
            else:
                # Show suggestion if available
                similar = self.sprite_mapper._find_similar_folders(bg.name)
                suggestion = similar[0] if similar else "???"
                lines.append(f"{bg.name} = {suggestion}  # NEEDS MAPPING")
        
        lines.append("")
        lines.append("# === SPRITES ===")
        
        for spr in self.extractor.sprites:
            found_path = self.sprite_mapper.find_sprite_path(spr.name)
            if found_path:
                mapped = Path(found_path).parent.name
                lines.append(f"{spr.name} = {mapped}")
            else:
                similar = self.sprite_mapper._find_similar_folders(spr.name)
                suggestion = similar[0] if similar else "???"
                lines.append(f"# {spr.name} = {suggestion}  # NEEDS MAPPING")
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        
        return output_path
    
    def load_mapping_file(self, mapping_path: str):
        """Load custom name mappings from a file"""
        if not os.path.exists(mapping_path):
            print(f"Mapping file not found: {mapping_path}")
            return
        
        with open(mapping_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    parts = line.split('=', 1)
                    original = parts[0].strip()
                    mapped = parts[1].split('#')[0].strip()  # Remove comments
                    if mapped and mapped != '???':
                        # Add to sprite mapper
                        folder_path = self.sprite_mapper.base_path / mapped
                        if folder_path.exists():
                            self.sprite_mapper.sprite_folders[original] = folder_path
                            self.sprite_mapper.sprite_folders[original.lower()] = folder_path
                            print(f"  Mapped: {original} -> {mapped}")
                        else:
                            print(f"  Warning: folder not found for mapping {original} -> {mapped}")
    
    def export_room_json(self, room_name: str) -> Optional[str]:
        """Export room data as JSON for debugging"""
        if not self.extractor:
            return None
        
        room = next((r for r in self.extractor.rooms if r.name == room_name), None)
        if not room:
            return None
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{room.name}.json"
        
        # Convert to dict
        room_dict = {
            'name': room.name,
            'index': room.index,
            'width': room.width,
            'height': room.height,
            'speed': room.speed,
            'color': room.color,
            'bg_defs': [
                {
                    'visible': bg.visible,
                    'foreground': bg.foreground,
                    'bg_index': bg.bg_index,
                    'bg_name': self.extractor.bg_map.get(bg.bg_index, Background(-1, "unknown")).name,
                    'x': bg.x, 'y': bg.y,
                    'tile_h': bg.tile_h, 'tile_v': bg.tile_v,
                    'stretch': bg.stretch
                }
                for bg in room.bg_defs
            ],
            'instances': [
                {
                    'x': inst.x, 'y': inst.y,
                    'obj_idx': inst.obj_idx,
                    'obj_name': self.extractor.object_map.get(inst.obj_idx, GameObject(-1, "unknown", -1, False, False, 0, -1, -1)).name,
                    'inst_id': inst.inst_id,
                    'scale_x': inst.scale_x, 'scale_y': inst.scale_y
                }
                for inst in room.instances
            ],
            'tiles': [
                {
                    'x': t.x, 'y': t.y,
                    'bg_index': t.bg_index,
                    'bg_name': self.extractor.bg_map.get(t.bg_index, Background(-1, "unknown")).name,
                    'src_x': t.src_x, 'src_y': t.src_y,
                    'width': t.width, 'height': t.height,
                    'depth': t.depth,
                    'scale_x': t.scale_x, 'scale_y': t.scale_y
                }
                for t in room.tiles
            ]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(room_dict, f, indent=2)
        
        return str(output_path)


# =============================================================================
# CLI INTERFACE
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert Game Maker rooms to MaxScript',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # List all rooms
  python gm_to_maxscript.py --list
  
  # Convert a specific room
  python gm_to_maxscript.py --room room_stage1
  
  # Convert all rooms
  python gm_to_maxscript.py --all
  
  # Export room data as JSON
  python gm_to_maxscript.py --room room_stage1 --json
  
  # Use custom paths
  python gm_to_maxscript.py --data-win "C:/Game/data.win" --sprites "C:/Game/sprites" --output "C:/MaxScripts"
''')
    
    parser.add_argument('--data-win', '-d', default=DEFAULT_DATA_WIN,
                        help='Path to data.win file')
    parser.add_argument('--sprites', '-s', default=DEFAULT_SPRITE_PATH,
                        help='Path to decompiled sprites folder')
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT_DIR,
                        help='Output directory for MaxScript files')
    
    parser.add_argument('--list', '-l', action='store_true',
                        help='List all rooms')
    parser.add_argument('--room', '-r', type=str,
                        help='Convert specific room by name')
    parser.add_argument('--all', '-a', action='store_true',
                        help='Convert all rooms')
    parser.add_argument('--json', '-j', action='store_true',
                        help='Also export room data as JSON')
    parser.add_argument('--info', '-i', type=str,
                        help='Show detailed info for a room')
    parser.add_argument('--report', action='store_true',
                        help='Generate asset mapping report (shows what is found/missing)')
    parser.add_argument('--gen-mapping', action='store_true',
                        help='Generate an editable mapping file for manual corrections')
    parser.add_argument('--use-mapping', type=str, metavar='FILE',
                        help='Load custom name mappings from a file')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress verbose output')
    
    args = parser.parse_args()
    
    # Validate paths
    if not os.path.exists(args.data_win):
        print(f"ERROR: data.win not found: {args.data_win}")
        print("Please specify the correct path with --data-win")
        return 1
    
    if not os.path.exists(args.sprites):
        print(f"WARNING: Sprite path not found: {args.sprites}")
        print("Sprites will not be resolved. Use --sprites to specify correct path.")
    
    # Initialize converter
    verbose = not args.quiet
    converter = RoomConverter(args.data_win, args.sprites, args.output)
    
    try:
        converter.load(verbose=verbose)
    except Exception as e:
        print(f"ERROR loading data.win: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Load custom mapping if specified
    if args.use_mapping:
        print(f"Loading custom mappings from: {args.use_mapping}")
        converter.load_mapping_file(args.use_mapping)
    
    # Handle commands
    if args.report:
        print(converter.generate_asset_report())
        return 0
    
    if args.gen_mapping:
        mapping_path = converter.generate_mapping_file()
        print(f"Generated mapping file: {mapping_path}")
        print("Edit this file to fix missing assets, then use --use-mapping to apply.")
        return 0
    
    if args.list:
        print("\nAvailable rooms:")
        for name in converter.list_rooms():
            print(f"  {name}")
        return 0
    
    if args.info:
        info = converter.get_room_info(args.info)
        if info:
            print(f"\n{info}")
        else:
            print(f"Room not found: {args.info}")
        return 0
    
    if args.room:
        path = converter.convert_room(args.room, verbose=verbose)
        if path:
            print(f"\nGenerated: {path}")
            if args.json:
                json_path = converter.export_room_json(args.room)
                if json_path:
                    print(f"JSON: {json_path}")
        return 0 if path else 1
    
    if args.all:
        paths = converter.convert_all_rooms(verbose=verbose)
        print(f"\nGenerated {len(paths)} MaxScript files in {args.output}")
        return 0
    
    # Default: show help
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
