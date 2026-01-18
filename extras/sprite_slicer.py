#!/usr/bin/env python3
"""
Game Maker Studio Sprite Atlas Slicer
Extracts individual sprite frames from texture atlases using data.win sprite definitions

Usage:
    python sprite_slicer.py data.win --textures ./textures -o ./sprites
"""

import struct
import os
import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)


# =============================================================================
# DATA.WIN READER
# =============================================================================

class ChunkID:
    FORM = 0x4D524F46
    STRG = 0x47525453
    SPRT = 0x54525053
    TPAG = 0x47415054
    TXTR = 0x52545854
    
    @staticmethod
    def name(cid: int) -> str:
        return struct.pack('<I', cid).decode('ascii', errors='replace')


@dataclass 
class Chunk:
    name: str
    offset: int
    size: int
    data_start: int


class DataWin:
    def __init__(self, path: str):
        with open(path, 'rb') as f:
            self.data = f.read()
        self.chunks: Dict[int, Chunk] = {}
        self._parse_chunks()
        
    def _parse_chunks(self):
        if self.u32(0) != ChunkID.FORM:
            raise ValueError("Not a valid data.win")
        pos = 8
        while pos < len(self.data) - 8:
            cid = self.u32(pos)
            size = self.u32(pos + 4)
            self.chunks[cid] = Chunk(ChunkID.name(cid), pos, size, pos + 8)
            pos += 8 + size
    
    def u8(self, off: int) -> int: return self.data[off]
    def u16(self, off: int) -> int: return struct.unpack_from('<H', self.data, off)[0]
    def i16(self, off: int) -> int: return struct.unpack_from('<h', self.data, off)[0]
    def u32(self, off: int) -> int: return struct.unpack_from('<I', self.data, off)[0]
    def i32(self, off: int) -> int: return struct.unpack_from('<i', self.data, off)[0]
    
    def gm_string(self, off: int) -> str:
        if off == 0 or off >= len(self.data) - 4:
            return ""
        length = self.u32(off)
        if length == 0 or length > 1000000 or off + 4 + length > len(self.data):
            return ""
        return self.data[off + 4:off + 4 + length].decode('utf-8', errors='replace')


# =============================================================================
# SPRITE DATA STRUCTURES
# =============================================================================

@dataclass
class TexturePageEntry:
    """TPAG entry - defines a region on a texture atlas"""
    src_x: int          # X position on texture atlas
    src_y: int          # Y position on texture atlas  
    src_width: int      # Width on atlas
    src_height: int     # Height on atlas
    target_x: int       # X offset when rendering (for trimmed sprites)
    target_y: int       # Y offset when rendering
    target_width: int   # Full width of sprite frame
    target_height: int  # Full height of sprite frame
    bounding_width: int # Bounding box width
    bounding_height: int # Bounding box height
    texture_id: int     # Which texture atlas this is on


@dataclass
class SpriteFrame:
    """A single frame of a sprite animation"""
    tpage: TexturePageEntry
    frame_index: int


@dataclass
class Sprite:
    """A sprite with all its animation frames"""
    name: str
    index: int
    width: int
    height: int
    origin_x: int
    origin_y: int
    frames: List[SpriteFrame]


# =============================================================================
# EXTRACTOR
# =============================================================================

class SpriteExtractor:
    def __init__(self, dw: DataWin):
        self.dw = dw
        self.sprites: List[Sprite] = []
        self.tpage_entries: List[TexturePageEntry] = []
        
    def extract_tpag(self):
        """Extract TPAG chunk - texture page entries"""
        if ChunkID.TPAG not in self.dw.chunks:
            print("WARNING: No TPAG chunk found")
            return
            
        chunk = self.dw.chunks[ChunkID.TPAG]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  TPAG: {count} texture page entries")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if ptr:
                # TPAG entry structure (22 bytes):
                # +0x00: src_x (u16)
                # +0x02: src_y (u16)
                # +0x04: src_width (u16)
                # +0x06: src_height (u16)
                # +0x08: target_x (u16)
                # +0x0A: target_y (u16)
                # +0x0C: target_width (u16)
                # +0x0E: target_height (u16)
                # +0x10: bounding_width (u16)
                # +0x12: bounding_height (u16)
                # +0x14: texture_id (u16)
                
                entry = TexturePageEntry(
                    src_x=self.dw.u16(ptr + 0),
                    src_y=self.dw.u16(ptr + 2),
                    src_width=self.dw.u16(ptr + 4),
                    src_height=self.dw.u16(ptr + 6),
                    target_x=self.dw.u16(ptr + 8),
                    target_y=self.dw.u16(ptr + 10),
                    target_width=self.dw.u16(ptr + 12),
                    target_height=self.dw.u16(ptr + 14),
                    bounding_width=self.dw.u16(ptr + 16),
                    bounding_height=self.dw.u16(ptr + 18),
                    texture_id=self.dw.u16(ptr + 20)
                )
                self.tpage_entries.append(entry)
    
    def extract_sprites(self):
        """Extract SPRT chunk"""
        if ChunkID.SPRT not in self.dw.chunks:
            print("WARNING: No SPRT chunk found")
            return
            
        chunk = self.dw.chunks[ChunkID.SPRT]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  SPRT: {count} sprites")
        
        # Debug: show first sprite structure to understand layout
        if count > 0:
            first_ptr = self.dw.u32(off + 4)
            print(f"\n  === DEBUG: First sprite entry at 0x{first_ptr:08X} ===")
            for field_off in range(0, 0x50, 4):
                val = self.dw.u32(first_ptr + field_off)
                print(f"    +0x{field_off:02X}: 0x{val:08X} ({val})")
            # Try to read name from offset 0
            name_ptr = self.dw.u32(first_ptr)
            if name_ptr and name_ptr < len(self.dw.data) - 4:
                print(f"  Trying to read string at 0x{name_ptr:08X}:")
                raw = self.dw.data[name_ptr:name_ptr+40]
                print(f"    Raw bytes: {raw[:20].hex()} ...")
                print(f"    As text: {repr(raw)}")
            print(f"  === END DEBUG ===\n")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if not ptr:
                continue
            
            # Validate pointer is within file
            if ptr >= len(self.dw.data) - 100:
                continue
                
            # SPRT entry structure (from decompiled code):
            # +0x00: name_ptr (u32) - pointer to string
            # +0x04: width (u32)
            # +0x08: height (u32)  
            # +0x0C: bbox_left (i32)
            # +0x10: bbox_right (i32)
            # +0x14: bbox_bottom (i32)
            # +0x18: bbox_top (i32)
            # +0x1C: transparent (u32)
            # +0x20: smooth (u32)
            # +0x24: preload (u32)
            # +0x28: bbox_mode (u32)
            # +0x2C: sep_masks (u32)
            # +0x30: origin_x (i32)
            # +0x34: origin_y (i32)
            # +0x38: frame_count (u32) - number of texture page entries
            # +0x3C+: frame pointers (TPAG entry pointers)
            
            name_ptr = self.dw.u32(ptr)
            name = ""
            if name_ptr and name_ptr < len(self.dw.data) - 4:
                # Try as GM string first (length-prefixed)
                name = self.dw.gm_string(name_ptr)
                
                # If that fails, try as null-terminated C string
                if not name:
                    end = self.dw.data.find(b'\x00', name_ptr, name_ptr + 200)
                    if end > name_ptr:
                        try:
                            name = self.dw.data[name_ptr:end].decode('utf-8', errors='replace')
                        except:
                            pass
            
            if not name:
                name = f"sprite_{i}"
            
            width = self.dw.u32(ptr + 4)
            height = self.dw.u32(ptr + 8)
            origin_x = self.dw.i32(ptr + 0x30)  # 48
            origin_y = self.dw.i32(ptr + 0x34)  # 52
            
            # Frame count at offset 0x38 (56)
            frame_count = self.dw.u32(ptr + 0x38)
            frame_ptr_start = ptr + 0x3C  # 60
            
            # Sanity checks
            if frame_count > 10000:
                print(f"  WARNING: sprite_{i} ({name}) has suspicious frame_count={frame_count}, skipping")
                continue
            
            frames = []
            for j in range(frame_count):
                tpage_ptr_off = frame_ptr_start + j * 4
                if tpage_ptr_off + 4 > len(self.dw.data):
                    break
                    
                tpage_ptr = self.dw.u32(tpage_ptr_off)
                
                # Validate TPAG pointer
                if tpage_ptr == 0 or tpage_ptr >= len(self.dw.data) - 22:
                    continue
                
                # Read TPAG entry (22 bytes)
                tpage = TexturePageEntry(
                    src_x=self.dw.u16(tpage_ptr + 0),
                    src_y=self.dw.u16(tpage_ptr + 2),
                    src_width=self.dw.u16(tpage_ptr + 4),
                    src_height=self.dw.u16(tpage_ptr + 6),
                    target_x=self.dw.u16(tpage_ptr + 8),
                    target_y=self.dw.u16(tpage_ptr + 10),
                    target_width=self.dw.u16(tpage_ptr + 12),
                    target_height=self.dw.u16(tpage_ptr + 14),
                    bounding_width=self.dw.u16(tpage_ptr + 16),
                    bounding_height=self.dw.u16(tpage_ptr + 18),
                    texture_id=self.dw.u16(tpage_ptr + 20)
                )
                
                # Sanity check texture_id
                if tpage.texture_id > 100:
                    continue
                    
                frames.append(SpriteFrame(tpage=tpage, frame_index=j))
            
            self.sprites.append(Sprite(
                name=name,
                index=i,
                width=width,
                height=height,
                origin_x=origin_x,
                origin_y=origin_y,
                frames=frames
            ))
    
    def extract_all(self):
        print("Extracting texture page entries...")
        self.extract_tpag()
        print("Extracting sprites...")
        self.extract_sprites()
        
        # Stats
        total_frames = sum(len(s.frames) for s in self.sprites)
        sprites_with_frames = sum(1 for s in self.sprites if s.frames)
        print(f"  Total: {len(self.sprites)} sprites, {total_frames} frames")
        print(f"  Sprites with frames: {sprites_with_frames}")


def slice_sprites(extractor: SpriteExtractor, textures_dir: Path, output_dir: Path, 
                  include_empty: bool = False):
    """Slice texture atlases into individual sprite frames"""
    
    # Load all texture atlases
    textures: Dict[int, Image.Image] = {}
    
    for i in range(100):  # Assume max 100 textures
        tex_path = textures_dir / f"texture_{i}.png"
        if tex_path.exists():
            print(f"Loading {tex_path.name}...")
            textures[i] = Image.open(tex_path)
    
    if not textures:
        print("ERROR: No textures found in", textures_dir)
        return
    
    print(f"Loaded {len(textures)} texture atlases")
    
    # Process each sprite
    output_dir.mkdir(parents=True, exist_ok=True)
    
    sprites_exported = 0
    frames_exported = 0
    
    for sprite in extractor.sprites:
        if not sprite.frames and not include_empty:
            continue
        
        # Extract each frame - flat structure with sprite name prefix
        for frame in sprite.frames:
            tpage = frame.tpage
            
            if tpage.texture_id not in textures:
                print(f"  WARNING: {sprite.name} frame {frame.frame_index} references missing texture {tpage.texture_id}")
                continue
            
            tex = textures[tpage.texture_id]
            
            # Sanity check coordinates
            if (tpage.src_x + tpage.src_width > tex.width or 
                tpage.src_y + tpage.src_height > tex.height):
                print(f"  WARNING: {sprite.name} frame {frame.frame_index} has invalid coordinates")
                continue
            
            if tpage.src_width == 0 or tpage.src_height == 0:
                continue
            
            # Crop the frame from the atlas
            crop_box = (
                tpage.src_x,
                tpage.src_y,
                tpage.src_x + tpage.src_width,
                tpage.src_y + tpage.src_height
            )
            
            frame_img = tex.crop(crop_box)
            
            # GameMaker trims transparent pixels from sprites in the atlas.
            # We need to reconstruct the full frame using:
            # - sprite.width/height = the full intended size of the frame
            # - tpage.target_x/y = where to place the cropped image on the full canvas
            # - tpage.src_width/height = the actual cropped image size
            
            # Always create full-size canvas using sprite dimensions
            if sprite.width > 0 and sprite.height > 0:
                full_img = Image.new('RGBA', (sprite.width, sprite.height), (0, 0, 0, 0))
                full_img.paste(frame_img, (tpage.target_x, tpage.target_y))
                frame_img = full_img
            
            # Save frame with sprite name prefix and 2-digit padding
            frame_path = output_dir / f"{sprite.name}_{frame.frame_index:02d}.png"
            frame_img.save(frame_path)
            frames_exported += 1
        
        sprites_exported += 1
    
    print(f"\nExported {sprites_exported} sprites, {frames_exported} frames")


def main():
    parser = argparse.ArgumentParser(description='GM:S Sprite Atlas Slicer')
    parser.add_argument('input', help='Path to data.win')
    parser.add_argument('--textures', '-t', required=True, help='Path to textures directory')
    parser.add_argument('-o', '--output', default='sprites_output', help='Output directory')
    parser.add_argument('--include-empty', action='store_true', help='Include sprites with no frames')
    parser.add_argument('--list', action='store_true', help='List sprites only, do not extract')
    parser.add_argument('--debug', action='store_true', help='Show debug info')
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        return 1
    
    if not os.path.exists(args.textures):
        print(f"Error: Textures directory {args.textures} not found")
        return 1
    
    print(f"Loading: {args.input}")
    dw = DataWin(args.input)
    
    print("\nChunks found:")
    for cid, chunk in dw.chunks.items():
        print(f"  {chunk.name}: offset=0x{chunk.offset:08X}, size={chunk.size:,}")
    
    print()
    extractor = SpriteExtractor(dw)
    extractor.extract_all()
    
    if args.list:
        print("\nSprites:")
        for sprite in extractor.sprites:
            frames_info = f"{len(sprite.frames)} frames" if sprite.frames else "no frames"
            print(f"  [{sprite.index:4d}] {sprite.name} ({sprite.width}x{sprite.height}) - {frames_info}")
            
            if args.debug and sprite.frames:
                for frame in sprite.frames[:3]:  # Show first 3 frames
                    t = frame.tpage
                    print(f"         frame {frame.frame_index}: tex={t.texture_id} "
                          f"src=({t.src_x},{t.src_y},{t.src_width}x{t.src_height}) "
                          f"tgt=({t.target_x},{t.target_y},{t.target_width}x{t.target_height})")
                if len(sprite.frames) > 3:
                    print(f"         ... and {len(sprite.frames)-3} more frames")
        return 0
    
    print(f"\nSlicing sprites to: {args.output}")
    slice_sprites(extractor, Path(args.textures), Path(args.output), args.include_empty)
    
    print("\nDone!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
