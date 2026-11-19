# Blender CTM Tools

Two Blender tools for importing OpenCTM meshes and mapping their faces into named parts. Built and tested with Blender 4.4.3 on Apple Silicon; Windows x64 binaries are included but the full workflow has not been tested there.

- **OpenCTM Import/Export** imports `.ctm` meshes and includes loose-parts and experimental print-solid operations. This is a modified copy of [RealIndrit/blender-openctm](https://github.com/RealIndrit/blender-openctm).
- **CTM Part Mapper** labels faces into named, colour-coded parts. It supports selection expansion, part visibility, notes, review status, extracting a reference copy, and exporting a JSON mapping report.

## Installation

Download the two ZIP files from the [`dist` folder](dist/). In Blender 4.2 or later, open **Edit → Preferences → Add-ons**, use the top-right menu **Install from Disk**, and select each ZIP. Enable both add-ons if Blender doesn't do so automatically. The OpenCTM importer appears under **File → Import → OpenCTM (.ctm)**. The mapper appears in the 3D View sidebar (**N → CTM Map**).

The importer package includes OpenCTM libraries for **Apple Silicon macOS** and **Windows x64**. Intel macOS and Linux binaries are not bundled. Linux may work with a separately installed OpenCTM library but has not been tested here. Blender 4.4.3 on Apple Silicon is the tested configuration.

## Mapping workflow

1. Import a CTM file. In Object Mode, select its mesh, open **CTM Map**, set the desired longest dimension in millimetres, and click **Prepare Mapping Copy**. This scales a copy and hides the original; it doesn't change the source CTM.
2. Add a part and give it a name and colour. In Edit Mode, use face select, box select (`B`) or lasso (`Ctrl`-drag). Use **Expand to Connected Islands** to grow the selection across visible shared edges, then review and **Assign**. Skip expansion to label part of an island.
3. **Protect Other Parts** prevents expansion into other labels. It doesn't prevent an explicit reassignment with **Assign**. Use **Unassign**, **Hide Part**, **Isolate**, **Unassigned Only**, and **Reveal All** as needed.
4. Add notes and a mapping status. In Object Mode use **Extract Active Part Copy** to make a separate reference object, or **Export Mapping Report** for a JSON handoff. Save the `.blend` to preserve labels. For viewport colours, use Solid shading with **Color → Attribute**; after changing a colour use **Refresh Colours**.

The report is a snapshot: export it again after mapping changes. Its part labels and axis-aligned bounds describe human selections, not verified assemblies, print-ready solids, or joints. Avoid topology changes to a labelled mesh; they can invalidate mappings. The mapper currently has no dedicated paint brush, printability validation, or connector generator.

## Testing

For each file in `tests/`, run:

```sh
/path/to/blender --background --factory-startup --python-exit-code 1 --python tests/test_mapping_handoff.py
/path/to/blender --background --factory-startup --python-exit-code 1 --python tests/test_mixed_reassignment.py
/path/to/blender --background --factory-startup --python-exit-code 1 --python tests/test_panel_actions.py
```

These tests cover the mapper; they do not replace manual Blender UI, slicer, or physical-fit testing. No ship models or user mapping files are included.

## Attribution and licensing

The importer is based on [RealIndrit/blender-openctm](https://github.com/RealIndrit/blender-openctm); its supplied [LICENSE](addons/openctm_ctm/LICENSE) retains the upstream and OpenCTM notices. The upstream repository's license file identifies MIT and zlib terms while its Blender extension manifest declares GPL-3.0-or-later; those notices are preserved as supplied rather than reconciled here. CTM Part Mapper is a separate add-on; no separate reuse license has yet been specified for it.
