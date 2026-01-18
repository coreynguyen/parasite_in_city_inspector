#!/usr/bin/env python3
"""
Game Maker Studio Audio Extractor
Extracts audio files from data.win with proper naming from SOND chunk
"""

import struct
import os
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional


class ChunkID:
    FORM = 0x4D524F46
    SOND = 0x444E4F53
    AUDO = 0x4F445541
    STRG = 0x47525453


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
            name = struct.pack('<I', cid).decode('ascii', errors='replace')
            self.chunks[cid] = Chunk(name, pos, size, pos + 8)
            pos += 8 + size
    
    def u16(self, off: int) -> int: 
        return struct.unpack_from('<H', self.data, off)[0]
    
    def u32(self, off: int) -> int: 
        return struct.unpack_from('<I', self.data, off)[0]
    
    def i32(self, off: int) -> int: 
        return struct.unpack_from('<i', self.data, off)[0]
    
    def f32(self, off: int) -> float: 
        return struct.unpack_from('<f', self.data, off)[0]
    
    def bytes(self, off: int, length: int) -> bytes: 
        return self.data[off:off + length]
    
    def gm_string(self, off: int) -> str:
        if off == 0 or off >= len(self.data) - 4:
            return ""
        length = self.u32(off)
        if length == 0 or length > 1000000 or off + 4 + length > len(self.data):
            return ""
        return self.data[off + 4:off + 4 + length].decode('utf-8', errors='replace')
    
    def c_string(self, off: int, max_len: int = 200) -> str:
        if off == 0 or off >= len(self.data):
            return ""
        end = self.data.find(b'\x00', off, off + max_len)
        if end > off:
            return self.data[off:end].decode('utf-8', errors='replace')
        return ""


@dataclass
class SoundDef:
    name: str
    index: int
    flags: int
    type_str: str
    file_str: str
    volume: float
    pitch: float
    group_id: int
    audio_id: int


class AudioExtractor:
    def __init__(self, dw: DataWin):
        self.dw = dw
        self.sounds: List[SoundDef] = []
        self.audio_data: Dict[int, bytes] = {}
    
    def extract_sounds(self):
        """Extract SOND chunk - sound definitions"""
        if ChunkID.SOND not in self.dw.chunks:
            print("WARNING: No SOND chunk found")
            return
        
        chunk = self.dw.chunks[ChunkID.SOND]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  SOND: {count} sound definitions")
        
        # Debug: dump first entry structure
        if count > 0:
            first_ptr = self.dw.u32(off + 4)
            print(f"\n  === DEBUG: First SOND entry at 0x{first_ptr:08X} ===")
            for field_off in range(0, 0x30, 4):
                val = self.dw.u32(first_ptr + field_off)
                # Try to interpret as string pointer
                str_val = ""
                if val > 0 and val < len(self.dw.data) - 4:
                    test_str = self.dw.gm_string(val)
                    if not test_str:
                        test_str = self.dw.c_string(val, 30)
                    if test_str:
                        str_val = f' -> "{test_str}"'
                print(f"    +0x{field_off:02X}: 0x{val:08X} ({val}){str_val}")
            print(f"  === END DEBUG ===\n")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if not ptr or ptr >= len(self.dw.data) - 32:
                continue
            
            # SOND entry structure:
            # +0x00: name_ptr
            # +0x04: flags
            # +0x08: type_ptr (e.g., ".ogg")
            # +0x0C: file_ptr (original filename)
            # +0x10: volume (float)
            # +0x14: pitch (float)  
            # +0x18: group_id (i32)
            # +0x1C: audio_id (i32) - index into AUDO chunk
            
            name_ptr = self.dw.u32(ptr)
            name = ""
            if name_ptr and name_ptr < len(self.dw.data):
                name = self.dw.gm_string(name_ptr)
                if not name:
                    name = self.dw.c_string(name_ptr)
            if not name:
                name = f"sound_{i}"
            
            type_ptr = self.dw.u32(ptr + 8)
            type_str = ""
            if type_ptr and type_ptr < len(self.dw.data):
                type_str = self.dw.gm_string(type_ptr)
                if not type_str:
                    type_str = self.dw.c_string(type_ptr)
            
            file_ptr = self.dw.u32(ptr + 12)
            file_str = ""
            if file_ptr and file_ptr < len(self.dw.data):
                file_str = self.dw.gm_string(file_ptr)
                if not file_str:
                    file_str = self.dw.c_string(file_ptr)
            
            self.sounds.append(SoundDef(
                name=name,
                index=i,
                flags=self.dw.u32(ptr + 4),
                type_str=type_str,
                file_str=file_str,
                volume=self.dw.f32(ptr + 16),
                pitch=self.dw.f32(ptr + 20),
                group_id=self.dw.i32(ptr + 24),
                audio_id=self.dw.i32(ptr + 28)
            ))
    
    def extract_audio(self):
        """Extract AUDO chunk - raw audio data"""
        if ChunkID.AUDO not in self.dw.chunks:
            print("WARNING: No AUDO chunk found")
            return
        
        chunk = self.dw.chunks[ChunkID.AUDO]
        off = chunk.data_start
        count = self.dw.u32(off)
        
        print(f"  AUDO: {count} audio entries")
        
        for i in range(count):
            ptr = self.dw.u32(off + 4 + i * 4)
            if not ptr or ptr >= len(self.dw.data) - 4:
                continue
            
            # AUDO entry: [length:u32][data...]
            length = self.dw.u32(ptr)
            if length > 0 and length < 100000000 and ptr + 4 + length <= len(self.dw.data):
                self.audio_data[i] = self.dw.bytes(ptr + 4, length)
    
    def detect_format(self, data: bytes) -> str:
        """Detect audio format from magic bytes"""
        if data[:4] == b'OggS':
            return '.ogg'
        elif data[:4] == b'RIFF':
            return '.wav'
        elif data[:3] == b'ID3' or (len(data) > 1 and data[:2] == b'\xff\xfb'):
            return '.mp3'
        elif data[:4] == b'fLaC':
            return '.flac'
        else:
            return '.bin'
    
    def extract_all(self):
        print("Extracting sound definitions...")
        self.extract_sounds()
        print("Extracting audio data...")
        self.extract_audio()
        
        # Build audio_id to name mapping
        id_to_name = {}
        for snd in self.sounds:
            if snd.audio_id >= 0:
                id_to_name[snd.audio_id] = snd.name
        
        print(f"  Mapped {len(id_to_name)} audio IDs to names")


def main():
    parser = argparse.ArgumentParser(description='GM:S Audio Extractor')
    parser.add_argument('input', help='Path to data.win')
    parser.add_argument('-o', '--output', default='audio_output', help='Output directory')
    parser.add_argument('--list', action='store_true', help='List sounds only')
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found")
        return 1
    
    print(f"Loading: {args.input}")
    dw = DataWin(args.input)
    
    print("\nChunks found:")
    for cid, chunk in dw.chunks.items():
        print(f"  {chunk.name}: offset=0x{chunk.offset:08X}, size={chunk.size:,}")
    
    print()
    extractor = AudioExtractor(dw)
    extractor.extract_all()
    
    if args.list:
        print("\nSound definitions:")
        for snd in extractor.sounds:
            audio_info = f"audio_id={snd.audio_id}" if snd.audio_id >= 0 else "no audio"
            print(f"  [{snd.index:3d}] {snd.name}")
            print(f"        type={snd.type_str}, file={snd.file_str}")
            print(f"        volume={snd.volume:.2f}, pitch={snd.pitch:.2f}, {audio_info}")
        return 0
    
    # Export audio files
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    
    # Build audio_id to name mapping
    id_to_name = {}
    for snd in extractor.sounds:
        if snd.audio_id >= 0:
            id_to_name[snd.audio_id] = snd.name
    
    print(f"\nExporting to: {args.output}")
    exported = 0
    
    for audio_id, data in extractor.audio_data.items():
        # Get name from sound definition, or use generic name
        name = id_to_name.get(audio_id, f"audio_{audio_id}")
        
        # Detect format and add extension
        ext = extractor.detect_format(data)
        
        # Clean filename
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in name)
        
        filepath = out / f"{safe_name}{ext}"
        with open(filepath, 'wb') as f:
            f.write(data)
        exported += 1
    
    print(f"Exported {exported} audio files")
    
    # Also save a manifest
    manifest_path = out / "_manifest.txt"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        f.write("# Audio Manifest\n")
        f.write("# name | volume | pitch | original_file\n\n")
        for snd in extractor.sounds:
            f.write(f"{snd.name}\t{snd.volume:.2f}\t{snd.pitch:.2f}\t{snd.file_str}\n")
    
    print(f"Saved manifest to: {manifest_path}")
    print("\nDone!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
