# FFX Phyre Tool

A modern, zero-configuration graphical utility and CLI tool for extracting and repacking 3D models and textures from **Final Fantasy X/X-2 HD Remaster** `.phyre` files. 

It converts model geometries into the standard `glTF 2.0` format (`.gltf` + `.bin` + textures) for direct importing, editing, and rigging in Blender.

---

## Features

* **3D Viewport Preview:** Preview selected 3D models directly in the GUI. Supports **Wireframe**, **Flat Shaded**, and **Textured** rendering, with support for double-clicking to enter a Fullscreen viewport.
* **Auto Format Detection:** Automatically reads headers of original `.phyre` files to detect texture compression formats: DXT1 (BC1), DXT3 (BC2), or DXT5 (BC3).
* **Dithered Block Compression:** Supports block compression dithering (`-bc d`) with `texconv` to prevent color gradient banding in-game.
* **AMD Compressonator CLI integration:** Built-in support to run `CompressonatorCLI.exe` as the DDS compiler for high-quality texture compression.
* **Adaptive GUI:** Automatically toggles interface modes based on selected assets (model mode for `.phyre`, texture mode for `.dds.phyre`).
* **Recent File History:** Save and load your recent files history from a dropdown list.
* **Batch Operations:** Select multiple files to extract or repack them in batches.

---

## Prerequisites

To respect the copyrights of other creators, **external helper tools are NOT bundled** in this repository. You must download them separately and place them in the `tools/` folder:

1. **FFXII Asset Converter **CLI version**(`FFXIIConvert.exe`):** Download from [FFXII Asset Converter on Nexus Mods](https://www.nexusmods.com/finalfantasy12/mods/288).
2. **Noesis (`Noesis64.exe`):** Download from [Rich Whitehouse's Official Noesis Page](https://www.richwhitehouse.com/index.php?content=showprograms.php).
3. **DDS Compiler (Choose one or both):**
   * **Microsoft DirectXTex (`texconv.exe`):** Download from [Microsoft's DirectXTex Repository](https://github.com/microsoft/DirectXTex).
   * **AMD Compressonator (`CompressonatorCLI.exe`):** Download from [GPUOpen Compressonator Page](https://gpuopen.com/compressonator/).

### Default Directory Structure:
```text
tools/
├── FFXIIConvert/
│   └── FFXIIConvert.exe
├── noesis/
│   └── Noesis64.exe
├── textconv/
│   └── texconv.exe
└── Compressonator/
    └── CompressonatorCLI.exe
```
*Note: Alternatively, you can configure custom paths directly in **File > Settings**.*

---

## Getting Started

### Extracting Models:
1. Open the **Extract Phyre** tab in the GUI.
2. Select your source `.phyre` model.
3. Click **Extract Model (Phyre -> gltf)**.

### Repacking Models:
1. Edit your extracted `.gltf` model in Blender (triangulated, rigged to the original skeletal bones).
2. Export it from Blender as **glTF Separate (.gltf + .bin + textures)**.
3. Open the **Repack Phyre** tab.
4. Select your modified `.gltf` file and the original `.phyre` reference file.
5. Click **Repack Model (gltf -> Phyre)**.

---

## Building from Source

To compile the Python source script into a standalone `.exe` executable:
```bash
pip install -r requirements.txt
python -m PyInstaller --clean FFX_Phyre_Tool.spec
```
*(UPX compression is disabled by default in the spec file to prevent antivirus false positives).*

---

## Credits
* **Roelin** for creating the excellent FFXII Asset Converter.
* **Rich Whitehouse** for Noesis.
* **Microsoft** for `DirectXTex` / `texconv`.
* **AMD GPUOpen** for `Compressonator`.
