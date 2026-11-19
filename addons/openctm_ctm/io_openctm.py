import bpy
import bmesh
import collections
import math
import mathutils
import numpy as np
from bpy_extras.io_utils import ImportHelper, ExportHelper, axis_conversion, orientation_helper
from ctypes import POINTER, c_char_p, c_float, c_uint, cast
from . import openctm as ctm
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
    EnumProperty,
)

@orientation_helper(axis_forward="Z", axis_up="Y")
class OpenCTMImport(bpy.types.Operator, ImportHelper):
    """Import from OpenCTM Format"""
    bl_idname = "import_scene.openctm"
    bl_label = "Import OpenCTM"
    filename_ext = ".ctm"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.ctm", options={'HIDDEN'})

    uv_pref: BoolProperty(name="UV", description="Import UV", default=True)
    colour_pref: BoolProperty(name="Color", description="Import vertex colors", default=True)
    select_pref: BoolProperty(name="Select", description="Select imported object after completion",
                                        default=True)

    def draw(self, context):
        box = self.layout.box()
        box.prop(self, "axis_forward")
        box.prop(self, "axis_up")

        box = self.layout.box()
        row1 = box.row()
        row1.prop(self, "uv_pref")
        row1.prop(self, "colour_pref")
        row2 = box.row()
        row2.prop(self, "select_pref")

    def execute(self, context):
        if not ctm.IS_AVAILABLE:
            err = getattr(ctm, "_BINDINGS_IMPORT_ERROR", "Unknown OpenCTM binding error")
            self.report({'ERROR'}, f"OpenCTM backend unavailable: {err}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Importing: {self.filepath}...")
        # Ensure there's at least one object
        if bpy.data.objects:
            if bpy.context.object and bpy.context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')

        ctm_context = None
        try:
            ctm_context = ctm.ctmNewContext(ctm.CTM_IMPORT)
            ctm.ctmLoad(ctm_context, _encode(self.filepath))
            err = ctm.ctmGetError(ctm_context)
            if err != ctm.CTM_NONE:
                raise IOError("Error loading file: %s" % str(ctm.ctmErrorString(err)))

            mesh = bpy.data.meshes.new(name="ImportedMesh")

            # read vertices
            vertex_count = ctm.ctmGetInteger(ctm_context, ctm.CTM_VERTEX_COUNT)
            vertex_ctm = ctm.ctmGetFloatArray(ctm_context, ctm.CTM_VERTICES)

            vertices = np.fromiter(vertex_ctm,
                                   dtype=float,
                                   count=vertex_count * 3).reshape((-1, 3))

            # read faces
            face_count = ctm.ctmGetInteger(ctm_context, ctm.CTM_TRIANGLE_COUNT)
            face_ctm = ctm.ctmGetIntegerArray(ctm_context, ctm.CTM_INDICES)
            faces = np.fromiter(face_ctm, dtype=int,
                                count=face_count * 3).reshape((-1, 3))

            mesh.from_pydata(vertices=vertices, edges=[], faces=faces)

            transform_matrix = axis_conversion(
                from_forward=self.axis_forward,
                from_up=self.axis_up,
            ).to_4x4()

            if self.uv_pref:
                if ctm.ctmGetInteger(ctm_context, ctm.CTM_UV_MAP_COUNT) > 0:
                    for map_index in range(8):
                        uv_coords = ctm.ctmGetFloatArray(ctm_context, (ctm.CTM_UV_MAP_1 + map_index))
                        if uv_coords:
                            uv_name = ctm.ctmGetUVMapString(ctm_context, (ctm.CTM_UV_MAP_1 + map_index), ctm.CTM_NAME)
                            uv_coords = np.fromiter(uv_coords, dtype=float, count=vertex_count * 2).reshape((-1, 2))
                            if uv_name:
                                uv_name = uv_name.decode("utf-8") + f"{map_index}"
                            else:
                                uv_name = f"{map_index}"
                            uv_layer = mesh.uv_layers.new(name=f"UV{uv_name}")

                            for poly in mesh.polygons:
                                for loop_index in poly.loop_indices:
                                    vertex_index = mesh.loops[loop_index].vertex_index
                                    uv = uv_coords[vertex_index]
                                    uv_layer.data[loop_index].uv = (uv[0], uv[1])

            if self.colour_pref:
                colour_map = ctm.ctmGetNamedAttribMap(ctm_context, c_char_p(_encode('Color')))
                if colour_map != ctm.CTM_FALSE:
                    color_3_layer = mesh.vertex_colors.new(name=f"RGBA")
                    colours = ctm.ctmGetFloatArray(ctm_context, colour_map)
                    colours = np.fromiter(colours, count=vertex_count * 4, dtype=float).reshape((-1, 4))

                    for poly in mesh.polygons:
                        for loop_index in poly.loop_indices:
                            vertex_index = mesh.loops[loop_index].vertex_index
                            color = colours[vertex_index]
                            color_3_layer.data[loop_index].color = (color[0], color[1], color[2], color[3])

                    mesh.vertex_colors.active = color_3_layer
            mesh.update()


            mesh_obj = bpy.data.objects.new(name="ImportedObject", object_data=mesh)
            mesh_obj.data.transform(transform_matrix)
            bpy.context.scene.collection.objects.link(mesh_obj)

            if self.select_pref:
                mesh_obj.select_set(True)

        finally:
            if ctm_context:
                ctm.ctmFreeContext(ctm_context)

        self.report({'INFO'}, "Imported: " + self.filepath)
        return {'FINISHED'}

@orientation_helper(axis_forward="Z", axis_up="Y")
class OpenCTMExport(bpy.types.Operator, ExportHelper):
    """Export to OpenCTM Format"""
    bl_idname = "export_scene.openctm"
    bl_label = "Export OpenCTM"

    filename_ext = ".ctm"
    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(default="*.ctm", options={'HIDDEN'})

    uv_pref: BoolProperty(name="UV", description="Export UV", default=True)
    normal_pref: BoolProperty(name="Normal", description="Export Normals", default=True)
    colour_pref: BoolProperty(name="Color", description="Export Vertex colors", default=True)
    compression_pref: EnumProperty(
        name="Algorithm",
        description="What type of compression algorithm the file use",
        items=[("MG1", "MG1", "MG1 Compression"),
               ("MG2", "MG2", "MG2 Compression"),
               ("RAW", "Uncompressed", "No Compression (Raw)"),],
        default="MG1"
    )

    export_vprec: bpy.props.FloatProperty(
        name="Vertex Precision",
        description="Relative vertex precision (fixed point)",
        default=0.01,
        min=0.0001,
        max=1.0
    )
    export_nprec: bpy.props.FloatProperty(
        name="Normal Precision",
        description="Normal precision (fixed point)",
        default=1.0 / 256.0,
        min=0.0001,
        max=1.0
    )
    export_uvprec: bpy.props.FloatProperty(
        name="UV Precision",
        description="UV precision (fixed point)",
        default=1.0 / 1024.0,
        min=0.0001,
        max=1.0
    )
    export_cprec: bpy.props.FloatProperty(
        name="Color Precision",
        description="Color precision (fixed point)",
        default=1.0 / 256.0,
        min=0.0001,
        max=1.0
    )

    def draw(self, context):
        box = self.layout.box()
        box.prop(self, "axis_forward")
        box.prop(self, "axis_up")

        box = self.layout.box()
        row1 = box.row()
        row1.prop(self, "uv_pref")
        row1.prop(self, "colour_pref")
        row2 = box.row()
        row2.prop(self, "normal_pref")

        box = self.layout.box()
        box.prop(self, "compression_pref")

        if self.compression_pref == "MG2":
            box.prop(self, "export_vprec")
            box.prop(self, "export_nprec")
            box.prop(self, "export_uvprec")
            box.prop(self, "export_cprec")


    def execute(self, context):
        if not ctm.IS_AVAILABLE:
            err = getattr(ctm, "_BINDINGS_IMPORT_ERROR", "Unknown OpenCTM binding error")
            self.report({'ERROR'}, f"OpenCTM backend unavailable: {err}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Exporting: {self.filepath}...")
        transform_matrix = axis_conversion(
            from_forward=self.axis_forward,
            from_up=self.axis_up,
        ).to_4x4()

        active_object = bpy.context.active_object

        if active_object is not None:
            if len(bpy.context.selected_objects) == 1:
                if not self.filepath.lower().endswith('.ctm'):
                    self.filepath += '.ctm'


                mesh = active_object.data.copy()
                mesh.transform(transform_matrix)
                mesh.calc_loop_triangles()

                triangle_count = len(mesh.loop_triangles)
                p_indices = cast((c_uint * (3 * triangle_count))(), POINTER(c_uint))

                index = 0
                for tri in mesh.loop_triangles:
                    p_indices[index] = c_uint(tri.vertices[0])
                    p_indices[index + 1] = c_uint(tri.vertices[1])
                    p_indices[index + 2] = c_uint(tri.vertices[2])
                    index += 3

                # Extract vertex array from the Blender mesh
                vertex_count = len(mesh.vertices)
                p_vertices = cast((c_float * (3 * vertex_count))(), POINTER(c_float))

                for i, v in enumerate(mesh.vertices):
                    p_vertices[3 * i] = c_float(v.co.x)
                    p_vertices[3 * i + 1] = c_float(v.co.y)
                    p_vertices[3 * i + 2] = c_float(v.co.z)

                # Extract normals
                if self.normal_pref:
                    p_normals = (c_float * (3 * vertex_count))()
                    for i, v in enumerate(mesh.vertices):
                        p_normals[3 * i] = c_float(v.normal.x)
                        p_normals[3 * i + 1] = c_float(v.normal.y)
                        p_normals[3 * i + 2] = c_float(v.normal.z)
                else:
                    p_normals = POINTER(c_float)()

                # Extract UVs
                if self.uv_pref:
                    p_UV_coords = (c_float * (2 * vertex_count))()

                    if hasattr(mesh, "uv_layers") and mesh.uv_layers:
                        uv_layer = mesh.uv_layers.active.data

                        for f in mesh.polygons:
                            for j, loop_index in enumerate(f.loop_indices):
                                k = mesh.loops[loop_index].vertex_index
                                if k < vertex_count:
                                    uv = uv_layer[loop_index].uv
                                    p_UV_coords[k * 2] = c_float(uv[0])
                                    p_UV_coords[k * 2 + 1] = c_float(uv[1])

                    else:
                        i = 0
                        for v in mesh.vertices:
                            if hasattr(v, "uvco"):
                                p_UV_coords[i] = c_float(v.uvco[0])
                                p_UV_coords[i + 1] = c_float(v.uvco[1])
                                i += 2
                else:
                    p_UV_coords = POINTER(c_float)()
                
                # Extract colors
                if self.colour_pref:
                    p_colors = cast((c_float * 4 * vertex_count)(), POINTER(c_float))
                    if mesh.vertex_colors:
                        color_layer = mesh.vertex_colors.active.data
                        for f in mesh.polygons:
                            for j, loop_index in enumerate(f.loop_indices):
                                k = mesh.loops[loop_index].vertex_index
                                if k < vertex_count:
                                    col = color_layer[loop_index]
                                    p_colors[k * 4] = col.color[0]
                                    p_colors[k * 4 + 1] = col.color[1]
                                    p_colors[k * 4 + 2] = col.color[2]
                                    p_colors[k * 4 + 3] = 1.0
                else:
                    p_colors = POINTER(c_float)()
                ctm_context = None
                try:
                    # Create an OpenCTM context
                    ctm_context = ctm.ctmNewContext(ctm.CTM_EXPORT)

                    # Set the file comment
                    ctm.ctmFileComment(ctm_context, c_char_p(_encode('Created by OpenCTM Addon (https://github.com/RealIndrit/blender-openctm) for Blender (https://www.blender.org/)')))

                    # Define the mesh
                    ctm.ctmDefineMesh(ctm_context, p_vertices, c_uint(vertex_count), p_indices, c_uint(triangle_count), p_normals)

                    # Add UV coordinates?
                    if self.uv_pref:
                        tm = ctm.ctmAddUVMap(ctm_context, p_UV_coords, c_char_p(), c_char_p())
                        if self.compression_pref == "MG2":
                            ctm.ctmUVCoordPrecision(ctm_context, tm, self.export_uvprec)

                    # Add colors?
                    if self.colour_pref:
                        cm = ctm.ctmAddAttribMap(ctm_context, p_colors, c_char_p(_encode('Color')))
                        if self.compression_pref == "MG2":
                            ctm.ctmAttribPrecision(ctm_context, cm, self.export_cprec)

                    # Set compression method
                    if self.compression_pref == "MG2":
                        ctm.ctmVertexPrecisionRel(ctm_context, self.export_vprec)
                        if self.normal_pref:
                            ctm.ctmNormalPrecision(ctm_context, self.export_nprec)


                    if self.compression_pref == "MG2":
                        ctm.ctmCompressionMethod(ctm_context, ctm.CTM_METHOD_MG2)
                    elif self.compression_pref == "MG1":
                        ctm.ctmCompressionMethod(ctm_context, ctm.CTM_METHOD_MG1)
                    elif self.compression_pref == "RAW":
                        ctm.ctmCompressionMethod(ctm_context, ctm.CTM_METHOD_RAW)

                    # Save the file
                    ctm.ctmSave(ctm_context, c_char_p(_encode(self.filepath)))

                    # Check for errors
                    e = ctm.ctmGetError(ctm_context)
                    if e != 0:
                        s = ctm.ctmErrorString(e)
                        self.report({'ERROR'}, f"Could not save the file: {s}")

                finally:
                    # Free the OpenCTM context
                    if ctm_context:
                        ctm.ctmFreeContext(ctm_context)
                    bpy.data.meshes.remove(mesh)

                self.report({'INFO'}, f"Exported: {self.filepath}")
                return {'FINISHED'}
            elif len(bpy.context.selected_objects) > 1:
                self.report({'ERROR'}, "Multiple objects selected, only one object per export allowed")
                return {'CANCELLED'}
            elif len(bpy.context.selected_objects) < 1:
                self.report({'ERROR'}, "No object selected")
                return {'CANCELLED'}
        else:
            self.report({'ERROR'}, f"No object selected")
            return {'CANCELLED'}


class OpenCTMSelectTouchingPanels(bpy.types.Operator):
    """Select mesh objects that touch or nearly touch selected seed objects"""
    bl_idname = "object.openctm_select_touching_panels"
    bl_label = "OpenCTM Select Touching Panels"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: FloatProperty(
        name="Touch Distance",
        description="Max gap distance between object bounds to consider as touching",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        subtype='DISTANCE',
    )
    replace_selection: BoolProperty(
        name="Replace Selection",
        description="Deselect non-matching objects",
        default=True,
    )
    use_selected_as_seed: BoolProperty(
        name="Use Selected As Seed",
        description="Start from all selected mesh objects instead of only active object",
        default=True,
    )
    max_objects: IntProperty(
        name="Max Objects",
        description="Safety cap for objects considered by this operator",
        default=15000,
        min=10,
        max=100000,
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        mesh_objects = [obj for obj in context.visible_objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'ERROR'}, "No visible mesh objects found")
            return {'CANCELLED'}
        if len(mesh_objects) > self.max_objects:
            self.report(
                {'ERROR'},
                f"Visible mesh count ({len(mesh_objects)}) exceeds Max Objects ({self.max_objects})",
            )
            return {'CANCELLED'}

        if self.use_selected_as_seed:
            seeds = [obj for obj in context.selected_objects if obj.type == 'MESH']
        else:
            seeds = [context.active_object] if context.active_object and context.active_object.type == 'MESH' else []

        if not seeds:
            self.report({'ERROR'}, "Select at least one mesh object (or set active mesh object)")
            return {'CANCELLED'}

        bounds = {obj: _world_aabb(obj) for obj in mesh_objects}
        selected_set = set(seeds)
        frontier = list(seeds)

        while frontier:
            current = frontier.pop()
            current_bounds = bounds[current]
            for candidate in mesh_objects:
                if candidate in selected_set:
                    continue
                if _aabb_distance(current_bounds, bounds[candidate]) <= self.threshold:
                    selected_set.add(candidate)
                    frontier.append(candidate)

        if self.replace_selection:
            bpy.ops.object.select_all(action='DESELECT')

        for obj in selected_set:
            obj.select_set(True)

        self.report({'INFO'}, f"Selected {len(selected_set)} touching mesh objects")
        return {'FINISHED'}


class OpenCTMSplitLoosePartsObjectMode(bpy.types.Operator):
    """Split connected components into separate objects without entering Edit Mode"""
    bl_idname = "object.openctm_split_loose_parts_object_mode"
    bl_label = "OpenCTM Split Loose Parts (Object Mode)"
    bl_options = {'REGISTER', 'UNDO'}

    min_faces_per_part: IntProperty(
        name="Min Faces Per Part",
        description="Skip tiny fragments smaller than this face count",
        default=1,
        min=1,
        max=1000000,
    )
    max_parts: IntProperty(
        name="Max Parts",
        description="Safety cap to avoid creating too many objects (keeps largest components if exceeded)",
        default=20000,
        min=10,
        max=50000,
    )
    delete_source_object: BoolProperty(
        name="Delete Source Object",
        description="Delete original mesh after split",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "min_faces_per_part")
        layout.prop(self, "max_parts")
        layout.prop(self, "delete_source_object")

    def execute(self, context):
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        source_obj = context.active_object
        if source_obj is None or source_obj.type != 'MESH':
            self.report({'ERROR'}, "Select one mesh object")
            return {'CANCELLED'}

        source_mesh = source_obj.data
        poly_count = len(source_mesh.polygons)
        if poly_count == 0:
            self.report({'ERROR'}, "Source mesh has no faces")
            return {'CANCELLED'}

        # Build face adjacency via shared edges.
        edge_to_faces = collections.defaultdict(list)
        for poly in source_mesh.polygons:
            for ek in poly.edge_keys:
                edge_to_faces[ek].append(poly.index)

        adjacency = [[] for _ in range(poly_count)]
        for face_indices in edge_to_faces.values():
            if len(face_indices) < 2:
                continue
            for i in range(len(face_indices)):
                a = face_indices[i]
                for j in range(i + 1, len(face_indices)):
                    b = face_indices[j]
                    adjacency[a].append(b)
                    adjacency[b].append(a)

        visited = [False] * poly_count
        components = []
        for face_idx in range(poly_count):
            if visited[face_idx]:
                continue
            queue = collections.deque([face_idx])
            visited[face_idx] = True
            comp = []
            while queue:
                current = queue.popleft()
                comp.append(current)
                for nb in adjacency[current]:
                    if not visited[nb]:
                        visited[nb] = True
                        queue.append(nb)
            if len(comp) >= self.min_faces_per_part:
                components.append(comp)

        if not components:
            self.report({'ERROR'}, "No components found with current Min Faces setting")
            return {'CANCELLED'}
        if len(components) > self.max_parts:
            components.sort(key=len, reverse=True)
            dropped = len(components) - self.max_parts
            components = components[:self.max_parts]
            self.report(
                {'WARNING'},
                f"Component count exceeded Max Parts; processing largest {self.max_parts} components and skipping {dropped}",
            )

        created_objects = []
        src_vertices = source_mesh.vertices
        src_polys = source_mesh.polygons

        for idx, comp_faces in enumerate(components, start=1):
            used_verts = set()
            for f_idx in comp_faces:
                used_verts.update(src_polys[f_idx].vertices)

            vert_map = {}
            vertices = []
            for old_vid in sorted(used_verts):
                vert_map[old_vid] = len(vertices)
                vertices.append(tuple(src_vertices[old_vid].co))

            faces = []
            for f_idx in comp_faces:
                old_face = src_polys[f_idx]
                faces.append([vert_map[v] for v in old_face.vertices])

            new_mesh = bpy.data.meshes.new(name=f"{source_mesh.name}_part_{idx:04d}")
            new_mesh.from_pydata(vertices, [], faces)
            new_mesh.update()

            new_obj = bpy.data.objects.new(name=f"{source_obj.name}_part_{idx:04d}", object_data=new_mesh)
            new_obj.matrix_world = source_obj.matrix_world.copy()
            _link_like_source(source_obj, new_obj, context)
            created_objects.append(new_obj)

        if self.delete_source_object:
            old_mesh = source_obj.data
            bpy.data.objects.remove(source_obj, do_unlink=True)
            if old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
        else:
            source_obj.hide_set(True)
            source_obj.hide_render = True

        bpy.ops.object.select_all(action='DESELECT')
        for obj in created_objects:
            obj.select_set(True)
        context.view_layer.objects.active = created_objects[0]

        self.report({'INFO'}, f"Created {len(created_objects)} mesh objects from loose parts")
        return {'FINISHED'}


class OpenCTMMakePrintableSolid(bpy.types.Operator):
    """Create a printable watertight mesh, optionally preserving selected openings"""
    bl_idname = "object.openctm_make_printable_solid"
    bl_label = "OpenCTM Make Printable Solid"
    bl_options = {'REGISTER', 'UNDO'}

    voxel_size: FloatProperty(
        name="Voxel Size",
        description="Lower values preserve more detail but are heavier to compute",
        default=0.01,
        min=0.0001,
        soft_max=1.0,
        subtype='DISTANCE',
    )
    adaptivity: FloatProperty(
        name="Adaptivity",
        description="Higher values reduce triangle count but lose detail",
        default=0.0,
        min=0.0,
        max=1.0,
    )
    auto_adjust_voxel_size: BoolProperty(
        name="Auto Adjust Voxel Size",
        description="Automatically increase voxel size when estimated voxel grid is too large",
        default=True,
    )
    max_voxel_cells: IntProperty(
        name="Max Voxel Cells",
        description="Safety limit for estimated voxel grid cells to avoid huge RAM usage",
        default=4000000,
        min=100000,
        soft_max=20000000,
    )
    max_estimated_memory_gb: FloatProperty(
        name="Max Estimated Memory (GB)",
        description="Abort if estimated voxel memory exceeds this budget",
        default=8.0,
        min=0.5,
        max=64.0,
    )
    max_opening_faces: IntProperty(
        name="Max Opening Faces",
        description="Safety limit for selected opening faces to avoid heavy boolean crashes",
        default=5000,
        min=50,
        max=200000,
    )
    preserve_selected_openings: BoolProperty(
        name="Preserve Selected Openings",
        description="Keep selected faces open after remesh (select openings in Edit Mode before running)",
        default=True,
    )
    opening_thickness: FloatProperty(
        name="Opening Thickness",
        description="Thickness applied to selected opening faces for robust boolean cutters",
        default=0.02,
        min=0.0001,
        soft_max=1.0,
        subtype='DISTANCE',
    )
    keep_original: BoolProperty(
        name="Keep Original",
        description="Create a new printable object and keep the source unchanged",
        default=True,
    )
    keep_cutter_object: BoolProperty(
        name="Keep Cutter",
        description="Keep generated cutter object for inspection/debugging",
        default=False,
    )
    boolean_solver: EnumProperty(
        name="Boolean Solver",
        description="FAST is less robust but much lower memory than EXACT",
        items=[
            ("FAST", "FAST", "Lower memory usage, recommended for large meshes"),
            ("EXACT", "EXACT", "More robust but can be very memory heavy"),
        ],
        default="FAST",
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "voxel_size")
        layout.prop(self, "adaptivity")
        layout.prop(self, "auto_adjust_voxel_size")
        layout.prop(self, "max_voxel_cells")
        layout.prop(self, "max_estimated_memory_gb")
        layout.prop(self, "preserve_selected_openings")
        if self.preserve_selected_openings:
            layout.prop(self, "max_opening_faces")
            layout.prop(self, "opening_thickness")
            layout.prop(self, "boolean_solver")
            layout.prop(self, "keep_cutter_object")
        layout.prop(self, "keep_original")

    def execute(self, context):
        source_obj = context.active_object
        if source_obj is None or source_obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}

        if context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        selected_faces = [poly.index for poly in source_obj.data.polygons if poly.select]
        success, result_obj, message, level = _process_printable_object(
            context,
            source_obj,
            self,
            selected_faces,
        )
        self.report({level}, message)
        if not success:
            return {'CANCELLED'}
        _make_active_object(context, result_obj)
        return {'FINISHED'}


class OpenCTMProcessSelectedIndividually(bpy.types.Operator):
    """Process each selected mesh object with printable-solid workflow one-by-one"""
    bl_idname = "object.openctm_process_selected_individually"
    bl_label = "OpenCTM Process Selected Individually"
    bl_options = {'REGISTER', 'UNDO'}

    voxel_size: FloatProperty(name="Voxel Size", default=0.01, min=0.0001, soft_max=1.0, subtype='DISTANCE')
    adaptivity: FloatProperty(name="Adaptivity", default=0.0, min=0.0, max=1.0)
    auto_adjust_voxel_size: BoolProperty(name="Auto Adjust Voxel Size", default=True)
    max_voxel_cells: IntProperty(name="Max Voxel Cells", default=4000000, min=100000, soft_max=20000000)
    max_estimated_memory_gb: FloatProperty(name="Max Estimated Memory (GB)", default=8.0, min=0.5, max=64.0)
    preserve_selected_openings: BoolProperty(name="Preserve Selected Openings", default=False)
    max_opening_faces: IntProperty(name="Max Opening Faces", default=5000, min=50, max=200000)
    opening_thickness: FloatProperty(name="Opening Thickness", default=0.02, min=0.0001, soft_max=1.0, subtype='DISTANCE')
    keep_original: BoolProperty(name="Keep Original", default=True)
    keep_cutter_object: BoolProperty(name="Keep Cutter", default=False)
    boolean_solver: EnumProperty(
        name="Boolean Solver",
        items=[("FAST", "FAST", "Lower memory usage"), ("EXACT", "EXACT", "Higher memory usage")],
        default="FAST",
    )
    stop_on_error: BoolProperty(
        name="Stop On Error",
        description="Stop batch immediately when one object fails",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "voxel_size")
        layout.prop(self, "adaptivity")
        layout.prop(self, "auto_adjust_voxel_size")
        layout.prop(self, "max_voxel_cells")
        layout.prop(self, "max_estimated_memory_gb")
        layout.prop(self, "preserve_selected_openings")
        if self.preserve_selected_openings:
            layout.prop(self, "max_opening_faces")
            layout.prop(self, "opening_thickness")
            layout.prop(self, "boolean_solver")
            layout.prop(self, "keep_cutter_object")
        layout.prop(self, "keep_original")
        layout.prop(self, "stop_on_error")

    def execute(self, context):
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        source_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not source_objects:
            self.report({'ERROR'}, "Select one or more mesh objects")
            return {'CANCELLED'}

        successes = 0
        failures = 0
        last_output = None

        for source_obj in source_objects:
            selected_faces = [poly.index for poly in source_obj.data.polygons if poly.select]
            success, result_obj, message, level = _process_printable_object(
                context,
                source_obj,
                self,
                selected_faces,
            )
            if success:
                successes += 1
                last_output = result_obj
            else:
                failures += 1
                self.report({'WARNING'}, f"{source_obj.name}: {message}")
                if self.stop_on_error:
                    break

        if last_output is not None:
            _make_active_object(context, last_output)

        if successes == 0:
            self.report({'ERROR'}, f"No objects processed successfully. Failures: {failures}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Processed {successes} object(s); failures: {failures}")
        return {'FINISHED'}


def _build_opening_cutter(source_obj, selected_face_indices, thickness, context):
    cutter_obj = source_obj.copy()
    cutter_obj.data = source_obj.data.copy()
    cutter_obj.name = f"{source_obj.name}_opening_cutter"
    _link_like_source(source_obj, cutter_obj, context)

    bm = bmesh.new()
    try:
        bm.from_mesh(cutter_obj.data)
        selected_set = set(selected_face_indices)
        faces_to_remove = [f for f in bm.faces if f.index not in selected_set]
        if faces_to_remove:
            bmesh.ops.delete(bm, geom=faces_to_remove, context='FACES')
        if not bm.faces:
            bmesh.free()
            bpy.data.objects.remove(cutter_obj, do_unlink=True)
            return None
        bm.to_mesh(cutter_obj.data)
    finally:
        if bm.is_valid:
            bm.free()

    solidify_mod = cutter_obj.modifiers.new(name="CTM_OpeningSolidify", type='SOLIDIFY')
    solidify_mod.thickness = thickness
    solidify_mod.offset = 0.0
    solidify_mod.use_even_offset = True
    _apply_modifier(context, cutter_obj, solidify_mod.name)
    return cutter_obj


def _link_like_source(source_obj, obj_to_link, context):
    if source_obj.users_collection:
        for collection in source_obj.users_collection:
            collection.objects.link(obj_to_link)
    else:
        context.scene.collection.objects.link(obj_to_link)


def _make_active_object(context, obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj


def _process_printable_object(context, source_obj, settings, selected_faces):
    if settings.preserve_selected_openings and len(selected_faces) > settings.max_opening_faces:
        return (
            False,
            None,
            (
                f"Too many selected opening faces ({len(selected_faces):,}). "
                f"Reduce selection or increase Max Opening Faces."
            ),
            'ERROR',
        )

    created_work_obj = False
    if settings.keep_original:
        work_obj = source_obj.copy()
        work_obj.data = source_obj.data.copy()
        work_obj.name = f"{source_obj.name}_printable"
        _link_like_source(source_obj, work_obj, context)
        created_work_obj = True
    else:
        work_obj = source_obj

    cutter_obj = None
    try:
        if settings.preserve_selected_openings and selected_faces:
            cutter_obj = _build_opening_cutter(
                source_obj,
                selected_faces,
                settings.opening_thickness,
                context,
            )
        elif settings.preserve_selected_openings and not selected_faces:
            raise RuntimeError("No faces selected for openings; result would be fully closed")

        safe_voxel_size, est_cells, est_memory_gb, auto_adjusted = _safe_voxel_size_for_object(
            work_obj,
            settings.voxel_size,
            settings.max_voxel_cells,
            settings.max_estimated_memory_gb,
            settings.auto_adjust_voxel_size,
        )
        if safe_voxel_size is None:
            recommended = _recommended_voxel_size(work_obj, settings.max_voxel_cells)
            raise RuntimeError(
                (
                    f"Unsafe remesh estimate ({est_cells:,} cells, ~{est_memory_gb:.1f} GB). "
                    f"Increase Voxel Size to at least ~{recommended:.4f} or raise Max Voxel Cells."
                )
            )

        remesh_mod = work_obj.modifiers.new(name="CTM_PrintRemesh", type='REMESH')
        remesh_mod.mode = 'VOXEL'
        remesh_mod.voxel_size = safe_voxel_size
        remesh_mod.adaptivity = settings.adaptivity
        remesh_mod.use_remove_disconnected = False
        if hasattr(remesh_mod, "use_smooth_shade"):
            remesh_mod.use_smooth_shade = False

        if not _apply_modifier(context, work_obj, remesh_mod.name):
            raise RuntimeError("Failed to apply voxel remesh modifier")

        if cutter_obj is not None:
            bool_mod = work_obj.modifiers.new(name="CTM_PreserveOpenings", type='BOOLEAN')
            bool_mod.object = cutter_obj
            bool_mod.operation = 'DIFFERENCE'
            if hasattr(bool_mod, "solver"):
                bool_mod.solver = settings.boolean_solver

            if not _apply_modifier(context, work_obj, bool_mod.name):
                raise RuntimeError("Failed to apply openings boolean modifier")

        if cutter_obj is not None and not settings.keep_cutter_object:
            cutter_mesh = cutter_obj.data
            bpy.data.objects.remove(cutter_obj, do_unlink=True)
            if cutter_mesh and cutter_mesh.users == 0:
                bpy.data.meshes.remove(cutter_mesh)

        if auto_adjusted:
            return (
                True,
                work_obj,
                (
                    f"Printable mesh ready: {work_obj.name}. "
                    f"Voxel Size auto-adjusted to {safe_voxel_size:.4f} "
                    f"(~{est_cells:,} cells, ~{est_memory_gb:.1f} GB)."
                ),
                'WARNING',
            )
        return True, work_obj, f"Printable mesh ready: {work_obj.name}", 'INFO'

    except RuntimeError as exc:
        if cutter_obj is not None and cutter_obj.name in bpy.data.objects and not settings.keep_cutter_object:
            cutter_mesh = cutter_obj.data
            bpy.data.objects.remove(cutter_obj, do_unlink=True)
            if cutter_mesh and cutter_mesh.users == 0:
                bpy.data.meshes.remove(cutter_mesh)
        if created_work_obj and work_obj.name in bpy.data.objects:
            work_mesh = work_obj.data
            bpy.data.objects.remove(work_obj, do_unlink=True)
            if work_mesh and work_mesh.users == 0:
                bpy.data.meshes.remove(work_mesh)
        return False, None, str(exc), 'ERROR'
    except Exception as exc:
        if cutter_obj is not None and cutter_obj.name in bpy.data.objects and not settings.keep_cutter_object:
            cutter_mesh = cutter_obj.data
            bpy.data.objects.remove(cutter_obj, do_unlink=True)
            if cutter_mesh and cutter_mesh.users == 0:
                bpy.data.meshes.remove(cutter_mesh)
        if created_work_obj and work_obj.name in bpy.data.objects:
            work_mesh = work_obj.data
            bpy.data.objects.remove(work_obj, do_unlink=True)
            if work_mesh and work_mesh.users == 0:
                bpy.data.meshes.remove(work_mesh)
        return False, None, f"Unexpected error: {exc}", 'ERROR'


def _world_aabb(obj):
    coords = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    xs = [co.x for co in coords]
    ys = [co.y for co in coords]
    zs = [co.z for co in coords]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _aabb_distance(bounds_a, bounds_b):
    (ax0, ay0, az0), (ax1, ay1, az1) = bounds_a
    (bx0, by0, bz0), (bx1, by1, bz1) = bounds_b

    dx = max(0.0, bx0 - ax1, ax0 - bx1)
    dy = max(0.0, by0 - ay1, ay0 - by1)
    dz = max(0.0, bz0 - az1, az0 - bz1)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _estimate_voxel_cells(obj, voxel_size):
    if voxel_size <= 0:
        return 0
    dims = obj.dimensions
    x = max(float(dims.x), voxel_size)
    y = max(float(dims.y), voxel_size)
    z = max(float(dims.z), voxel_size)
    nx = max(1, math.ceil(x / voxel_size))
    ny = max(1, math.ceil(y / voxel_size))
    nz = max(1, math.ceil(z / voxel_size))
    return nx * ny * nz


def _recommended_voxel_size(obj, max_voxel_cells):
    dims = obj.dimensions
    volume = max(float(dims.x), 0.000001) * max(float(dims.y), 0.000001) * max(float(dims.z), 0.000001)
    return (volume / max(max_voxel_cells, 1)) ** (1.0 / 3.0)


def _safe_voxel_size_for_object(
    obj,
    requested_voxel_size,
    max_voxel_cells,
    max_estimated_memory_gb,
    auto_adjust,
):
    # Conservative rough estimate. Real usage depends on topology/solver.
    bytes_per_cell = 128.0
    estimated = _estimate_voxel_cells(obj, requested_voxel_size)
    estimated_memory_gb = (estimated * bytes_per_cell) / (1024.0 ** 3)
    if estimated <= max_voxel_cells and estimated_memory_gb <= max_estimated_memory_gb:
        return requested_voxel_size, estimated, estimated_memory_gb, False
    if not auto_adjust:
        return None, estimated, estimated_memory_gb, False

    recommended = _recommended_voxel_size(obj, max_voxel_cells)
    # Add a small safety margin to avoid edge rounding causing limit overruns.
    adjusted = max(requested_voxel_size, recommended * 1.05)
    adjusted_estimated = _estimate_voxel_cells(obj, adjusted)
    adjusted_memory_gb = (adjusted_estimated * bytes_per_cell) / (1024.0 ** 3)
    if adjusted_estimated > max_voxel_cells or adjusted_memory_gb > max_estimated_memory_gb:
        return None, adjusted_estimated, adjusted_memory_gb, False
    return adjusted, adjusted_estimated, adjusted_memory_gb, True


def _apply_modifier(context, obj, modifier_name):
    previous_active = context.view_layer.objects.active
    previous_selection = list(context.selected_objects)
    previous_mode = context.object.mode if context.object else 'OBJECT'

    try:
        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier_name)
        return True
    except RuntimeError:
        return False
    finally:
        bpy.ops.object.select_all(action='DESELECT')
        for selected in previous_selection:
            if selected.name in bpy.data.objects:
                selected.select_set(True)
        if previous_active and previous_active.name in bpy.data.objects:
            context.view_layer.objects.active = previous_active
        if context.object and previous_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode=previous_mode)
            except RuntimeError:
                pass

def register():
    bpy.utils.register_class(OpenCTMImport)
    bpy.utils.register_class(OpenCTMExport)
    bpy.utils.register_class(OpenCTMSplitLoosePartsObjectMode)
    bpy.utils.register_class(OpenCTMSelectTouchingPanels)
    bpy.utils.register_class(OpenCTMMakePrintableSolid)
    bpy.utils.register_class(OpenCTMProcessSelectedIndividually)

def unregister():
    bpy.utils.unregister_class(OpenCTMProcessSelectedIndividually)
    bpy.utils.unregister_class(OpenCTMMakePrintableSolid)
    bpy.utils.unregister_class(OpenCTMSelectTouchingPanels)
    bpy.utils.unregister_class(OpenCTMSplitLoosePartsObjectMode)
    bpy.utils.unregister_class(OpenCTMExport)
    bpy.utils.unregister_class(OpenCTMImport)

def _encode(_filename):
    try:
        return str(_filename).encode("utf-8")
    except UnicodeEncodeError:
        pass
