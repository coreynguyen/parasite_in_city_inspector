#!/usr/bin/env python3
"""
Game Maker Room to MaxScript Converter - GUI Version
Simple interface for converting rooms from data.win to MaxScript files
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading

# Import the converter
from gm_to_maxscript import (
    RoomConverter, 
    DEFAULT_DATA_WIN, 
    DEFAULT_SPRITE_PATH, 
    DEFAULT_OUTPUT_DIR
)


class Colors:
    BG = '#1e1e1e'
    BG2 = '#252526'
    BG3 = '#2d2d2d'
    FG = '#d4d4d4'
    ACCENT = '#0078d4'
    SELECT = '#094771'


def setup_dark_theme(root):
    style = ttk.Style()
    try:
        style.theme_use('clam')
    except:
        pass
    
    style.configure('.', background=Colors.BG, foreground=Colors.FG)
    style.configure('TFrame', background=Colors.BG)
    style.configure('TLabel', background=Colors.BG, foreground=Colors.FG)
    style.configure('TButton', background=Colors.BG3, foreground=Colors.FG)
    style.map('TButton', background=[('active', Colors.ACCENT)])
    style.configure('TEntry', fieldbackground=Colors.BG2, foreground=Colors.FG)
    style.configure('TLabelframe', background=Colors.BG, foreground=Colors.FG)
    style.configure('TLabelframe.Label', background=Colors.BG, foreground=Colors.FG)
    style.configure('Treeview', background=Colors.BG, foreground=Colors.FG, fieldbackground=Colors.BG)
    style.map('Treeview', background=[('selected', Colors.SELECT)])
    
    root.configure(bg=Colors.BG)


class ConverterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GM Room to MaxScript Converter")
        self.root.geometry("900x700")
        setup_dark_theme(root)
        
        self.converter = None
        self.build_ui()
    
    def build_ui(self):
        # Main container
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill='both', expand=True)
        
        # Paths frame
        paths_frame = ttk.LabelFrame(main, text="Paths", padding=10)
        paths_frame.pack(fill='x', pady=(0, 10))
        
        # Data.win path
        ttk.Label(paths_frame, text="data.win:").grid(row=0, column=0, sticky='w')
        self.data_win_var = tk.StringVar(value=DEFAULT_DATA_WIN)
        ttk.Entry(paths_frame, textvariable=self.data_win_var, width=70).grid(row=0, column=1, padx=5)
        ttk.Button(paths_frame, text="Browse", command=self.browse_data_win).grid(row=0, column=2)
        
        # Sprites path
        ttk.Label(paths_frame, text="Sprites folder:").grid(row=1, column=0, sticky='w', pady=(5,0))
        self.sprites_var = tk.StringVar(value=DEFAULT_SPRITE_PATH)
        ttk.Entry(paths_frame, textvariable=self.sprites_var, width=70).grid(row=1, column=1, padx=5, pady=(5,0))
        ttk.Button(paths_frame, text="Browse", command=self.browse_sprites).grid(row=1, column=2, pady=(5,0))
        
        # Output path
        ttk.Label(paths_frame, text="Output folder:").grid(row=2, column=0, sticky='w', pady=(5,0))
        self.output_var = tk.StringVar(value=DEFAULT_OUTPUT_DIR)
        ttk.Entry(paths_frame, textvariable=self.output_var, width=70).grid(row=2, column=1, padx=5, pady=(5,0))
        ttk.Button(paths_frame, text="Browse", command=self.browse_output).grid(row=2, column=2, pady=(5,0))
        
        # Load button
        ttk.Button(paths_frame, text="Load data.win", command=self.load_data).grid(row=3, column=1, pady=(10,0))
        
        # Rooms frame
        rooms_frame = ttk.LabelFrame(main, text="Rooms", padding=10)
        rooms_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # Room list
        list_frame = ttk.Frame(rooms_frame)
        list_frame.pack(side='left', fill='both', expand=True)
        
        self.room_list = tk.Listbox(list_frame, bg=Colors.BG2, fg=Colors.FG, 
                                     selectbackground=Colors.SELECT, selectmode='extended',
                                     width=30, height=15)
        self.room_list.pack(side='left', fill='both', expand=True)
        self.room_list.bind('<<ListboxSelect>>', self.on_room_select)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.room_list.yview)
        scrollbar.pack(side='right', fill='y')
        self.room_list.config(yscrollcommand=scrollbar.set)
        
        # Room info
        info_frame = ttk.Frame(rooms_frame)
        info_frame.pack(side='right', fill='both', expand=True, padx=(10, 0))
        
        ttk.Label(info_frame, text="Room Info:").pack(anchor='w')
        self.info_text = scrolledtext.ScrolledText(info_frame, bg=Colors.BG2, fg=Colors.FG,
                                                    width=50, height=15, wrap='word')
        self.info_text.pack(fill='both', expand=True)
        
        # Actions frame
        actions_frame = ttk.Frame(main)
        actions_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(actions_frame, text="Convert Selected", command=self.convert_selected).pack(side='left', padx=5)
        ttk.Button(actions_frame, text="Convert All", command=self.convert_all).pack(side='left', padx=5)
        ttk.Button(actions_frame, text="Export JSON", command=self.export_json).pack(side='left', padx=5)
        
        self.also_json_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions_frame, text="Also export JSON", variable=self.also_json_var).pack(side='left', padx=20)
        
        # Log frame
        log_frame = ttk.LabelFrame(main, text="Log", padding=5)
        log_frame.pack(fill='x')
        
        self.log_text = scrolledtext.ScrolledText(log_frame, bg=Colors.BG2, fg=Colors.FG,
                                                   height=8, wrap='word')
        self.log_text.pack(fill='x')
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready - Load a data.win file to begin")
        ttk.Label(main, textvariable=self.status_var).pack(anchor='w', pady=(5, 0))
    
    def log(self, msg):
        self.log_text.insert('end', msg + '\n')
        self.log_text.see('end')
        self.root.update_idletasks()
    
    def browse_data_win(self):
        path = filedialog.askopenfilename(
            title="Select data.win",
            filetypes=[("data.win", "data.win"), ("All files", "*.*")]
        )
        if path:
            self.data_win_var.set(path)
    
    def browse_sprites(self):
        path = filedialog.askdirectory(title="Select Sprites Folder")
        if path:
            self.sprites_var.set(path)
    
    def browse_output(self):
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_var.set(path)
    
    def load_data(self):
        data_win = self.data_win_var.get()
        sprites = self.sprites_var.get()
        output = self.output_var.get()
        
        if not os.path.exists(data_win):
            messagebox.showerror("Error", f"data.win not found: {data_win}")
            return
        
        self.log(f"Loading {data_win}...")
        self.status_var.set("Loading...")
        self.root.update_idletasks()
        
        try:
            self.converter = RoomConverter(data_win, sprites, output)
            self.converter.load(verbose=False)
            
            # Populate room list
            self.room_list.delete(0, 'end')
            for room_name in self.converter.list_rooms():
                self.room_list.insert('end', room_name)
            
            self.log(f"Loaded {len(self.converter.extractor.rooms)} rooms")
            self.log(f"Found {len(self.converter.extractor.sprites)} sprites")
            self.log(f"Found {len(self.converter.extractor.objects)} objects")
            self.log(f"Found {len(self.converter.sprite_mapper.sprite_folders)} sprite folders")
            
            self.status_var.set(f"Loaded - {len(self.converter.extractor.rooms)} rooms available")
            
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
            self.status_var.set("Error loading file")
    
    def on_room_select(self, event):
        if not self.converter:
            return
        
        selection = self.room_list.curselection()
        if not selection:
            return
        
        room_name = self.room_list.get(selection[0])
        info = self.converter.get_room_info(room_name)
        
        self.info_text.delete('1.0', 'end')
        if info:
            self.info_text.insert('1.0', info)
    
    def convert_selected(self):
        if not self.converter:
            messagebox.showwarning("Warning", "Load a data.win file first")
            return
        
        selection = self.room_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Select one or more rooms to convert")
            return
        
        for idx in selection:
            room_name = self.room_list.get(idx)
            self.log(f"Converting {room_name}...")
            
            try:
                path = self.converter.convert_room(room_name, verbose=False)
                if path:
                    self.log(f"  -> {path}")
                    
                    if self.also_json_var.get():
                        json_path = self.converter.export_room_json(room_name)
                        if json_path:
                            self.log(f"  -> {json_path}")
            except Exception as e:
                self.log(f"  ERROR: {e}")
        
        self.log("Done!")
        self.status_var.set(f"Converted {len(selection)} room(s)")
    
    def convert_all(self):
        if not self.converter:
            messagebox.showwarning("Warning", "Load a data.win file first")
            return
        
        if not messagebox.askyesno("Confirm", "Convert all rooms? This may take a while."):
            return
        
        self.log("Converting all rooms...")
        self.status_var.set("Converting...")
        self.root.update_idletasks()
        
        try:
            paths = self.converter.convert_all_rooms(verbose=False)
            self.log(f"Generated {len(paths)} MaxScript files")
            self.status_var.set(f"Done - {len(paths)} files generated")
        except Exception as e:
            self.log(f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
    
    def export_json(self):
        if not self.converter:
            messagebox.showwarning("Warning", "Load a data.win file first")
            return
        
        selection = self.room_list.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Select one or more rooms to export")
            return
        
        for idx in selection:
            room_name = self.room_list.get(idx)
            self.log(f"Exporting {room_name} as JSON...")
            
            try:
                path = self.converter.export_room_json(room_name)
                if path:
                    self.log(f"  -> {path}")
            except Exception as e:
                self.log(f"  ERROR: {e}")
        
        self.log("Done!")


def main():
    root = tk.Tk()
    app = ConverterGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
