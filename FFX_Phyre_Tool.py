"""
FFX Phyre Tool - Asset Extraction & Repacking Utility
Created and Authored by NfgOdin
"""

import os
import sys
import subprocess
import argparse
import threading
import json
import tempfile
import shutil
import math
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk




if getattr(sys, 'frozen', False):
    script_dir = os.path.dirname(sys.executable)
else:
    script_dir = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(script_dir, "ffx_phyre_tool_recent_files.json")

# Define default paths relative to script/exe folder looking in local tools/ folder
DEFAULT_FFXII_CONVERT = os.path.join(script_dir, "tools", "FFXIIConvert", "FFXIIConvert.exe")
DEFAULT_NOESIS = os.path.join(script_dir, "tools", "noesis", "Noesis64.exe")
DEFAULT_TEXCONV = os.path.join(script_dir, "tools", "textconv", "texconv.exe")
DEFAULT_COMPRESSONATOR = os.path.join(script_dir, "tools", "Compressonator", "CompressonatorCLI.exe")


def get_phyre_texture_format(phyre_path):
    """Scans the first 0x2000 bytes of a .phyre file for texture format signatures."""
    try:
        if not os.path.exists(phyre_path):
            return None
        with open(phyre_path, "rb") as f:
            data = f.read(0x2000)
        # Search for known compression signature descriptors
        for fmt in [b"DXT5", b"DXT3", b"DXT1", b"BC1", b"BC2", b"BC3", b"BC7"]:
            if fmt in data:
                return fmt.decode()
    except Exception:
        pass
    return None


class PhyreToolBackend:
    def __init__(self, ffxii_convert_path=None, noesis_path=None, texconv_path=None, compressonator_path=None, log_callback=None):
        config_file = CONFIG_FILE
        config = {}
        if os.path.exists(config_file):
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
            except Exception:
                pass
        cfg_convert = config.get("ffxii_convert_path")
        self.ffxii_convert_path = ffxii_convert_path or (cfg_convert if cfg_convert and os.path.exists(cfg_convert) else None) or DEFAULT_FFXII_CONVERT
        cfg_noesis = config.get("noesis_path")
        self.noesis_path = noesis_path or (cfg_noesis if cfg_noesis and os.path.exists(cfg_noesis) else None) or DEFAULT_NOESIS
        cfg_texconv = config.get("texconv_path")
        self.texconv_path = texconv_path or (cfg_texconv if cfg_texconv and os.path.exists(cfg_texconv) else None) or DEFAULT_TEXCONV
        cfg_comp = config.get("compressonator_path")
        self.compressonator_path = compressonator_path or (cfg_comp if cfg_comp and os.path.exists(cfg_comp) else None) or DEFAULT_COMPRESSONATOR
        self.dds_encoder = config.get("dds_encoder", "texconv")
        self.texconv_dither = config.get("texconv_dither", False)
        self.log_callback = log_callback or self._default_log


    def _default_log(self, text):
        print(text)

    def log(self, text):
        self.log_callback(text + "\n")

    def run_cmd(self, cmd):
        self.log(f"Running: {' '.join(cmd)}")
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                self.log(f"  [Output] {line.strip()}")
            process.wait()
            return process.returncode
        except Exception as e:
            self.log(f"  [Error] Failed to execute process: {str(e)}")
            return -1

    def unpack(self, phyre_in, out_model):
        if not os.path.exists(self.ffxii_convert_path):
            msg = f"FFXIIConvert.exe was not found at:\n{self.ffxii_convert_path}\n\nPlease place FFXIIConvert.exe in the 'tools/' directory or configure its path in Settings."
            self.log(msg)
            try:
                messagebox.showerror("Tool Not Found", msg)
            except Exception:
                pass
            return False


        # Detect texture vs model
        is_texture = phyre_in.lower().endswith('.dds.phyre') or out_model.lower().endswith('.png') or out_model.lower().endswith('.dds')

        if is_texture:
            self.log(f"--- Starting Texture Unpack of {os.path.basename(phyre_in)} ---")
            ret = self.run_cmd([self.ffxii_convert_path, "unpack", phyre_in, out_model])
            if ret != 0 or not os.path.exists(out_model):
                self.log("Error: Texture unpack failed.")
                return False
            self.log("--- Texture Unpack Successful ---")
            return True

        # Model unpack (standard gltf)
        if not os.path.exists(self.noesis_path):
            msg = f"Noesis64.exe was not found at:\n{self.noesis_path}\n\nPlease place Noesis64.exe in the 'tools/' directory or configure its path in Settings."
            self.log(msg)
            try:
                messagebox.showerror("Tool Not Found", msg)
            except Exception:
                pass
            return False


        temp_fbx = os.path.splitext(out_model)[0] + "_temp.fbx"
        if os.path.exists(temp_fbx):
            os.remove(temp_fbx)

        self.log(f"--- Starting Unpack of {os.path.basename(phyre_in)} ---")
        
        # Step 1: Phyre -> Temp FBX. Use -r flag to auto-unpack textures references.
        self.log("Step 1: Unpacking Phyre to FBX using FFXIIConvert...")
        ret = self.run_cmd([self.ffxii_convert_path, "unpack", phyre_in, temp_fbx, "-r"])
        if ret != 0 or not os.path.exists(temp_fbx):
            self.log("Error: Unpack to FBX failed.")
            return False

        # Step 2: Temp FBX -> glTF
        self.log("Step 2: Converting FBX to glTF using Noesis...")
        ret = self.run_cmd([self.noesis_path, "?cmode", temp_fbx, out_model])
        if ret != 0 or not os.path.exists(out_model):
            self.log("Error: Convert to glTF failed.")
            if os.path.exists(temp_fbx):
                os.remove(temp_fbx)
            return False

        # Step 3: Clean up temp FBX
        if os.path.exists(temp_fbx):
            os.remove(temp_fbx)

        self.log("--- Unpack Successful ---")
        return True

    def pack(self, orig_phyre, ref_model_in, phyre_out):
        if not os.path.exists(self.ffxii_convert_path):
            msg = f"FFXIIConvert.exe was not found at:\n{self.ffxii_convert_path}\n\nPlease place FFXIIConvert.exe in the 'tools/' directory or configure its path in Settings."
            self.log(msg)
            try:
                messagebox.showerror("Tool Not Found", msg)
            except Exception:
                pass
            return False


        # Detect texture vs model
        is_texture = ref_model_in.lower().endswith('.png') or ref_model_in.lower().endswith('.dds') or orig_phyre.lower().endswith('.dds.phyre')

        if is_texture:
            self.log(f"--- Starting Texture Pack to {os.path.basename(phyre_out)} ---")
            
            pack_input_file = ref_model_in
            temp_dds = None
            
            if ref_model_in.lower().endswith('.png'):
                fmt = get_phyre_texture_format(orig_phyre)
                if fmt:
                    self.log(f"Detected original texture format: {fmt}")
                    if self.dds_encoder == "compressonator" and self.compressonator_path and os.path.exists(self.compressonator_path):
                        # Map format to Compressonator format
                        comp_map = {
                            "DXT1": "BC1",
                            "DXT3": "BC2",
                            "DXT5": "BC3",
                            "BC1": "BC1",
                            "BC2": "BC2",
                            "BC3": "BC3",
                            "BC7": "BC7"
                        }
                        comp_fmt = comp_map.get(fmt, "BC3")
                        self.log(f"Compiling PNG to DDS using Compressonator format: {comp_fmt}...")
                        try:
                            # Create a temporary directory for Compressonator output
                            temp_dir = tempfile.mkdtemp(prefix="ffx_compressonator_")
                            base_name = os.path.splitext(os.path.basename(ref_model_in))[0]
                            temp_dds = os.path.join(temp_dir, base_name + ".dds")
                            
                            ret_conv = self.run_cmd([self.compressonator_path, "-nomipmap", "-fd", comp_fmt, ref_model_in, temp_dds])
                            if ret_conv == 0 and os.path.exists(temp_dds):
                                self.log(f"Successfully compiled PNG to DDS: {temp_dds}")
                                pack_input_file = temp_dds
                            else:
                                self.log("Error: Compressonator failed. Falling back to direct PNG packing.")
                                shutil.rmtree(temp_dir, ignore_errors=True)
                                temp_dir = None
                                temp_dds = None
                        except Exception as e:
                            self.log(f"Error invoking Compressonator: {str(e)}. Falling back to direct PNG packing.")
                            if temp_dir and os.path.exists(temp_dir):
                                shutil.rmtree(temp_dir, ignore_errors=True)
                            temp_dir = None
                            temp_dds = None
                    elif self.texconv_path and os.path.exists(self.texconv_path):
                        # Map format to texconv flags
                        fmt_map = {
                            "DXT1": "BC1_UNORM",
                            "DXT3": "BC2_UNORM",
                            "DXT5": "BC3_UNORM",
                            "BC1": "BC1_UNORM",
                            "BC2": "BC2_UNORM",
                            "BC3": "BC3_UNORM",
                            "BC7": "BC7_UNORM"
                        }
                        texconv_fmt = fmt_map.get(fmt, "BC3_UNORM")
                        self.log(f"Compiling PNG to DDS using texconv format: {texconv_fmt}...")
                        
                        try:
                            # Create a temporary directory for texconv output
                            temp_dir = tempfile.mkdtemp(prefix="ffx_texconv_")
                            cmd = [self.texconv_path, "-f", texconv_fmt]
                            if self.texconv_dither and fmt in ["DXT1", "DXT3", "DXT5", "BC1", "BC2", "BC3"]:
                                cmd.extend(["-bc", "d"])
                            cmd.extend(["-y", "-o", temp_dir, ref_model_in])
                            
                            ret_conv = self.run_cmd(cmd)
                            if ret_conv == 0:
                                base_name = os.path.splitext(os.path.basename(ref_model_in))[0]
                                temp_dds = os.path.join(temp_dir, base_name + ".dds")
                                if os.path.exists(temp_dds):
                                    self.log(f"Successfully compiled PNG to DDS: {temp_dds}")
                                    pack_input_file = temp_dds
                                else:
                                    self.log("Error: texconv reported success, but DDS file was not found. Falling back to PNG packing.")
                                    shutil.rmtree(temp_dir, ignore_errors=True)
                                    temp_dir = None
                                    temp_dds = None
                            else:
                                self.log("Error: texconv failed. Falling back to direct PNG packing.")
                                shutil.rmtree(temp_dir, ignore_errors=True)
                                temp_dir = None
                                temp_dds = None
                        except Exception as e:
                            self.log(f"Error invoking texconv: {str(e)}. Falling back to direct PNG packing.")
                            if temp_dir and os.path.exists(temp_dir):
                                shutil.rmtree(temp_dir, ignore_errors=True)
                            temp_dir = None
                            temp_dds = None
                    else:
                        self.log("Tip: For best results and to avoid visual artifacts (like blotchy gradients in UI/sky textures),\n"
                                 "      consider configuring a DDS encoder (texconv.exe or CompressonatorCLI.exe) in settings\n"
                                 "      to automatically compile PNG to DDS matching the original compression format.\n")
                else:
                    self.log("Tip: Original texture format could not be detected. Packing PNG directly.\n")
                    
            ret = self.run_cmd([self.ffxii_convert_path, "pack", orig_phyre, pack_input_file, phyre_out])
            
            # Clean up temp DDS and temp dir if created
            if temp_dds and os.path.exists(temp_dds):
                try:
                    temp_dir = os.path.dirname(temp_dds)
                    os.remove(temp_dds)
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass
                    
            if ret != 0 or not os.path.exists(phyre_out):
                self.log("Error: Texture packing failed.")
                return False
            self.log("--- Texture Pack Successful ---")
            return True


        # Model pack
        if not os.path.exists(self.noesis_path):
            msg = f"Noesis64.exe was not found at:\n{self.noesis_path}\n\nPlease place Noesis64.exe in the 'tools/' directory or configure its path in Settings."
            self.log(msg)
            try:
                messagebox.showerror("Tool Not Found", msg)
            except Exception:
                pass
            return False


        self.log(f"--- Starting Pack to {os.path.basename(phyre_out)} ---")

        # Handle file types - only glTF is supported
        if not ref_model_in.lower().endswith('.gltf'):
            self.log("Error: Only glTF (.gltf) models are supported for repacking.")
            return False

        temp_fbx = os.path.splitext(ref_model_in)[0] + "_temp.fbx"
        if os.path.exists(temp_fbx):
            os.remove(temp_fbx)
        
        # Step 1: Convert glTF to temp FBX using Noesis
        self.log("Step 1: Converting glTF to FBX using Noesis...")
        ret = self.run_cmd([self.noesis_path, "?cmode", ref_model_in, temp_fbx])
        if ret != 0 or not os.path.exists(temp_fbx):
            self.log("Error: glTF to FBX conversion failed.")
            return False
        
        # Step 2: Pack FBX back into Phyre
        self.log("Step 2: Packing FBX into Phyre using FFXIIConvert...")
        ret = self.run_cmd([self.ffxii_convert_path, "pack", orig_phyre, temp_fbx, phyre_out])

        # Clean up temp FBX
        if os.path.exists(temp_fbx):
            os.remove(temp_fbx)

        if ret != 0 or not os.path.exists(phyre_out):
            self.log("Error: Packing to Phyre failed.")
            return False

        self.log("--- Pack Successful ---")
        return True


class PhyreToolGUI:
    def __init__(self, parent, is_embedded=False):
        self.parent = parent
        self.is_embedded = is_embedded
        self.root = parent.winfo_toplevel() if is_embedded else parent
        
        # Dark Theme Palette
        self.bg_color = "#121212"
        self.card_color = "#1e1e1e"
        self.accent_color = "#3b82f6"
        self.accent_hover = "#2563eb"
        self.text_color = "#e5e7eb"
        self.text_dim = "#9ca3af"
        self.border_color = "#374151"
        self.success_color = "#10b981"
        self.error_color = "#ef4444"
        
        if not is_embedded:
            self.root.title("FFX Phyre Tool")
            self.root.geometry("1020x600")
            self.root.minsize(800, 500)
            self.root.configure(bg=self.bg_color)
            
            # Apply TTK styles
            self.style = ttk.Style()
            self.style.theme_use("clam")
            
            self.style.configure(".", background=self.bg_color, foreground=self.text_color)
            self.style.configure("TFrame", background=self.bg_color)
            self.style.configure("TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 10))
            
            # Header Style
            self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), foreground=self.accent_color)
            self.style.configure("SubHeader.TLabel", font=("Segoe UI", 10, "italic"), foreground=self.text_dim)
            
            # Tab Style
            self.style.configure("TNotebook", background=self.bg_color, borderwidth=0)
            self.style.configure("TNotebook.Tab", background=self.card_color, foreground=self.text_dim, 
                                 padding=[15, 5], font=("Segoe UI", 10, "bold"), borderwidth=1, bordercolor=self.border_color)
            self.style.map("TNotebook.Tab", 
                           background=[("selected", self.accent_color), ("active", self.border_color), ("", self.card_color)],
                           foreground=[("selected", "#ffffff"), ("active", self.text_color), ("", self.text_dim)])
            
            # Scrollbar Styling
            self.style.configure("Vertical.TScrollbar", background=self.card_color, troughcolor=self.bg_color, 
                                 bordercolor=self.border_color, arrowcolor=self.accent_color,
                                 lightcolor=self.border_color, darkcolor=self.border_color)
            self.style.map("Vertical.TScrollbar",
                           background=[("active", self.accent_color), ("pressed", self.accent_color), ("", self.card_color)],
                           arrowcolor=[("active", "#ffffff"), ("", self.accent_color)])
            self.style.configure("Horizontal.TScrollbar", background=self.card_color, troughcolor=self.bg_color, 
                                 bordercolor=self.border_color, arrowcolor=self.accent_color,
                                 lightcolor=self.border_color, darkcolor=self.border_color)
            self.style.map("Horizontal.TScrollbar",
                           background=[("active", self.accent_color), ("pressed", self.accent_color), ("", self.card_color)],
                           arrowcolor=[("active", "#ffffff"), ("", self.accent_color)])
            
            # Entry Style
            self.style.configure("TEntry", fieldbackground=self.card_color, foreground=self.text_color, 
                                 bordercolor=self.border_color, lightcolor=self.border_color, darkcolor=self.border_color)
            self.style.configure("TCombobox", fieldbackground=self.card_color, background=self.card_color, 
                                 foreground=self.text_color, arrowcolor=self.accent_color, bordercolor=self.border_color)
            self.style.map("TCombobox",
                           fieldbackground=[("readonly", self.card_color), ("disabled", self.card_color)],
                           foreground=[("readonly", self.text_color), ("disabled", self.text_dim)],
                           background=[("readonly", self.card_color), ("disabled", self.card_color), ("active", self.border_color)],
                           arrowcolor=[("disabled", self.text_dim), ("!disabled", self.accent_color)],
                           bordercolor=[("focus", self.accent_color), ("!focus", self.border_color)])

        # Style the dropdown Listbox popup globally (white background, black text for high visibility on Windows)
        self.root.option_add("*TCombobox*Listbox.background", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.foreground", "#000000")
        self.root.option_add("*TCombobox*Listbox.selectBackground", self.accent_color)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))

        # Safeguard bind to force dropdown Listbox colors (white background, black text) on Windows
        def on_combobox_click(event):
            def configure_listbox(retries=0):
                try:
                    popdown = str(event.widget) + ".popdown"
                    listbox = popdown + ".f.l"
                    if event.widget.tk.call("winfo", "exists", listbox):
                        event.widget.tk.call(
                            listbox, "configure",
                            "-background", "#ffffff",
                            "-foreground", "#000000",
                            "-selectbackground", self.accent_color,
                            "-selectforeground", "#ffffff",
                            "-font", "{Segoe UI} 10"
                        )
                    elif retries < 10:
                        event.widget.after(20, lambda: configure_listbox(retries + 1))
                except Exception:
                    if retries < 10:
                        event.widget.after(20, lambda: configure_listbox(retries + 1))
            event.widget.after(5, configure_listbox)

        self.root.bind_class("TCombobox", "<ButtonPress-1>", on_combobox_click, add="+")
        self.root.bind_class("TCombobox", "<Down>", on_combobox_click, add="+")
        
        # Batch paths lists
        self.selected_unpack_paths = []
        self.selected_pack_paths = []
        self.temp_preview_files = []
        self.current_preview_target = None
        
        # 3D preview variables
        self.model_vertices = []
        self.model_indices = []
        self.model_uvs = []
        self.model_texture_src = None
        self.model_cx = 0
        self.model_cy = 0
        self.model_cz = 0
        self.model_scale = 1.0
        self.model_yaw = 0.0
        self.model_pitch = 0.0
        self.active_canvas = None
        self.fs_window = None
        self.fs_canvas = None

        
        # Load recent files config
        self.load_config()

        # Setup UI
        self.create_widgets()

        # Setup Menu Bar for File and Recent Files
        if not self.is_embedded:
            self.menu_bar = tk.Menu(self.root)
            
            # File Menu
            self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
            self.menu_bar.add_cascade(label="File", menu=self.file_menu)
            self.file_menu.add_command(label="Settings", command=self.open_settings_dialog)
            self.file_menu.add_separator()
            self.file_menu.add_command(label="Exit", command=self.on_app_close)
            
            self.recent_menu = tk.Menu(self.menu_bar, tearoff=0)
            self.menu_bar.add_cascade(label="Recent Files", menu=self.recent_menu)
            
            self.root.config(menu=self.menu_bar)
            self.update_recent_menu()




        # Bind app close cleanup
        if not self.is_embedded:
            self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
            self.root.after(500, self.check_tools_on_startup)


    def load_config(self):
        self.recent_files = []
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.recent_files = config.get("recent_files", [])
            except Exception:
                pass

    def save_config(self):
        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
            except Exception:
                pass
        config["recent_files"] = self.recent_files
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def add_recent_file(self, path):
        if not path:
            return
        path = os.path.abspath(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:10]  # keep top 10
        self.save_config()
        self.update_recent_menu()

    def update_recent_menu(self):
        if self.is_embedded:
            return
        def update():
            self.recent_menu.delete(0, tk.END)
            if not self.recent_files:
                self.recent_menu.add_command(label="No recent files", state="disabled")
                return
            for path in self.recent_files:
                filename = os.path.basename(path)
                self.recent_menu.add_command(label=f"{filename} ({os.path.dirname(path)})", 
                                             command=lambda p=path: self.load_recent_file(p))
        self.root.after(0, update)


    def load_recent_file(self, path):
        if path.lower().endswith('.phyre'):
            self.selected_unpack_paths = [path]
            self.unpack_phyre_in.set(path)
            self.notebook.select(0)  # switch to unpack tab
        elif path.lower().endswith(('.gltf', '.png')):
            self.selected_pack_paths = [path]
            self.pack_model_in.set(path)
            self.notebook.select(1)  # switch to pack tab

    def create_widgets(self):
        # Top Title and Settings button
        title_frame = ttk.Frame(self.parent, padding=15)
        title_frame.pack(fill="x")
        
        # Left side title/subtitle
        text_frame = ttk.Frame(title_frame)
        text_frame.pack(side="left", fill="both", expand=True)
        
        lbl_title = ttk.Label(text_frame, text="FFX PHYRE TOOL", style="Header.TLabel")
        lbl_title.pack(anchor="w")
        
        lbl_subtitle = ttk.Label(text_frame, text="Extract & Repack PhyreEngine models and textures for Final Fantasy X/X-2 HD | Created by NfgOdin", style="SubHeader.TLabel")
        lbl_subtitle.pack(anchor="w")




        # Main horizontal container
        main_container = ttk.Frame(self.parent)
        main_container.pack(fill="both", expand=True)

        # Right Frame (Sidebar) for Preview & Tips
        right_frame = tk.Frame(main_container, bg=self.card_color, width=220, bd=1, relief="flat")
        right_frame.pack(side="right", fill="y", padx=(0, 10), pady=10)
        right_frame.pack_propagate(False)

        # Asset Preview Section
        lbl_preview_title = tk.Label(right_frame, text="ASSET PREVIEW", bg=self.card_color, fg=self.accent_color,
                                     font=("Segoe UI", 9, "bold"))
        lbl_preview_title.pack(anchor="n", pady=(10, 5))
        
        self.lbl_thumbnail = tk.Label(right_frame, text="[No Preview]", bg="#0d0d0d", fg=self.text_dim,
                                      width=20, height=8, relief="solid", bd=1)
        self.lbl_thumbnail.pack(anchor="n", pady=5, padx=10, fill="x")
        
        # 3D Canvas Preview (initially hidden)
        self.canvas_preview = tk.Canvas(right_frame, bg="#0d0d0d", highlightthickness=1, 
                                        highlightbackground=self.border_color, width=190, height=130)
        self.canvas_preview.bind("<Button-1>", self.on_canvas_drag_start)
        self.canvas_preview.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas_preview.bind("<MouseWheel>", self.on_canvas_zoom)
        self.canvas_preview.bind("<Double-Button-1>", lambda e: self.preview_model())
        self.active_canvas = self.canvas_preview

        self.lbl_thumbnail_name = tk.Label(right_frame, text="", bg=self.card_color, fg=self.text_dim,
                                           font=("Segoe UI", 8, "italic"), wrap=200)
        self.lbl_thumbnail_name.pack(anchor="n", pady=(0, 10))
        
        # Actions section
        lbl_actions = tk.Label(right_frame, text="QUICK ACTIONS", bg=self.card_color, fg=self.accent_color,
                               font=("Segoe UI", 9, "bold"))
        lbl_actions.pack(anchor="n", pady=(10, 5))
        
        self.btn_fullscreen = tk.Button(right_frame, text="💻 Fullscreen View", state="disabled", command=self.enter_fullscreen,
                                        bg=self.card_color, fg=self.text_dim, relief="flat", bd=1,
                                        activebackground=self.border_color, activeforeground=self.text_color)
        self.btn_fullscreen.pack(fill="x", padx=20, pady=5)
        self.bind_hover(self.btn_fullscreen)

        self.btn_open_folder = tk.Button(right_frame, text="Open Folder", state="disabled", command=self.open_output_folder,
                                         bg=self.card_color, fg=self.text_dim, relief="flat", bd=1,
                                         activebackground=self.border_color, activeforeground=self.text_color)
        self.btn_open_folder.pack(fill="x", padx=20, pady=5)
        self.bind_hover(self.btn_open_folder)

        # Render Mode Section
        lbl_render_mode = tk.Label(right_frame, text="RENDER MODE", bg=self.card_color, fg=self.accent_color,
                                   font=("Segoe UI", 9, "bold"))
        lbl_render_mode.pack(anchor="n", pady=(15, 5))
        
        self.render_mode_var = tk.StringVar(value="Textured")
        self.cmb_render_mode = ttk.Combobox(right_frame, textvariable=self.render_mode_var,
                                            values=["Wireframe", "Flat Shaded", "Textured"], state="readonly", width=18)
        self.cmb_render_mode.pack(anchor="n", pady=5)
        self.cmb_render_mode.bind("<<ComboboxSelected>>", lambda e: self.draw_3d_wireframe())
        
        # Modding Tips Section
        lbl_tips_title = tk.Label(right_frame, text="MODDING TIPS", bg=self.card_color, fg=self.accent_color,
                                  font=("Segoe UI", 9, "bold"))
        lbl_tips_title.pack(anchor="n", pady=(20, 5))
        
        tips_text = (
            "• Use glTF Separate (.gltf) format in Blender.\n"
            "• Rig custom meshes to original bones.\n"
            "• Hold Ctrl to select multiple files for batch processing.\n"
            "• Original model textures are auto-extracted with the model."
        )
        lbl_tips = tk.Label(right_frame, text=tips_text, bg=self.card_color, fg=self.text_dim,
                            font=("Segoe UI", 8), justify="left", wrap=180)
        lbl_tips.pack(anchor="n", padx=10, pady=5)

        # Left Frame for Notebook and Logs
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side="left", fill="both", expand=True)

        # Tabs Container
        notebook = ttk.Notebook(left_frame)
        notebook.pack(fill="both", expand=True, padx=15, pady=5)
        self.notebook = notebook
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)


        # TAB 1: UNPACK
        tab_unpack = ttk.Frame(notebook, padding=15)
        notebook.add(tab_unpack, text="Extract Phyre")
        self.setup_unpack_tab(tab_unpack)

        # TAB 2: PACK
        tab_pack = ttk.Frame(notebook, padding=15)
        notebook.add(tab_pack, text="Repack Phyre")
        self.setup_pack_tab(tab_pack)

        if not self.is_embedded:
            # Bottom Log Frame inside left_frame
            log_frame = ttk.Frame(left_frame, padding=10)
            log_frame.pack(fill="both", expand=True, side="bottom")
            
            lbl_log = ttk.Label(log_frame, text="Process Execution Logs:", font=("Segoe UI", 9, "bold"))
            lbl_log.pack(anchor="w", pady=2)
            
            self.txt_log = tk.Text(log_frame, height=5, bg="#0d0d0d", fg="#e5e7eb", insertbackground="white", 
                                   font=("Consolas", 9), wrap="word", relief="flat", highlightthickness=1,
                                   highlightbackground=self.border_color)
            self.txt_log.pack(fill="both", expand=True, side="left")
            
            # Log Console Tags for rich colored log outputs
            self.txt_log.tag_config("success", foreground=self.success_color, font=("Consolas", 9, "bold"))
            self.txt_log.tag_config("error", foreground=self.error_color, font=("Consolas", 9, "bold"))
            self.txt_log.tag_config("info", foreground=self.accent_color, font=("Consolas", 9, "bold"))
            self.txt_log.tag_config("default", foreground="#e5e7eb")
            
            scrollbar = ttk.Scrollbar(log_frame, command=self.txt_log.yview)
            scrollbar.pack(fill="y", side="right")
            self.txt_log.config(yscrollcommand=scrollbar.set)
        else:
            self.txt_log = None

        # Status Bar at bottom of screen
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = tk.Label(self.parent, textvariable=self.status_var, bg="#1e1e1e", fg=self.text_dim,
                                   font=("Segoe UI", 9, "bold"), anchor="w", padx=10, pady=4)
        self.status_bar.pack(fill="x", side="bottom")

    def show_open_folder_btn(self, directory):
        self.output_dir = directory
        def enable():
            self.btn_open_folder.config(state="normal", bg=self.accent_color, fg="white")
        self.root.after(0, enable)

    def open_output_folder(self):
        if hasattr(self, 'output_dir') and os.path.exists(self.output_dir):
            os.startfile(self.output_dir)

    def show_preview(self, png_path):
        def update_ui():
            try:
                # Load image
                img = tk.PhotoImage(file=png_path)
                
                # Simple downscale using subsample to fit in sidebar without Pillow
                w = img.width()
                h = img.height()
                
                max_size = 150
                factor = 1
                if w > max_size or h > max_size:
                    factor = max(w // max_size, h // max_size)
                
                if factor > 1:
                    img = img.subsample(factor)
                
                self.thumbnail_image = img
                self.lbl_thumbnail.config(image=self.thumbnail_image, text="", width=0, height=0)
                self.lbl_thumbnail_name.config(text=os.path.basename(png_path))
            except Exception:
                self.clear_preview()
        self.root.after(0, update_ui)

    def clear_preview(self):
        def update():
            self.thumbnail_image = None
            self.canvas_bg_image = None
            self.model_texture_np = None
            self.lbl_thumbnail.config(image="", text="[No Preview]", width=20, height=8)
            self.lbl_thumbnail_name.config(text="")
            self.canvas_preview.delete("all")
            self.canvas_preview.pack_forget()
            self.lbl_thumbnail.pack(anchor="n", pady=5, padx=10, fill="x")
        self.root.after(0, update)

    def on_canvas_drag_start(self, event):
        self.canvas_drag_last_x = event.x
        self.canvas_drag_last_y = event.y
        
    def on_canvas_drag(self, event):
        if not hasattr(self, 'canvas_drag_last_x'):
            return
        dx = event.x - self.canvas_drag_last_x
        dy = event.y - self.canvas_drag_last_y
        
        self.model_yaw += dx * 0.015
        self.model_pitch += dy * 0.015
        
        self.canvas_drag_last_x = event.x
        self.canvas_drag_last_y = event.y
        
        self.draw_3d_wireframe()

    def draw_3d_wireframe(self):
        canvas = getattr(self, 'active_canvas', self.canvas_preview)
        if not canvas:
            canvas = self.canvas_preview
        canvas.delete("all")
        
        w = canvas.winfo_width() or 190
        h = canvas.winfo_height() or 130
        
        # Create base image
        img = np.zeros((h, w, 3), dtype=np.uint8)
            
        if len(self.model_vertices) == 0 or len(self.model_indices) == 0:
            # Convert to PhotoImage and draw
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            self.canvas_bg_image = ImageTk.PhotoImage(image=pil_img)
            canvas.create_image(w/2, h/2, anchor="center", image=self.canvas_bg_image)
            return
            
        cos_y, sin_y = math.cos(self.model_yaw), math.sin(self.model_yaw)
        cos_p, sin_p = math.cos(self.model_pitch), math.sin(self.model_pitch)
        
        scale_multiplier = 1.0
        if canvas != self.canvas_preview:
            scale_multiplier = min(w / 190.0, h / 130.0) * 0.85
            
        scale_val = self.model_scale * scale_multiplier
        
        # Vectorized 3D projection using NumPy
        centered = self.model_vertices - np.array([self.model_cx, self.model_cy, self.model_cz], dtype=np.float32)
        
        # Yaw rotation
        x1 = centered[:, 0] * cos_y - centered[:, 2] * sin_y
        z1 = centered[:, 0] * sin_y + centered[:, 2] * cos_y
        
        # Pitch rotation
        y2 = centered[:, 1] * cos_p - z1 * sin_p
        z2 = centered[:, 1] * sin_p + z1 * cos_p
        
        # Screen projection coordinates
        sx = (w / 2 + x1 * scale_val).astype(np.int32)
        sy = (h / 2 - y2 * scale_val).astype(np.int32)
        
        proj_verts = np.column_stack((sx, sy))
        
        # Check render mode
        mode = self.render_mode_var.get() if hasattr(self, 'render_mode_var') else "Textured"
        
        # Fallback to Flat Shaded if Textured is selected but no texture is available or no UVs
        if mode == "Textured" and (self.model_texture_src is None or len(self.model_uvs) == 0):
            mode = "Flat Shaded"
            
        if mode == "Wireframe":
            # Draw original background if available
            if hasattr(self, 'model_texture_np') and self.model_texture_np is not None:
                img = self.model_texture_np.copy()
            # Reshape indices to triangles: shape (N, 3, 2)
            triangles = proj_verts[self.model_indices].reshape(-1, 3, 2)
            cv2.polylines(img, triangles, isClosed=True, color=(246, 130, 59), thickness=1, lineType=cv2.LINE_AA)
            
        elif mode == "Flat Shaded":
            num_tri = len(self.model_indices) // 3
            tri_idx = self.model_indices[:num_tri * 3].reshape(-1, 3)
            
            # 2D Screen Vertices of Triangles
            tri_verts_2d = proj_verts[tri_idx] # [T, 3, 2]
            
            # Backface Culling
            p0 = tri_verts_2d[:, 0]
            p1 = tri_verts_2d[:, 1]
            p2 = tri_verts_2d[:, 2]
            cross = (p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0])
            
            visible_mask = cross > 0
            visible_indices = np.where(visible_mask)[0]
            
            if len(visible_indices) > 0:
                # Depth Sorting (Painter's algorithm)
                depth = z2[tri_idx].mean(axis=1)
                visible_depths = depth[visible_indices]
                sort_order = np.argsort(-visible_depths)
                sorted_triangles = visible_indices[sort_order]
                
                # Face Normal & Lighting in Camera Space (headlight pointing at +Z)
                rot_3d = np.column_stack((x1, y2, z2))
                v0_rot = rot_3d[tri_idx[:, 0]]
                v1_rot = rot_3d[tri_idx[:, 1]]
                v2_rot = rot_3d[tri_idx[:, 2]]
                
                normals = np.cross(v1_rot - v0_rot, v2_rot - v0_rot)
                len_n = np.linalg.norm(normals, axis=1)
                len_n[len_n == 0] = 1.0
                intensity = normals[:, 2] / len_n
                intensity = 0.2 + 0.8 * np.clip(intensity, 0.0, 1.0)
                
                for t in sorted_triangles:
                    pts = tri_verts_2d[t].astype(np.int32)
                    shade = intensity[t]
                    # Blue accent flat shading (BGR format)
                    color = (int(246 * shade), int(130 * shade), int(59 * shade))
                    cv2.fillConvexPoly(img, pts, color)
                    
        elif mode == "Textured":
            num_tri = len(self.model_indices) // 3
            tri_idx = self.model_indices[:num_tri * 3].reshape(-1, 3)
            
            # 2D Screen Vertices of Triangles
            tri_verts_2d = proj_verts[tri_idx] # [T, 3, 2]
            
            # Backface Culling
            p0 = tri_verts_2d[:, 0]
            p1 = tri_verts_2d[:, 1]
            p2 = tri_verts_2d[:, 2]
            cross = (p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0])
            
            visible_mask = cross > 0
            visible_indices = np.where(visible_mask)[0]
            
            if len(visible_indices) > 0:
                # Depth Sorting (Painter's algorithm)
                depth = z2[tri_idx].mean(axis=1)
                visible_depths = depth[visible_indices]
                sort_order = np.argsort(-visible_depths)
                sorted_triangles = visible_indices[sort_order]
                
                # Texture map vertices coordinates
                tex_h, tex_w = self.model_texture_src.shape[:2]
                tex_coords = self.model_uvs * np.array([tex_w - 1, tex_h - 1], dtype=np.float32)
                tex_verts = tex_coords[tri_idx]
                
                for t in sorted_triangles:
                    tri_dst = tri_verts_2d[t].astype(np.float32)
                    tri_src = tex_verts[t].astype(np.float32)
                    warp_triangle(self.model_texture_src, img, tri_src, tri_dst)
        
        # Convert BGR to RGB, then to Tk PhotoImage
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(img_rgb)
        self.canvas_bg_image = ImageTk.PhotoImage(image=pil_img)
        canvas = getattr(self, 'active_canvas', self.canvas_preview) or self.canvas_preview
        canvas.create_image(w/2, h/2, anchor="center", image=self.canvas_bg_image)


    def load_3d_model_for_preview(self, gltf_path):
        try:
            with open(gltf_path, 'r') as f:
                gltf = json.load(f)
            
            buffers = []
            base_dir = os.path.dirname(gltf_path)
            for b in gltf.get('buffers', []):
                uri = b.get('uri')
                buf_path = os.path.join(base_dir, uri)
                if os.path.exists(buf_path):
                    with open(buf_path, 'rb') as f_bin:
                        buffers.append(f_bin.read())
                else:
                    buffers.append(b"")
                    
            accessors = gltf.get('accessors', [])
            buffer_views = gltf.get('bufferViews', [])
            
            vertices = []
            indices = []
            uvs = []
            vertex_offset = 0
            
            for mesh in gltf.get('meshes', []):
                for primitive in mesh.get('primitives', []):
                    attribs = primitive.get('attributes', {})
                    pos_acc_idx = attribs.get('POSITION')
                    ind_acc_idx = primitive.get('indices')
                    uv_acc_idx = attribs.get('TEXCOORD_0')
                    
                    local_vertices = []
                    if pos_acc_idx is not None:
                        acc = accessors[pos_acc_idx]
                        bv = buffer_views[acc.get('bufferView')]
                        buf_idx = bv.get('buffer')
                        if buf_idx < len(buffers):
                            data = buffers[buf_idx]
                            byte_offset = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
                            count = acc.get('count')
                            comp_type = acc.get('componentType')
                            if comp_type == 5126: # Float
                                stride = bv.get('byteStride', 12)
                                for i in range(count):
                                    offset = byte_offset + i * stride
                                    x, y, z = struct.unpack_from('<fff', data, offset)
                                    local_vertices.append([x, y, z])
                                    vertices.append([x, y, z])
                    
                    if ind_acc_idx is not None:
                        acc = accessors[ind_acc_idx]
                        bv = buffer_views[acc.get('bufferView')]
                        buf_idx = bv.get('buffer')
                        if buf_idx < len(buffers):
                            data = buffers[buf_idx]
                            byte_offset = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
                            count = acc.get('count')
                            comp_type = acc.get('componentType')
                            if comp_type == 5123: # unsigned short
                                stride = bv.get('byteStride', 2)
                                for i in range(count):
                                    offset = byte_offset + i * stride
                                    idx = struct.unpack_from('<H', data, offset)[0]
                                    indices.append(vertex_offset + idx)
                            elif comp_type == 5125: # unsigned int
                                stride = bv.get('byteStride', 4)
                                for i in range(count):
                                    offset = byte_offset + i * stride
                                    idx = struct.unpack_from('<I', data, offset)[0]
                                    indices.append(vertex_offset + idx)
                    else:
                        indices.extend(range(vertex_offset, vertex_offset + len(local_vertices)))
                        
                    # Load UV coordinates
                    local_uvs = []
                    if uv_acc_idx is not None:
                        acc_uv = accessors[uv_acc_idx]
                        bv_uv = buffer_views[acc_uv.get('bufferView')]
                        buf_idx_uv = bv_uv.get('buffer')
                        if buf_idx_uv < len(buffers):
                            data_uv = buffers[buf_idx_uv]
                            byte_offset_uv = bv_uv.get('byteOffset', 0) + acc_uv.get('byteOffset', 0)
                            count_uv = acc_uv.get('count')
                            comp_type_uv = acc_uv.get('componentType')
                            if comp_type_uv == 5126: # Float
                                stride_uv = bv_uv.get('byteStride', 8)
                                for i in range(count_uv):
                                    offset_uv = byte_offset_uv + i * stride_uv
                                    u, v = struct.unpack_from('<ff', data_uv, offset_uv)
                                    local_uvs.append([u, v])
                                    
                    # Pad if count doesn't match
                    if len(local_uvs) < len(local_vertices):
                        needed = len(local_vertices) - len(local_uvs)
                        for _ in range(needed):
                            local_uvs.append([0.0, 0.0])
                    elif len(local_uvs) > len(local_vertices):
                        local_uvs = local_uvs[:len(local_vertices)]
                        
                    uvs.extend(local_uvs)
                    vertex_offset += len(local_vertices)
            
            # Save mesh data as NumPy arrays
            self.model_vertices = np.array(vertices, dtype=np.float32)
            self.model_indices = np.array(indices, dtype=np.int32)
            self.model_uvs = np.array(uvs, dtype=np.float32)
            
            # Load texture referenced by glTF
            self.model_texture_src = None
            images_list = gltf.get('images', [])
            if images_list:
                uri = images_list[0].get('uri')
                if uri:
                    tex_path = os.path.join(base_dir, uri)
                    if os.path.exists(tex_path):
                        self.model_texture_src = cv2.imread(tex_path)
            
            # Fallback search for any PNG in directory
            if self.model_texture_src is None:
                for f_name in os.listdir(base_dir):
                    if f_name.lower().endswith('.png'):
                        tex_path = os.path.join(base_dir, f_name)
                        self.model_texture_src = cv2.imread(tex_path)
                        if self.model_texture_src is not None:
                            break
            
            # Find bounds and center
            if len(self.model_vertices) > 0:
                xs = self.model_vertices[:, 0]
                ys = self.model_vertices[:, 1]
                zs = self.model_vertices[:, 2]
                min_x, max_x = xs.min(), xs.max()
                min_y, max_y = ys.min(), ys.max()
                min_z, max_z = zs.min(), zs.max()
                
                self.model_cx = (min_x + max_x) / 2
                self.model_cy = (min_y + max_y) / 2
                self.model_cz = (min_z + max_z) / 2
                
                max_range = max(max_x - min_x, max_y - min_y, max_z - min_z)
                self.model_scale = 55.0 / max_range if max_range > 0 else 1.0
            else:
                self.model_cx = self.model_cy = self.model_cz = 0
                self.model_scale = 1.0
                
            self.model_yaw = -0.5
            self.model_pitch = -0.3
            
            # Display canvas
            def update_ui():
                self.lbl_thumbnail.pack_forget()
                self.canvas_preview.pack(anchor="n", pady=5, padx=10, fill="x")
                self.lbl_thumbnail_name.config(text=os.path.basename(gltf_path))
                self.draw_3d_wireframe()
            self.root.after(0, update_ui)
        except Exception as e:
            self.clear_preview()
            self.log_text(f"Error loading 3D preview model: {str(e)}\n", "error")

    def on_canvas_zoom(self, event):
        if len(self.model_vertices) == 0:
            return
        if event.delta > 0:
            self.model_scale *= 1.15
        else:
            self.model_scale /= 1.15
        self.model_scale = max(0.005, min(self.model_scale, 5000.0))
        self.draw_3d_wireframe()

    def enter_fullscreen(self):
        if len(self.model_vertices) == 0:
            return
        self.fs_window = tk.Toplevel(self.root)
        self.fs_window.title("3D Viewport - Fullscreen")
        self.fs_window.attributes("-fullscreen", True)
        self.fs_window.configure(bg="#0d0d0d")
        
        self.fs_canvas = tk.Canvas(self.fs_window, bg="#0d0d0d", highlightthickness=0)
        self.fs_canvas.pack(fill="both", expand=True)
        
        self.fs_canvas.bind("<Button-1>", self.on_canvas_drag_start)
        self.fs_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.fs_canvas.bind("<MouseWheel>", self.on_canvas_zoom)
        self.fs_canvas.bind("<Double-Button-1>", lambda e: self.preview_model())
        self.fs_window.bind("<Escape>", lambda e: self.exit_fullscreen())
        
        btn_exit = tk.Button(self.fs_window, text="Exit Fullscreen [Esc]", command=self.exit_fullscreen,
                             bg=self.error_color, fg="white", relief="flat", bd=0, padx=15, pady=8,
                             font=("Segoe UI", 10, "bold"), activebackground="#dc2626", activeforeground="white")
        btn_exit.place(relx=0.98, rely=0.02, anchor="ne")
        
        self.active_canvas = self.fs_canvas
        self.fs_window.update_idletasks()
        self.draw_3d_wireframe()

    def exit_fullscreen(self):
        if hasattr(self, 'fs_window') and self.fs_window:
            self.fs_window.destroy()
            self.fs_window = None
            self.fs_canvas = None
        self.active_canvas = self.canvas_preview
        self.draw_3d_wireframe()


    def load_3d_texture_background(self, png_path):
        try:
            tex_img = cv2.imread(png_path)
            if tex_img is not None:
                # Dim the texture to make the wireframe lines pop (multiply by 0.35)
                tex_img = cv2.resize(tex_img, (190, 130))
                self.model_texture_np = (tex_img * 0.35).astype(np.uint8)
            else:
                self.model_texture_np = None
        except Exception:
            self.model_texture_np = None

    def on_tab_changed(self, event):

        self.clear_preview()
        if hasattr(self, 'btn_fullscreen'):
            self.btn_fullscreen.config(state="disabled", bg=self.card_color, fg=self.text_dim)
        try:
            selected_tab = self.notebook.index(self.notebook.select())
            if selected_tab == 0:  # Extract Phyre tab
                self.on_unpack_in_changed()
            elif selected_tab == 1:  # Repack Phyre tab
                self.on_pack_model_changed()
        except Exception:
            pass

    def on_app_close(self):

        for f in getattr(self, 'temp_preview_files', []):
            try:
                if os.path.isdir(f):
                    shutil.rmtree(f, ignore_errors=True)
                elif os.path.isfile(f):
                    os.remove(f)
            except Exception:
                pass
        self.root.destroy()
    def check_tools_on_startup(self):
        backend = PhyreToolBackend()
        missing = []
        if not os.path.exists(backend.ffxii_convert_path):
            missing.append("FFXIIConvert.exe")
        if not os.path.exists(backend.noesis_path):
            missing.append("Noesis64.exe")
        if backend.dds_encoder == "compressonator":
            if not os.path.exists(backend.compressonator_path):
                missing.append("CompressonatorCLI.exe")
        else:
            if not os.path.exists(backend.texconv_path):
                missing.append("texconv.exe")
            
        if missing:
            msg = (
                f"The following required external tools were not found:\n"
                f"• {', '.join(missing)}\n\n"
                f"Please place them in the 'tools/' folder next to this application,\n"
                f"or configure their directory locations in the Settings menu (File -> Settings)."
            )
            messagebox.showwarning("Tools Missing", msg)

    def open_settings_dialog(self):
        # Create dialog styled to match our dark theme
        dialog = tk.Toplevel(self.root)
        dialog.title("Settings")
        dialog.geometry("570x420")
        dialog.resizable(False, False)
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Style variables
        val_convert = tk.StringVar()
        val_noesis = tk.StringVar()
        val_texconv = tk.StringVar()
        val_compressonator = tk.StringVar()
        val_encoder = tk.StringVar()
        val_dither = tk.BooleanVar()
        
        # Load current config
        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
            except Exception:
                pass
                
        val_convert.set(config.get("ffxii_convert_path") or DEFAULT_FFXII_CONVERT)
        val_noesis.set(config.get("noesis_path") or DEFAULT_NOESIS)
        val_texconv.set(config.get("texconv_path") or DEFAULT_TEXCONV)
        val_compressonator.set(config.get("compressonator_path") or DEFAULT_COMPRESSONATOR)
        val_encoder.set(config.get("dds_encoder", "texconv"))
        val_dither.set(config.get("texconv_dither", False))
        
        # Create Notebook container inside Settings window for extensibility
        settings_notebook = ttk.Notebook(dialog)
        settings_notebook.pack(fill="both", expand=True, padx=15, pady=(15, 10))
        
        # Tab 1: Path Configuration
        tab_paths = ttk.Frame(settings_notebook, padding=10)
        settings_notebook.add(tab_paths, text=" Path Configuration ")
        
        # Grid container inside Tab 1
        grid_frame = tk.Frame(tab_paths, bg=self.bg_color)
        grid_frame.pack(fill="both", expand=True, pady=5)
        
        # Path validation helper
        def validate_path(var, lbl):
            p = var.get().strip()
            if p and os.path.exists(p) and os.path.isfile(p):
                lbl.config(text="✓", fg=self.success_color)
            else:
                lbl.config(text="✗", fg=self.error_color)

        # Row 1: FFXIIConvert.exe
        lbl_c = tk.Label(grid_frame, text="FFXIIConvert.exe:", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9))
        lbl_c.grid(row=0, column=0, sticky="w", pady=5)
        ent_c = tk.Entry(grid_frame, textvariable=val_convert, bg=self.card_color, fg=self.text_color, insertbackground="white", bd=0, highlightthickness=1, highlightbackground=self.border_color, highlightcolor=self.accent_color, font=("Segoe UI", 9), width=42)
        ent_c.grid(row=0, column=1, padx=5, pady=5)
        lbl_status_c = tk.Label(grid_frame, bg=self.bg_color, font=("Segoe UI", 11, "bold"))
        lbl_status_c.grid(row=0, column=2, padx=5, pady=5)
        
        def browse_convert():
            p = filedialog.askopenfilename(title="Select FFXIIConvert.exe", filetypes=[("Executable Files", "*.exe")])
            if p: val_convert.set(p)
        btn_c = tk.Button(grid_frame, text="Browse...", command=browse_convert, bg=self.card_color, fg=self.text_color, relief="flat", activebackground=self.border_color, activeforeground=self.text_color, font=("Segoe UI", 9))
        btn_c.grid(row=0, column=3, padx=5, pady=5)
        self.bind_hover(btn_c)
        
        # Row 2: Noesis64.exe
        lbl_n = tk.Label(grid_frame, text="Noesis64.exe:", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9))
        lbl_n.grid(row=1, column=0, sticky="w", pady=5)
        ent_n = tk.Entry(grid_frame, textvariable=val_noesis, bg=self.card_color, fg=self.text_color, insertbackground="white", bd=0, highlightthickness=1, highlightbackground=self.border_color, highlightcolor=self.accent_color, font=("Segoe UI", 9), width=42)
        ent_n.grid(row=1, column=1, padx=5, pady=5)
        lbl_status_n = tk.Label(grid_frame, bg=self.bg_color, font=("Segoe UI", 11, "bold"))
        lbl_status_n.grid(row=1, column=2, padx=5, pady=5)
        
        def browse_noesis():
            p = filedialog.askopenfilename(title="Select Noesis64.exe", filetypes=[("Executable Files", "*.exe")])
            if p: val_noesis.set(p)
        btn_n = tk.Button(grid_frame, text="Browse...", command=browse_noesis, bg=self.card_color, fg=self.text_color, relief="flat", activebackground=self.border_color, activeforeground=self.text_color, font=("Segoe UI", 9))
        btn_n.grid(row=1, column=3, padx=5, pady=5)
        self.bind_hover(btn_n)
        
        # Row 3: texconv.exe
        lbl_t = tk.Label(grid_frame, text="texconv.exe:", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9))
        lbl_t.grid(row=2, column=0, sticky="w", pady=5)
        ent_t = tk.Entry(grid_frame, textvariable=val_texconv, bg=self.card_color, fg=self.text_color, insertbackground="white", bd=0, highlightthickness=1, highlightbackground=self.border_color, highlightcolor=self.accent_color, font=("Segoe UI", 9), width=42)
        ent_t.grid(row=2, column=1, padx=5, pady=5)
        lbl_status_t = tk.Label(grid_frame, bg=self.bg_color, font=("Segoe UI", 11, "bold"))
        lbl_status_t.grid(row=2, column=2, padx=5, pady=5)
        
        def browse_texconv():
            p = filedialog.askopenfilename(title="Select texconv.exe", filetypes=[("Executable Files", "*.exe")])
            if p: val_texconv.set(p)
        btn_t = tk.Button(grid_frame, text="Browse...", command=browse_texconv, bg=self.card_color, fg=self.text_color, relief="flat", activebackground=self.border_color, activeforeground=self.text_color, font=("Segoe UI", 9))
        btn_t.grid(row=2, column=3, padx=5, pady=5)
        self.bind_hover(btn_t)
        
        # Row 4: CompressonatorCLI.exe
        lbl_p = tk.Label(grid_frame, text="CompressonatorCLI.exe:", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9))
        lbl_p.grid(row=3, column=0, sticky="w", pady=5)
        ent_p = tk.Entry(grid_frame, textvariable=val_compressonator, bg=self.card_color, fg=self.text_color, insertbackground="white", bd=0, highlightthickness=1, highlightbackground=self.border_color, highlightcolor=self.accent_color, font=("Segoe UI", 9), width=42)
        ent_p.grid(row=3, column=1, padx=5, pady=5)
        lbl_status_p = tk.Label(grid_frame, bg=self.bg_color, font=("Segoe UI", 11, "bold"))
        lbl_status_p.grid(row=3, column=2, padx=5, pady=5)
        
        def browse_compressonator():
            p = filedialog.askopenfilename(title="Select CompressonatorCLI.exe", filetypes=[("Executable Files", "*.exe")])
            if p: val_compressonator.set(p)
        btn_p = tk.Button(grid_frame, text="Browse...", command=browse_compressonator, bg=self.card_color, fg=self.text_color, relief="flat", activebackground=self.border_color, activeforeground=self.text_color, font=("Segoe UI", 9))
        btn_p.grid(row=3, column=3, padx=5, pady=5)
        self.bind_hover(btn_p)
        
        # Bind traces for real-time verification updates
        val_convert.trace_add("write", lambda *a: validate_path(val_convert, lbl_status_c))
        val_noesis.trace_add("write", lambda *a: validate_path(val_noesis, lbl_status_n))
        val_texconv.trace_add("write", lambda *a: validate_path(val_texconv, lbl_status_t))
        val_compressonator.trace_add("write", lambda *a: validate_path(val_compressonator, lbl_status_p))
        
        # Initial validation check on dialog load
        validate_path(val_convert, lbl_status_c)
        validate_path(val_noesis, lbl_status_n)
        validate_path(val_texconv, lbl_status_t)
        validate_path(val_compressonator, lbl_status_p)
        
        # Row 5: DDS Encoder
        lbl_e = tk.Label(grid_frame, text="DDS Encoder:", bg=self.bg_color, fg=self.text_color, font=("Segoe UI", 9))
        lbl_e.grid(row=4, column=0, sticky="w", pady=5)
        cmb_e = ttk.Combobox(grid_frame, textvariable=val_encoder, values=["texconv", "compressonator"], state="readonly", width=15)
        cmb_e.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        
        # Row 6: Dithering option (Checkbutton)
        chk_d = tk.Checkbutton(grid_frame, text="Enable texconv dithering (-bc d)", variable=val_dither, bg=self.bg_color, fg=self.text_color, activebackground=self.bg_color, activeforeground=self.text_color, selectcolor=self.card_color, font=("Segoe UI", 9))
        chk_d.grid(row=5, column=1, sticky="w", padx=5, pady=5)
        
        # Bottom Buttons Row
        btn_frame = tk.Frame(dialog, bg=self.bg_color)
        btn_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        def save():
            config["ffxii_convert_path"] = val_convert.get().strip()
            config["noesis_path"] = val_noesis.get().strip()
            config["texconv_path"] = val_texconv.get().strip()
            config["compressonator_path"] = val_compressonator.get().strip()
            config["dds_encoder"] = val_encoder.get()
            config["texconv_dither"] = val_dither.get()
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(config, f, indent=2)
                self.log_text("Configuration updated successfully.\n", "success")
                messagebox.showinfo("Success", "Configuration updated successfully!", parent=dialog)
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save configuration: {e}", parent=dialog)
                
        btn_save = tk.Button(btn_frame, text="Save Settings", command=save, bg=self.accent_color, fg="white", font=("Segoe UI", 10, "bold"), relief="flat", activebackground=self.accent_hover, activeforeground="white", padx=15, pady=5)
        btn_save.pack(side="left")
        self.bind_hover(btn_save, is_primary=True)
        
        def clear_recent():
            if messagebox.askyesno("Confirm", "Are you sure you want to clear the recent files list?", parent=dialog):
                self.recent_files = []
                self.save_config()
                self.update_recent_menu()
                self.log_text("Recent files list cleared.\n", "info")
                messagebox.showinfo("Success", "Recent files list cleared!", parent=dialog)
                
        btn_clear = tk.Button(btn_frame, text="Clear Recent Files", command=clear_recent, bg=self.error_color, fg="white", font=("Segoe UI", 10), relief="flat", activebackground="#dc2626", activeforeground="white", padx=15, pady=5)
        btn_clear.pack(side="left", padx=(10, 0))
        self.bind_hover(btn_clear)
        
        btn_cancel = tk.Button(btn_frame, text="Cancel", command=dialog.destroy, bg=self.card_color, fg=self.text_color, font=("Segoe UI", 10), relief="flat", activebackground=self.border_color, activeforeground=self.text_color, padx=15, pady=5)
        btn_cancel.pack(side="right")
        self.bind_hover(btn_cancel)



    def extract_texture_preview(self, phyre_path):
        self.current_preview_target = phyre_path
        self.clear_preview()
        if hasattr(self, 'btn_fullscreen'):
            self.btn_fullscreen.config(state="disabled", bg=self.card_color, fg=self.text_dim)
        
        # Show loading status
        def show_loading():
            self.lbl_thumbnail.config(text="[Extracting Preview...]")
        self.root.after(0, show_loading)
        
        def run():
            try:
                fd, temp_png = tempfile.mkstemp(suffix=".png", prefix="ffx_tex_prev_")
                os.close(fd)
                self.temp_preview_files.append(temp_png)
                
                backend = PhyreToolBackend()
                cmd = [backend.ffxii_convert_path, "unpack", phyre_path, temp_png]
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                process.wait()
                
                if process.returncode == 0 and os.path.exists(temp_png) and os.path.getsize(temp_png) > 0:
                    if self.current_preview_target == phyre_path:
                        self.show_preview(temp_png)
                else:
                    if self.current_preview_target == phyre_path:
                        def show_fail():
                            self.lbl_thumbnail.config(text="[No Preview]")
                        self.root.after(0, show_fail)
            except Exception:
                if self.current_preview_target == phyre_path:
                    def show_fail():
                        self.lbl_thumbnail.config(text="[No Preview]")
                    self.root.after(0, show_fail)
        
        threading.Thread(target=run, daemon=True).start()

    def handle_model_selected(self, phyre_path):
        self.current_preview_target = phyre_path
        self.clear_preview()
        
        # Enable Preview Model button and show loading text on thumbnail label
        def update_ui_loading():
            self.lbl_thumbnail.config(text="[Loading Mesh & Texture...]")
            self.lbl_thumbnail_name.config(text=os.path.basename(phyre_path))
            if hasattr(self, 'btn_fullscreen'):
                self.btn_fullscreen.config(state="normal", bg=self.accent_color, fg="white")
        self.root.after(0, update_ui_loading)
        
        def run():
            temp_dir = None
            try:
                temp_dir = tempfile.mkdtemp(prefix="ffx_phyre_preview_")
                self.temp_preview_files.append(temp_dir)
                
                backend = PhyreToolBackend()
                
                model_name = os.path.splitext(os.path.basename(phyre_path))[0]
                if model_name.lower().endswith(".dae"):
                    model_name = model_name[:-4]
                temp_fbx = os.path.join(temp_dir, model_name + ".fbx")
                temp_gltf = os.path.join(temp_dir, model_name + ".gltf")
                
                # Step 1: Unpack to FBX
                ret = backend.run_cmd([backend.ffxii_convert_path, "unpack", phyre_path, temp_fbx, "-r"])
                if ret != 0 or not os.path.exists(temp_fbx):
                    if self.current_preview_target == phyre_path:
                        def show_fail():
                            self.lbl_thumbnail.config(text="[No Preview]")
                        self.root.after(0, show_fail)
                    return
                
                # Step 2: Convert FBX to GLTF
                ret = backend.run_cmd([backend.noesis_path, "?cmode", temp_fbx, temp_gltf])
                if ret != 0 or not os.path.exists(temp_gltf):
                    if self.current_preview_target == phyre_path:
                        def show_fail():
                            self.lbl_thumbnail.config(text="[No Preview]")
                        self.root.after(0, show_fail)
                    return
                
                # Step 3: Check for PNG textures extracted by Noesis in temp_dir
                import glob
                extracted_pngs = glob.glob(os.path.join(temp_dir, "*.png"))
                extracted_pngs = [p for p in extracted_pngs if os.path.basename(p) != "main_texture.png"]
                
                main_png = None
                if extracted_pngs:
                    extracted_pngs.sort(key=lambda p: os.path.getsize(p), reverse=True)
                    main_png = extracted_pngs[0]
                    if self.current_preview_target == phyre_path:
                        self.load_3d_texture_background(main_png)
                
                # Step 4: Fallback to grandparent search if no PNG was extracted
                if main_png is None:
                    grandparent = os.path.dirname(os.path.dirname(os.path.dirname(phyre_path)))
                    texture_phyres = glob.glob(os.path.join(grandparent, "**", "*.dds.phyre"), recursive=True)
                    
                    if texture_phyres:
                        texture_phyres.sort(key=lambda p: os.path.getsize(p), reverse=True)
                        main_tex_phyre = texture_phyres[0]
                        temp_png = os.path.join(temp_dir, "main_texture.png")
                        
                        ret = backend.run_cmd([backend.ffxii_convert_path, "unpack", main_tex_phyre, temp_png])
                        if ret == 0 and os.path.exists(temp_png):
                            if self.current_preview_target == phyre_path:
                                self.load_3d_texture_background(temp_png)
                
                # Step 5: Load GLTF in Python memory for rendering
                if self.current_preview_target == phyre_path:
                    self.load_3d_model_for_preview(temp_gltf)
            except Exception:
                if self.current_preview_target == phyre_path:
                    def show_fail():
                        self.lbl_thumbnail.config(text="[No Preview]")
                    self.root.after(0, show_fail)
            finally:
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception:
                        pass
                    if temp_dir in self.temp_preview_files:
                        self.temp_preview_files.remove(temp_dir)
        
        threading.Thread(target=run, daemon=True).start()


    def handle_no_preview(self):
        self.current_preview_target = None
        self.clear_preview()
        def update_ui():
            if hasattr(self, 'btn_fullscreen'):
                self.btn_fullscreen.config(state="disabled", bg=self.card_color, fg=self.text_dim)
        self.root.after(0, update_ui)

    def preview_model(self):
        phyre_path = self.unpack_phyre_in.get()
        if not phyre_path or not os.path.exists(phyre_path):
            messagebox.showerror("Error", "Selected model file does not exist.")
            return
            
        self.btn_preview_model.config(state="disabled", bg=self.card_color, fg=self.text_dim)
        self.set_status("Extracting model for preview...", self.accent_color, "white")
        self.log_text(f"--- Preparing 3D Preview for {os.path.basename(phyre_path)} ---\n")
        
        def run():
            temp_dir = None
            try:
                temp_dir = tempfile.mkdtemp(prefix="ffx_phyre_preview_")
                self.temp_preview_files.append(temp_dir)
                
                model_name = os.path.splitext(os.path.basename(phyre_path))[0]
                if model_name.lower().endswith(".dae"):
                    model_name = model_name[:-4]
                temp_fbx = os.path.join(temp_dir, model_name + ".fbx")
                
                backend = PhyreToolBackend(log_callback=self.log_text)
                
                self.log_text("Extracting model references and geometry...\n")
                ret = backend.run_cmd([backend.ffxii_convert_path, "unpack", phyre_path, temp_fbx, "-r"])
                
                if ret != 0 or not os.path.exists(temp_fbx):
                    self.log_text("Error: Preview extraction failed.\n", "error")
                    self.set_status("Preview failed", self.error_color, "white")
                    return
                
                self.log_text("Launching Noesis viewer...\n")
                self.set_status("Noesis Viewer Active", self.success_color, "white")
                
                noesis_cmd = [backend.noesis_path, temp_fbx]
                process = subprocess.Popen(
                    noesis_cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                process.wait()
                
                self.log_text("Closed Noesis viewer. Cleaning up temp files...\n")
                self.set_status("Ready")
            except Exception as e:
                self.log_text(f"Error during preview: {str(e)}\n", "error")
                self.set_status("Preview Error", self.error_color, "white")
            finally:
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception:
                        pass
                    if temp_dir in self.temp_preview_files:
                        self.temp_preview_files.remove(temp_dir)
                
                def enable_btn():
                    current_path = self.unpack_phyre_in.get()
                    if current_path == phyre_path:
                        if hasattr(self, 'btn_fullscreen'):
                            self.btn_fullscreen.config(state="normal", bg=self.accent_color, fg="white")
                self.root.after(0, enable_btn)
                
        threading.Thread(target=run, daemon=True).start()



    def set_status(self, text, bg_color=None, fg_color=None):
        def update():
            self.status_var.set(text)
            self.status_bar.config(bg=bg_color or "#1e1e1e", fg=fg_color or self.text_dim)
        self.root.after(0, update)

    def bind_hover(self, btn, is_primary=False):
        if is_primary:
            btn.bind("<Enter>", lambda e: btn.config(bg=self.accent_hover))
            btn.bind("<Leave>", lambda e: btn.config(bg=self.accent_color))
        else:
            btn.bind("<Enter>", lambda e: btn.config(bg=self.border_color))
            btn.bind("<Leave>", lambda e: btn.config(bg=self.card_color))

    def setup_unpack_tab(self, frame):
        self.unpack_phyre_in = tk.StringVar()
        self.unpack_model_out = tk.StringVar()

        # Trace file picker path to dynamically change output format and labels
        self.unpack_phyre_in.trace_add("write", self.on_unpack_in_changed)

        # Input row
        lbl_in = ttk.Label(frame, text="Source .phyre File:")
        lbl_in.grid(row=0, column=0, sticky="w", pady=5)
        ent_in = tk.Entry(frame, textvariable=self.unpack_phyre_in, bg=self.card_color, fg=self.text_color,
                          insertbackground="white", bd=0, highlightthickness=1,
                          highlightbackground=self.border_color, highlightcolor=self.accent_color,
                          font=("Segoe UI", 10))
        ent_in.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        btn_in = tk.Button(frame, text="Select File", command=self.select_unpack_in, bg=self.card_color, fg=self.text_color,
                           relief="flat", activebackground=self.border_color, activeforeground=self.text_color)
        btn_in.grid(row=0, column=2, pady=5)
        self.bind_hover(btn_in)

        # Output row
        self.lbl_unpack_out = ttk.Label(frame, text="Destination .gltf File:")
        self.lbl_unpack_out.grid(row=1, column=0, sticky="w", pady=5)
        ent_out = tk.Entry(frame, textvariable=self.unpack_model_out, bg=self.card_color, fg=self.text_color,
                           insertbackground="white", bd=0, highlightthickness=1,
                           highlightbackground=self.border_color, highlightcolor=self.accent_color,
                           font=("Segoe UI", 10))
        ent_out.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        btn_out = tk.Button(frame, text="Select Path", command=self.select_unpack_out, bg=self.card_color, fg=self.text_color,
                            relief="flat", activebackground=self.border_color, activeforeground=self.text_color)
        btn_out.grid(row=1, column=2, pady=5)
        self.bind_hover(btn_out)

        # Run Button
        self.btn_unpack_run = tk.Button(frame, text="Extract Model (Phyre -> gltf)", command=self.start_unpack, bg=self.accent_color, fg="#ffffff",
                            font=("Segoe UI", 11, "bold"), relief="flat", activebackground=self.accent_hover, activeforeground="#ffffff", pady=5)
        self.btn_unpack_run.grid(row=2, column=1, pady=20, sticky="w")
        self.bind_hover(self.btn_unpack_run, is_primary=True)

        frame.columnconfigure(1, weight=1)

    def setup_pack_tab(self, frame):
        self.pack_orig_phyre = tk.StringVar()
        self.pack_model_in = tk.StringVar()
        self.pack_phyre_out = tk.StringVar()

        # Trace model input selection to dynamically adapt labels and defaults
        self.pack_model_in.trace_add("write", self.on_pack_model_changed)

        # Modified Model Input Row
        self.lbl_pack_model = ttk.Label(frame, text="Modified Model (.gltf):")
        self.lbl_pack_model.grid(row=0, column=0, sticky="w", pady=5)
        ent_model = tk.Entry(frame, textvariable=self.pack_model_in, bg=self.card_color, fg=self.text_color,
                             insertbackground="white", bd=0, highlightthickness=1,
                             highlightbackground=self.border_color, highlightcolor=self.accent_color,
                             font=("Segoe UI", 10))
        ent_model.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        btn_model = tk.Button(frame, text="Select File", command=self.select_pack_model, bg=self.card_color, fg=self.text_color,
                              relief="flat", activebackground=self.border_color, activeforeground=self.text_color)
        btn_model.grid(row=0, column=2, pady=5)
        self.bind_hover(btn_model)

        # Original Reference Phyre Row
        self.lbl_pack_orig = ttk.Label(frame, text="Original Reference .phyre:")
        self.lbl_pack_orig.grid(row=1, column=0, sticky="w", pady=5)
        ent_orig = tk.Entry(frame, textvariable=self.pack_orig_phyre, bg=self.card_color, fg=self.text_color,
                            insertbackground="white", bd=0, highlightthickness=1,
                            highlightbackground=self.border_color, highlightcolor=self.accent_color,
                            font=("Segoe UI", 10))
        ent_orig.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        btn_orig = tk.Button(frame, text="Select File", command=self.select_pack_orig, bg=self.card_color, fg=self.text_color,
                             relief="flat", activebackground=self.border_color, activeforeground=self.text_color)
        btn_orig.grid(row=1, column=2, pady=5)
        self.bind_hover(btn_orig)

        # Output Phyre Row
        self.lbl_pack_out = ttk.Label(frame, text="Output Modded .phyre:")
        self.lbl_pack_out.grid(row=2, column=0, sticky="w", pady=5)
        ent_out = tk.Entry(frame, textvariable=self.pack_phyre_out, bg=self.card_color, fg=self.text_color,
                           insertbackground="white", bd=0, highlightthickness=1,
                           highlightbackground=self.border_color, highlightcolor=self.accent_color,
                           font=("Segoe UI", 10))
        ent_out.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        btn_out = tk.Button(frame, text="Select Path", command=self.select_pack_out, bg=self.card_color, fg=self.text_color,
                            relief="flat", activebackground=self.border_color, activeforeground=self.text_color)
        btn_out.grid(row=2, column=2, pady=5)
        self.bind_hover(btn_out)

        # Run Button
        self.btn_pack_run = tk.Button(frame, text="Repack Model (gltf -> Phyre)", command=self.start_pack, bg=self.accent_color, fg="#ffffff",
                            font=("Segoe UI", 11, "bold"), relief="flat", activebackground=self.accent_hover, activeforeground="#ffffff", pady=5)
        self.btn_pack_run.grid(row=3, column=1, pady=20, sticky="w")
        self.bind_hover(self.btn_pack_run, is_primary=True)

        frame.columnconfigure(1, weight=1)

    # Smart UI events
    def on_unpack_in_changed(self, *args):
        path = self.unpack_phyre_in.get()
        if not path or "files selected" in path:
            if path and "files selected" in path:
                self.handle_no_preview()
                self.lbl_thumbnail.config(text="[Multiple Files Selected]")
            else:
                self.handle_no_preview()
            return
        base, _ = os.path.splitext(path)
        if path.lower().endswith('.dds.phyre'):
            self.lbl_unpack_out.config(text="Destination Image File:")
            if base.lower().endswith('.dds'):
                base = base[:-4]
            # Keep .png as default but label is generic
            self.unpack_model_out.set(base + ".png")
            self.btn_unpack_run.config(text="Extract Texture (Phyre -> Image)")
            self.extract_texture_preview(path)
        elif path.lower().endswith('.phyre'):
            self.lbl_unpack_out.config(text="Destination .gltf File:")
            if base.lower().endswith('.dae'):
                base = base[:-4]
            self.unpack_model_out.set(base + ".gltf")
            self.btn_unpack_run.config(text="Extract Model (Phyre -> gltf)")
            self.handle_model_selected(path)
        else:
            self.handle_no_preview()


    def on_pack_model_changed(self, *args):
        path = self.pack_model_in.get()
        if not path or "files selected" in path:
            return
        if path.lower().endswith('.png') or path.lower().endswith('.dds'):
            self.lbl_pack_model.config(text="Modified Texture (.png/.dds):")
            self.lbl_pack_orig.config(text="Original Reference .dds.phyre:")
            self.lbl_pack_out.config(text="Output Modded .dds.phyre:")
            self.btn_pack_run.config(text="Repack Texture (Image -> Phyre)")
            if path.lower().endswith('.png'):
                self.show_preview(path)
            else:
                self.clear_preview()
        else:
            self.lbl_pack_model.config(text="Modified Model (.gltf):")
            self.lbl_pack_orig.config(text="Original Reference .phyre:")
            self.lbl_pack_out.config(text="Output Modded .phyre:")
            self.btn_pack_run.config(text="Repack Model (gltf -> Phyre)")
            self.clear_preview()

    # Browser Dialogs
    def select_unpack_in(self):
        paths = filedialog.askopenfilenames(title="Select Source Phyre File(s)", filetypes=[("Phyre files", "*.phyre")])
        if paths:
            self.btn_open_folder.config(state="disabled", bg=self.card_color, fg=self.text_dim)
            if len(paths) == 1:
                self.selected_unpack_paths = [paths[0]]
                self.unpack_phyre_in.set(paths[0])
            else:
                self.selected_unpack_paths = list(paths)
                self.unpack_phyre_in.set(f"{len(paths)} files selected")
                self.unpack_model_out.set("Multiple outputs (Auto-calculated)")
                self.lbl_unpack_out.config(text="Destination Files:")
                self.btn_unpack_run.config(text="Batch Extract Phyre Files")

    def select_unpack_out(self):
        if len(self.selected_unpack_paths) > 1:
            messagebox.showinfo("Batch Info", "Outputs will be automatically generated in the same directory as source files.")
            return

        path = self.unpack_phyre_in.get()
        if path.lower().endswith('.dds.phyre'):
            filetypes = [("PNG Image", "*.png"), ("DDS Texture", "*.dds")]
            def_ext = ".png"
            title = "Select Destination Image File"
        else:
            filetypes = [("glTF 2.0 Model", "*.gltf")]
            def_ext = ".gltf"
            title = "Select Destination glTF File"

        out_path = filedialog.asksaveasfilename(title=title, filetypes=filetypes, defaultextension=def_ext)
        if out_path:
            self.unpack_model_out.set(out_path)

    def select_pack_model(self):
        paths = filedialog.askopenfilenames(title="Select Modified File(s)", filetypes=[("Model / Texture Files", "*.gltf;*.png;*.dds")])
        if paths:
            self.btn_open_folder.config(state="disabled", bg=self.card_color, fg=self.text_dim)
            if len(paths) == 1:
                self.selected_pack_paths = [paths[0]]
                self.pack_model_in.set(paths[0])
                if not self.pack_orig_phyre.get():

                    self.log_text(f"Auto-selected file: {os.path.basename(paths[0])}\n")
            else:
                self.selected_pack_paths = list(paths)
                self.pack_model_in.set(f"{len(paths)} files selected")
                self.pack_orig_phyre.set("Required: Match folder of references")
                self.pack_phyre_out.set("Multiple outputs (Auto-calculated)")
                self.lbl_pack_model.config(text="Modified Files:")
                self.lbl_pack_orig.config(text="Reference Source File/Folder:")
                self.lbl_pack_out.config(text="Output Directory:")
                self.btn_pack_run.config(text="Batch Repack Files")

    def select_pack_orig(self):
        path = self.selected_pack_paths[0] if self.selected_pack_paths else ""
        if len(self.selected_pack_paths) > 1:
            # Batch repack: ask for reference file, will seek its folder
            orig_path = filedialog.askopenfilename(title="Select A Sample Original Reference Phyre", 
                                                   filetypes=[("Phyre Files", "*.phyre")])
            if orig_path:
                self.pack_orig_phyre.set(orig_path)
            return

        if path.lower().endswith('.png'):
            filetypes = [("Texture Phyre Files", "*.dds.phyre")]
            title = "Select Original Reference .dds.phyre"
        else:
            filetypes = [("Model Phyre Files", "*.phyre")]
            title = "Select Original Reference .phyre"
            
        orig_path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if orig_path:
            self.pack_orig_phyre.set(orig_path)
            if not self.pack_phyre_out.get():
                base, ext = os.path.splitext(orig_path)
                self.pack_phyre_out.set(base + "_modded" + ext)

    def select_pack_out(self):
        if len(self.selected_pack_paths) > 1:
            messagebox.showinfo("Batch Info", "Output modded files will be written with '_modded' suffix in original reference directories.")
            return

        path = self.pack_model_in.get()
        if path.lower().endswith(('.png', '.dds')):
            filetypes = [("Texture Phyre Files", "*.dds.phyre")]
            def_ext = ".dds.phyre"
            title = "Select Destination .dds.phyre File"
        else:
            filetypes = [("Model Phyre Files", "*.phyre")]
            def_ext = ".phyre"
            title = "Select Destination .phyre File"
            
        out_path = filedialog.asksaveasfilename(title=title, filetypes=filetypes, defaultextension=def_ext)
        if out_path:
            self.pack_phyre_out.set(out_path)

    # Logger
    def log_text(self, text, tag=None):
        if not self.txt_log:
            return
        if tag is None:
            text_lower = text.lower()
            if "error" in text_lower or "failed" in text_lower:
                tag = "error"
            elif "successful" in text_lower or "success" in text_lower:
                tag = "success"
            elif text.startswith("---") or text.startswith("Step") or text.startswith("Running"):
                tag = "info"
            else:
                tag = "default"
        def update():
            if self.txt_log:
                self.txt_log.insert(tk.END, text, tag)
                self.txt_log.see(tk.END)
        self.root.after(0, update)

    def clear_log(self):
        if self.txt_log:
            self.txt_log.delete("1.0", tk.END)

    # Threads wrappers
    def start_unpack(self):
        if not self.selected_unpack_paths:
            messagebox.showerror("Error", "Please select source .phyre file(s).")
            return

        self.clear_log()
        self.btn_open_folder.config(state="disabled", bg=self.card_color, fg=self.text_dim)
        
        backend = PhyreToolBackend(log_callback=self.log_text)
        total = len(self.selected_unpack_paths)

        def run():
            success_count = 0
            for idx, phyre_in in enumerate(self.selected_unpack_paths):
                # Calculate output filename
                base, _ = os.path.splitext(phyre_in)
                is_texture = phyre_in.lower().endswith('.dds.phyre')
                
                if is_texture:
                    if base.lower().endswith('.dds'):
                        base = base[:-4]
                    out_model = base + ".png"
                else:
                    if base.lower().endswith('.dae'):
                        base = base[:-4]
                    out_model = base + ".gltf"
                
                if total == 1:
                    out_model = self.unpack_model_out.get()
                    if not out_model:
                        self.set_status("Extraction aborted.", self.error_color, "white")
                        return

                action_name = "Extracting Texture" if is_texture else "Extracting Model"
                self.set_status(f"{action_name} [{idx+1}/{total}]...", self.accent_color, "white")
                self.log_text(f"[{idx+1}/{total}] Unpacking: {os.path.basename(phyre_in)}\n")

                success = backend.unpack(phyre_in, out_model)
                if success:
                    success_count += 1
                    self.add_recent_file(phyre_in)
                    if is_texture and os.path.exists(out_model) and out_model.lower().endswith('.png'):
                        self.show_preview(out_model)
                else:
                    self.log_text(f"Error: Extraction failed for {phyre_in}\n")

            if success_count == total:
                self.set_status("All extractions successful!", self.success_color, "white")
                self.show_open_folder_btn(os.path.dirname(self.selected_unpack_paths[0]))
                messagebox.showinfo("Success", "All files extracted successfully!")
            else:
                self.set_status(f"Extracted {success_count}/{total} files.", self.error_color, "white")
                messagebox.showerror("Errors Occurred", f"Extracted {success_count} out of {total} files successfully. Check logs.")

        threading.Thread(target=run, daemon=True).start()

    def start_pack(self):
        if not self.selected_pack_paths:
            messagebox.showerror("Error", "Please select modified file(s) to repack.")
            return
        
        orig_ref = self.pack_orig_phyre.get()
        if not orig_ref or "Required" in orig_ref:
            messagebox.showerror("Error", "Please select original reference Phyre file.")
            return

        self.clear_log()
        self.btn_open_folder.config(state="disabled", bg=self.card_color, fg=self.text_dim)
        
        backend = PhyreToolBackend(log_callback=self.log_text)
        total = len(self.selected_pack_paths)

        def find_matching_reference(ref_base_path, modified_filename):
            mod_name = os.path.splitext(modified_filename)[0]
            if mod_name.endswith('_modded'):
                mod_name = mod_name[:-7]
            
            ref_dir = os.path.dirname(ref_base_path)
            if not os.path.exists(ref_dir):
                return ref_base_path
                
            for f in os.listdir(ref_dir):
                if f.lower().startswith(mod_name.lower()) and f.lower().endswith('.phyre'):
                    return os.path.join(ref_dir, f)
            return ref_base_path

        def run():
            success_count = 0
            for idx, ref_model in enumerate(self.selected_pack_paths):
                ref_phyre = find_matching_reference(orig_ref, os.path.basename(ref_model))
                
                base, ext = os.path.splitext(ref_phyre)
                phyre_out = base + "_modded" + ext
                
                if total == 1:
                    phyre_out = self.pack_phyre_out.get()
                    if not phyre_out:
                        self.set_status("Repack aborted.", self.error_color, "white")
                        return

                is_texture = ref_model.lower().endswith('.png') or ref_model.lower().endswith('.dds')
                action_name = "Repacking Texture" if is_texture else "Repacking Model"
                
                self.set_status(f"{action_name} [{idx+1}/{total}]...", self.accent_color, "white")
                self.log_text(f"[{idx+1}/{total}] Repacking: {os.path.basename(ref_model)} using reference {os.path.basename(ref_phyre)}\n")

                success = backend.pack(ref_phyre, ref_model, phyre_out)
                if success:
                    success_count += 1
                    self.add_recent_file(ref_model)
                else:
                    self.log_text(f"Error: Repack failed for {ref_model}\n")

            if success_count == total:
                self.set_status("All repacks successful!", self.success_color, "white")
                self.show_open_folder_btn(os.path.dirname(self.selected_pack_paths[0]))
                messagebox.showinfo("Success", "All files repacked successfully!")
            else:
                self.set_status(f"Repacked {success_count}/{total} files.", self.error_color, "white")
                messagebox.showerror("Errors Occurred", f"Repacked {success_count} out of {total} files successfully. Check logs.")

        threading.Thread(target=run, daemon=True).start()


def warp_triangle(img_src, img_dst, tri_src, tri_dst):
    # Find bounding box for each triangle
    r2 = cv2.boundingRect(tri_dst) # (x, y, w, h)
    
    # Clip r2 to img_dst bounds to prevent indexing errors
    h_dst, w_dst = img_dst.shape[:2]
    x_min = max(0, r2[0])
    y_min = max(0, r2[1])
    x_max = min(w_dst, r2[0] + r2[2])
    y_max = min(h_dst, r2[1] + r2[3])
    
    if x_min >= x_max or y_min >= y_max:
        return
        
    bx_w = x_max - x_min
    bx_h = y_max - y_min
    
    r1 = cv2.boundingRect(tri_src)
    h_src, w_src = img_src.shape[:2]
    sx_min = max(0, r1[0])
    sy_min = max(0, r1[1])
    sx_max = min(w_src, r1[0] + r1[2])
    sy_max = min(h_src, r1[1] + r1[3])
    
    if sx_min >= sx_max or sy_min >= sy_max:
        return
        
    # Crop patches and offset coordinates
    tri1_cropped = tri_src - np.array([r1[0], r1[1]], dtype=np.float32)
    tri2_cropped = tri_dst - np.array([x_min, y_min], dtype=np.float32)
    
    img1_cropped = img_src[sy_min:sy_max, sx_min:sx_max]
    if img1_cropped.size == 0:
        return
        
    # Recalculate affine mapping matrix
    warp_mat = cv2.getAffineTransform(tri1_cropped, tri2_cropped)
    
    # Warp patch to the size of the destination bounding box
    img2_cropped = cv2.warpAffine(img1_cropped, warp_mat, (bx_w, bx_h), None,
                                  flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
                                  
    # Create mask for destination triangle
    mask = np.zeros((bx_h, bx_w), dtype=np.uint8)
    cv2.fillConvexPoly(mask, tri2_cropped.astype(np.int32), 255)
    
    # Crop the target region to modify
    roi = img_dst[y_min:y_max, x_min:x_max]
    
    # Apply using NumPy mask
    mask_3d = np.expand_dims(mask == 255, axis=-1)
    np.copyto(roi, img2_cropped, where=mask_3d)


def main():
    parser = argparse.ArgumentParser(description="FFX Phyre Asset Extraction & Repacking Utility")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode")
    parser.add_argument("--mode", choices=["unpack", "pack"], help="Operation mode (unpack/pack)")
    parser.add_argument("--input", help="Input file (Source Phyre for unpack, Modified asset for pack)")
    parser.add_argument("--output", help="Output file (Destination glTF/PNG for unpack, Modded Phyre for pack)")
    parser.add_argument("--ref", help="Reference original Phyre (Required for pack mode only)")
    parser.add_argument("--ffxii_convert", help="Path to FFXIIConvert.exe")
    parser.add_argument("--noesis", help="Path to Noesis64.exe")

    args = parser.parse_args()

    # CLI Mode execution
    if args.cli or args.mode:
        if not args.mode or not args.input or not args.output:
            parser.print_help()
            sys.exit(1)
            
        backend = PhyreToolBackend(args.ffxii_convert, args.noesis)
        
        if args.mode == "unpack":
            success = backend.unpack(args.input, args.output)
            sys.exit(0 if success else 1)
        elif args.mode == "pack":
            if not args.ref:
                print("Error: --ref parameter (original reference Phyre) is required for pack mode.")
                sys.exit(1)
            success = backend.pack(args.ref, args.input, args.output)
            sys.exit(0 if success else 1)
    else:
        # Launch GUI Mode
        root = tk.Tk()
        app = PhyreToolGUI(root)
        root.mainloop()

if __name__ == "__main__":
    main()
()
