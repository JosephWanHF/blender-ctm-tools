import bpy
from . import io_openctm
from .io_openctm import OpenCTMImport, OpenCTMExport

bl_info = {
    "name": "OpenCTM (.ctm)",
    "description": "Import/Export meshes from/to OpenCTM (.ctm)",
    "author": "RealIndrit",
    "version": (1, 4, 0),
    "blender": (3, 6, 0),
    "location": "File > Import-Export",
    "warning": "",
    "wiki_url": "https://github.com/RealIndrit/blender-import-openctm",
    "tracker_url": "https://github.com/RealIndrit/blender-import-openctm",
    "category": "Import-Export",
}

def menu_import(self, context):
    self.layout.operator(OpenCTMImport.bl_idname, text="OpenCTM (.ctm)")

def menu_export(self, context):
    self.layout.operator(OpenCTMExport.bl_idname, text="OpenCTM (.ctm)")

def menu_object_print_tools(self, context):
    self.layout.separator()
    self.layout.operator("object.openctm_split_loose_parts_object_mode", text="OpenCTM Split Loose Parts (Object Mode)")
    self.layout.operator("object.openctm_select_touching_panels", text="OpenCTM Select Touching Panels")
    self.layout.operator("object.openctm_make_printable_solid", text="OpenCTM Make Printable Solid")
    self.layout.operator("object.openctm_process_selected_individually", text="OpenCTM Process Selected Individually")

def register():
    io_openctm.register()
    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_export)
    bpy.types.VIEW3D_MT_object.append(menu_object_print_tools)

def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_object_print_tools)
    io_openctm.unregister()
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_export)

if __name__ == "__main__":
    register()
