#!/usr/bin/env python3
"""
Game Maker Studio Room & Object Exporter
Exports OBJT and ROOM data to JSON, with optional visual room rendering

Usage:
    python room_exporter.py data.win -o output_dir
    python room_exporter.py data.win -o output_dir --render --textures ./textures
"""

import struct
import os
import sys
import json
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# =============================================================================
# DATA.WIN READER
# =============================================================================

class ChunkID:
    FORM = 0x4D524F46
    STRG = 0x47525453
    SPRT = 0x54525053
    TPAG = 0x47415054
    BGND = 0x444E4742
    OBJT = 0x544A424F
    ROOM = 0x4D4F4F52
    
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
    def f32(self, off: int) -> float: return struct.unpack_from('<f', self.data, off)[0]
    
    def gm_string(self, off: int) -> str:
        if off == 0 or off >= len(self.data) - 4:
            return ""
        length = self.u32(off)
        if length == 0 or length > 1000000 or off + 4 + length > len(self.data):
            return ""
        return self.data[off + 4:off + 4 + length].decode('utf-8', errors='replace')
    
    def c_string(self, off: int, max_len: int = 200) -> str:
        """Read null-terminated C string"""
        if off == 0 or off >= len(self.data):
            return ""
        end = self.data.find(b'\x00', off, off + max_len)
        if end > off:
            return self.data[off:end].decode('utf-8', errors='replace')
        return ""


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class GameObject:
    index: int
    name: str
    sprite_index: int
    visible: bool
    solid: bool
    depth: int
    persistent: bool
    parent_index: int
    mask_index: int
    physics_enabled: bool = False


@dataclass
class RoomInstance:
    x: int
    y: int
    object_index: int
    instance_id: int
    creation_code: int = 0
    scale_x: float = 1.0
    scale_y: float = 1.0
    color: int = 0xFFFFFFFF
    rotation: float = 0.0


@dataclass
class RoomBackground:
    enabled: bool
    foreground: bool
    background_index: int
    x: int
    y: int
    tile_x: bool
    tile_y: bool
    speed_x: int
    speed_y: int
    stretch: bool


@dataclass
class RoomView:
    enabled: bool
    view_x: int
    view_y: int
    view_width: int
    view_height: int
    port_x: int
    port_y: int
    port_width: int
    port_height: int
    border_x: int
    border_y: int
    speed_x: int
    speed_y: int
    object_index: int


@dataclass
class Room:
    index: int
    name: str
    caption: str
    width: int
    height: int
    speed: int
    persistent: bool
    color: int
    show_color: bool
    creation_code: int
    flags: int
    backgrounds: List[RoomBackground]
    views: List[RoomView]
    instances: List[RoomInstance]
    tiles: List[dict]


@dataclass
class Background:
    index: int
    name: str
    transparent: bool
    smooth: bool
    preload: bool
    texture_id: int
    tile_width: int
    tile_height: int


@dataclass
class TexturePageEntry:
    src_x: int
    src_y: int
    src_width: int
    src_height: int
    target_x: int
    target_y: int
    target_width: int
    target_height: int
    bounding_width: int
    bounding_height: int
    texture_id: int


@dataclass
class Sprite:
    index: int
    name: str
    width: int
    height: int
    origin_x: int
    origin_y: int
    frames: List[TexturePageEntry]


# =============================================================================
# EXTRACTOR
# =============================================================================

class GameDataExtractor:
    def __init__(self, dw: DataWin):
        self.dw = dw
        self.objects: List[GameObject] = []
        self.rooms: List[Room] = []
        self.backgrounds: List[Background] = []
        self.sprites: List[Sprite] = []
        self.object_by_index: Dict[int, GameObject] = {}
        self.sprite_by_index: Dict[int, Sprite] = {}
    
    def extract_objects(self):
        """Extract OBJT chunk"""
        if ChunkID.OBJT not in self.dw.chunks:
            return
        
        chunk = self.dw.chunks[ChunkID.OBJT]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  OBJT: {count} objects")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if not ptr or ptr >= len(self.dw.data) - 32:
                continue
            
            # OBJT entry structure:
            # +0x00: name_ptr
            # +0x04: sprite_index
            # +0x08: visible
            # +0x0C: solid
            # +0x10: depth
            # +0x14: persistent
            # +0x18: parent_index
            # +0x1C: mask_index
            # +0x20: physics...
            
            name_ptr = self.dw.u32(ptr)
            name = self.dw.c_string(name_ptr) if name_ptr else f"object_{i}"
            
            obj = GameObject(
                index=i,
                name=name,
                sprite_index=self.dw.i32(ptr + 4),
                visible=bool(self.dw.u32(ptr + 8)),
                solid=bool(self.dw.u32(ptr + 12)),
                depth=self.dw.i32(ptr + 16),
                persistent=bool(self.dw.u32(ptr + 20)),
                parent_index=self.dw.i32(ptr + 24),
                mask_index=self.dw.i32(ptr + 28),
            )
            
            self.objects.append(obj)
            self.object_by_index[i] = obj
    
    def extract_backgrounds(self):
        """Extract BGND chunk"""
        if ChunkID.BGND not in self.dw.chunks:
            return
        
        chunk = self.dw.chunks[ChunkID.BGND]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  BGND: {count} backgrounds")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if not ptr or ptr >= len(self.dw.data) - 20:
                continue
            
            name_ptr = self.dw.u32(ptr)
            name = self.dw.c_string(name_ptr) if name_ptr else f"background_{i}"
            
            bg = Background(
                index=i,
                name=name,
                transparent=bool(self.dw.u32(ptr + 4)),
                smooth=bool(self.dw.u32(ptr + 8)),
                preload=bool(self.dw.u32(ptr + 12)),
                texture_id=self.dw.i32(ptr + 16) if ptr + 20 <= len(self.dw.data) else -1,
                tile_width=0,
                tile_height=0,
            )
            
            self.backgrounds.append(bg)
    
    def extract_sprites(self):
        """Extract SPRT chunk (basic info for room rendering)"""
        if ChunkID.SPRT not in self.dw.chunks:
            return
        
        chunk = self.dw.chunks[ChunkID.SPRT]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  SPRT: {count} sprites")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if not ptr or ptr >= len(self.dw.data) - 60:
                continue
            
            name_ptr = self.dw.u32(ptr)
            name = self.dw.c_string(name_ptr) if name_ptr else f"sprite_{i}"
            
            width = self.dw.u32(ptr + 4)
            height = self.dw.u32(ptr + 8)
            origin_x = self.dw.i32(ptr + 0x30)
            origin_y = self.dw.i32(ptr + 0x34)
            frame_count = self.dw.u32(ptr + 0x38)
            
            frames = []
            if frame_count < 1000:
                for j in range(frame_count):
                    tpage_ptr = self.dw.u32(ptr + 0x3C + j * 4)
                    if tpage_ptr and tpage_ptr < len(self.dw.data) - 22:
                        tpe = TexturePageEntry(
                            src_x=self.dw.u16(tpage_ptr),
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
                        if tpe.texture_id < 100:
                            frames.append(tpe)
            
            sprite = Sprite(
                index=i,
                name=name,
                width=width,
                height=height,
                origin_x=origin_x,
                origin_y=origin_y,
                frames=frames
            )
            
            self.sprites.append(sprite)
            self.sprite_by_index[i] = sprite
    
    def extract_rooms(self):
        """Extract ROOM chunk"""
        if ChunkID.ROOM not in self.dw.chunks:
            return
        
        chunk = self.dw.chunks[ChunkID.ROOM]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  ROOM: {count} rooms")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if not ptr or ptr >= len(self.dw.data) - 80:
                continue
            
            # ROOM entry structure:
            # +0x00: name_ptr
            # +0x04: caption_ptr
            # +0x08: width
            # +0x0C: height
            # +0x10: speed
            # +0x14: persistent
            # +0x18: color
            # +0x1C: show_color
            # +0x20: creation_code
            # +0x24: flags
            # +0x28: backgrounds_ptr (pointer to list)
            # +0x2C: views_ptr
            # +0x30: instances_ptr
            # +0x34: tiles_ptr
            
            name_ptr = self.dw.u32(ptr)
            name = self.dw.c_string(name_ptr) if name_ptr else f"room_{i}"
            
            caption_ptr = self.dw.u32(ptr + 4)
            caption = self.dw.c_string(caption_ptr) if caption_ptr else ""
            
            room = Room(
                index=i,
                name=name,
                caption=caption,
                width=self.dw.u32(ptr + 8),
                height=self.dw.u32(ptr + 12),
                speed=self.dw.u32(ptr + 16),
                persistent=bool(self.dw.u32(ptr + 20)),
                color=self.dw.u32(ptr + 24),
                show_color=bool(self.dw.u32(ptr + 28)),
                creation_code=self.dw.i32(ptr + 32),
                flags=self.dw.u32(ptr + 36),
                backgrounds=[],
                views=[],
                instances=[],
                tiles=[]
            )
            
            # Parse backgrounds (8 entries typically)
            bg_ptr = self.dw.u32(ptr + 40)
            if bg_ptr and bg_ptr < len(self.dw.data) - 4:
                bg_count = self.dw.u32(bg_ptr)
                for j in range(min(bg_count, 8)):
                    bg_entry_ptr = self.dw.u32(bg_ptr + 4 + j * 4)
                    if bg_entry_ptr and bg_entry_ptr < len(self.dw.data) - 40:
                        room.backgrounds.append(RoomBackground(
                            enabled=bool(self.dw.u32(bg_entry_ptr)),
                            foreground=bool(self.dw.u32(bg_entry_ptr + 4)),
                            background_index=self.dw.i32(bg_entry_ptr + 8),
                            x=self.dw.i32(bg_entry_ptr + 12),
                            y=self.dw.i32(bg_entry_ptr + 16),
                            tile_x=bool(self.dw.u32(bg_entry_ptr + 20)),
                            tile_y=bool(self.dw.u32(bg_entry_ptr + 24)),
                            speed_x=self.dw.i32(bg_entry_ptr + 28),
                            speed_y=self.dw.i32(bg_entry_ptr + 32),
                            stretch=bool(self.dw.u32(bg_entry_ptr + 36)),
                        ))
            
            # Parse views (8 entries typically)
            view_ptr = self.dw.u32(ptr + 44)
            if view_ptr and view_ptr < len(self.dw.data) - 4:
                view_count = self.dw.u32(view_ptr)
                for j in range(min(view_count, 8)):
                    view_entry_ptr = self.dw.u32(view_ptr + 4 + j * 4)
                    if view_entry_ptr and view_entry_ptr < len(self.dw.data) - 56:
                        room.views.append(RoomView(
                            enabled=bool(self.dw.u32(view_entry_ptr)),
                            view_x=self.dw.i32(view_entry_ptr + 4),
                            view_y=self.dw.i32(view_entry_ptr + 8),
                            view_width=self.dw.u32(view_entry_ptr + 12),
                            view_height=self.dw.u32(view_entry_ptr + 16),
                            port_x=self.dw.i32(view_entry_ptr + 20),
                            port_y=self.dw.i32(view_entry_ptr + 24),
                            port_width=self.dw.u32(view_entry_ptr + 28),
                            port_height=self.dw.u32(view_entry_ptr + 32),
                            border_x=self.dw.u32(view_entry_ptr + 36),
                            border_y=self.dw.u32(view_entry_ptr + 40),
                            speed_x=self.dw.i32(view_entry_ptr + 44),
                            speed_y=self.dw.i32(view_entry_ptr + 48),
                            object_index=self.dw.i32(view_entry_ptr + 52),
                        ))
            
            # Parse instances
            inst_ptr = self.dw.u32(ptr + 48)
            if inst_ptr and inst_ptr < len(self.dw.data) - 4:
                inst_count = self.dw.u32(inst_ptr)
                for j in range(min(inst_count, 10000)):
                    inst_entry_ptr = self.dw.u32(inst_ptr + 4 + j * 4)
                    if inst_entry_ptr and inst_entry_ptr < len(self.dw.data) - 16:
                        room.instances.append(RoomInstance(
                            x=self.dw.i32(inst_entry_ptr),
                            y=self.dw.i32(inst_entry_ptr + 4),
                            object_index=self.dw.i32(inst_entry_ptr + 8),
                            instance_id=self.dw.u32(inst_entry_ptr + 12),
                        ))
            
            self.rooms.append(room)
    
    def extract_all(self):
        print("Extracting game data...")
        self.extract_objects()
        self.extract_backgrounds()
        self.extract_sprites()
        self.extract_rooms()


# =============================================================================
# ROOM RENDERER
# =============================================================================

class RoomRenderer:
    def __init__(self, extractor: GameDataExtractor, textures_dir: Path):
        self.extractor = extractor
        self.textures: Dict[int, Image.Image] = {}
        self.sprite_images: Dict[int, Image.Image] = {}  # First frame of each sprite
        
        # Load textures
        for i in range(100):
            tex_path = textures_dir / f"texture_{i}.png"
            if tex_path.exists():
                self.textures[i] = Image.open(tex_path).convert('RGBA')
        
        print(f"  Loaded {len(self.textures)} textures for rendering")
        
        # Pre-extract first frame of each sprite
        for sprite in extractor.sprites:
            if sprite.frames:
                frame = sprite.frames[0]
                if frame.texture_id in self.textures:
                    tex = self.textures[frame.texture_id]
                    if (frame.src_x + frame.src_width <= tex.width and
                        frame.src_y + frame.src_height <= tex.height):
                        crop = tex.crop((
                            frame.src_x, frame.src_y,
                            frame.src_x + frame.src_width,
                            frame.src_y + frame.src_height
                        ))
                        # Create full frame with offset
                        full = Image.new('RGBA', (frame.target_width, frame.target_height), (0, 0, 0, 0))
                        full.paste(crop, (frame.target_x, frame.target_y))
                        self.sprite_images[sprite.index] = full
    
    def render_room(self, room: Room, max_size: int = 4096) -> Image.Image:
        """Render a room to an image"""
        # Limit size for very large rooms
        width = min(room.width, max_size)
        height = min(room.height, max_size)
        scale = min(1.0, max_size / max(room.width, room.height))
        
        # Create canvas
        bg_color = (
            (room.color >> 16) & 0xFF,
            (room.color >> 8) & 0xFF,
            room.color & 0xFF,
            255
        ) if room.show_color else (64, 64, 64, 255)
        
        img = Image.new('RGBA', (int(room.width * scale), int(room.height * scale)), bg_color)
        
        # Sort instances by depth (higher depth = drawn first/behind)
        instances_with_depth = []
        for inst in room.instances:
            obj = self.extractor.object_by_index.get(inst.object_index)
            depth = obj.depth if obj else 0
            instances_with_depth.append((depth, inst, obj))
        
        # Sort by depth descending (higher depth = behind)
        instances_with_depth.sort(key=lambda x: -x[0])
        
        # Draw instances
        for depth, inst, obj in instances_with_depth:
            if not obj:
                continue
            
            sprite_idx = obj.sprite_index
            if sprite_idx < 0 or sprite_idx not in self.sprite_images:
                continue
            
            sprite = self.extractor.sprite_by_index.get(sprite_idx)
            if not sprite:
                continue
            
            sprite_img = self.sprite_images[sprite_idx]
            
            # Calculate position (accounting for origin)
            x = int((inst.x - sprite.origin_x) * scale)
            y = int((inst.y - sprite.origin_y) * scale)
            
            # Scale sprite if needed
            if scale != 1.0:
                new_size = (int(sprite_img.width * scale), int(sprite_img.height * scale))
                if new_size[0] > 0 and new_size[1] > 0:
                    sprite_img = sprite_img.resize(new_size, Image.Resampling.NEAREST)
            
            # Paste with alpha
            if 0 <= x < img.width and 0 <= y < img.height:
                img.paste(sprite_img, (x, y), sprite_img)
        
        return img


# =============================================================================
# MAIN
# =============================================================================

def save_json(path: Path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=lambda o: asdict(o) if hasattr(o, '__dataclass_fields__') else str(o))


def main():
    parser = argparse.ArgumentParser(description='GM:S Room & Object Exporter')
    parser.add_argument('input', help='Path to data.win')
    parser.add_argument('-o', '--output', default='room_export', help='Output directory')
    parser.add_argument('--render', action='store_true', help='Render room images')
    parser.add_argument('--textures', '-t', help='Path to textures directory (required for --render)')
    parser.add_argument('--max-size', type=int, default=4096, help='Max rendered image dimension')
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        return 1
    
    if args.render and not args.textures:
        print("Error: --textures required for --render")
        return 1
    
    if args.render and not HAS_PIL:
        print("Error: Pillow required for --render. Install with: pip install Pillow")
        return 1
    
    print(f"Loading: {args.input}")
    dw = DataWin(args.input)
    
    extractor = GameDataExtractor(dw)
    extractor.extract_all()
    
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    
    # Export objects
    print("\nExporting objects...")
    objects_data = [asdict(obj) for obj in extractor.objects]
    save_json(out / "objects.json", objects_data)
    print(f"  Saved {len(extractor.objects)} objects")
    
    # Export backgrounds
    print("Exporting backgrounds...")
    bg_data = [asdict(bg) for bg in extractor.backgrounds]
    save_json(out / "backgrounds.json", bg_data)
    print(f"  Saved {len(extractor.backgrounds)} backgrounds")
    
    # Export rooms
    print("Exporting rooms...")
    rooms_dir = out / "rooms"
    rooms_dir.mkdir(exist_ok=True)
    
    for room in extractor.rooms:
        room_data = {
            'index': room.index,
            'name': room.name,
            'caption': room.caption,
            'width': room.width,
            'height': room.height,
            'speed': room.speed,
            'persistent': room.persistent,
            'color': room.color,
            'show_color': room.show_color,
            'backgrounds': [asdict(bg) for bg in room.backgrounds],
            'views': [asdict(v) for v in room.views],
            'instances': [],
        }
        
        # Add instance data with object names
        for inst in room.instances:
            obj = extractor.object_by_index.get(inst.object_index)
            inst_data = asdict(inst)
            inst_data['object_name'] = obj.name if obj else f"object_{inst.object_index}"
            room_data['instances'].append(inst_data)
        
        save_json(rooms_dir / f"{room.name}.json", room_data)
    
    print(f"  Saved {len(extractor.rooms)} rooms")
    
    # Render rooms if requested
    if args.render:
        print("\nRendering room images...")
        renderer = RoomRenderer(extractor, Path(args.textures))
        
        render_dir = out / "room_renders"
        render_dir.mkdir(exist_ok=True)
        
        for room in extractor.rooms:
            print(f"  Rendering {room.name} ({room.width}x{room.height})...")
            try:
                img = renderer.render_room(room, args.max_size)
                img.save(render_dir / f"{room.name}.png")
            except Exception as e:
                print(f"    Error: {e}")
        
        print(f"  Rendered {len(extractor.rooms)} rooms")
    
    # Create summary
    summary = {
        'objects_count': len(extractor.objects),
        'backgrounds_count': len(extractor.backgrounds),
        'sprites_count': len(extractor.sprites),
        'rooms_count': len(extractor.rooms),
        'rooms': [{'name': r.name, 'size': f"{r.width}x{r.height}", 'instances': len(r.instances)} for r in extractor.rooms],
    }
    save_json(out / "summary.json", summary)
    
    print(f"\nDone! Output in: {args.output}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
