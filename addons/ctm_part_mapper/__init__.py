bl_info = {'name': 'CTM Part Mapper', 'author': 'Codex', 'version': (0, 1, 0), 'blender': (4, 2, 0), 'location': '3D View > Sidebar > CTM Map', 'description': 'Label source faces into human-defined parts', 'category': 'Mesh'}
import bpy, bmesh, colorsys, json, collections
from bpy_extras.io_utils import ExportHelper
from collections import deque
from mathutils import Matrix
from bpy.props import StringProperty, FloatVectorProperty, FloatProperty, IntProperty, CollectionProperty

ID_LAYER = 'ctm_part_id'
COLOR_LAYER = 'ctm_part_color'

class CTMMAP_Part(bpy.types.PropertyGroup):
    name: StringProperty(name='Name', default='New part')
    label_id: IntProperty()
    description: StringProperty(name='Notes', description='Human description, role or uncertainty')
    status: bpy.props.EnumProperty(name='Mapping status', items=[('DRAFT','Draft','Mapping is in progress'),('REVIEW','Needs review','Ready for review'),('CONFIRMED','Confirmed','Human has reviewed this mapping')], default='DRAFT')
    color: FloatVectorProperty(name='Colour', subtype='COLOR', size=4, min=0, max=1, default=(0.8, 0.35, 0.15, 1))

class CTMMAP_UL_parts(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'color', text='')
        layout.prop(item, 'name', text='', emboss=False)

def active_map(context):
    obj = context.active_object
    return obj if obj and obj.type == 'MESH' and obj.get('ctm_mapper_version') else None

def active_part(obj):
    return obj.ctm_parts[obj.ctm_part_index] if 0 <= obj.ctm_part_index < len(obj.ctm_parts) else None

def edit_mesh(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    return bm, bm.faces.layers.int.get(ID_LAYER), bm.loops.layers.color.get(COLOR_LAYER)

def recolor(obj, bm, layer, colors):
    palette = {p.label_id: tuple(p.color) for p in obj.ctm_parts}
    for face in bm.faces:
        c = palette.get(face[layer], (0.32, 0.32, 0.32, 1.0))
        for loop in face.loops: loop[colors] = c
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

class CTMMAP_OT_prepare(bpy.types.Operator):
    bl_idname = 'ctm_map.prepare'; bl_label = 'Prepare Mapping Copy'; bl_options = {'REGISTER', 'UNDO'}
    target_mm: FloatProperty(name='Target longest dimension (mm)', default=875.0, min=0.001, description='Set to the desired size of the whole model; creates a scaled copy')
    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object and context.active_object.type == 'MESH'
    def execute(self, context):
        src = context.active_object
        if src.get('ctm_mapper_version'):
            self.report({'ERROR'}, 'Select the original mesh, not an existing mapping copy'); return {'CANCELLED'}
        if not src.data.polygons:
            self.report({'ERROR'}, 'The selected mesh has no faces'); return {'CANCELLED'}
        if ID_LAYER in src.data.attributes or COLOR_LAYER in src.data.attributes:
            self.report({'ERROR'}, 'Source already has reserved mapping attributes'); return {'CANCELLED'}
        if context.scene.unit_settings.scale_length <= 0:
            self.report({'ERROR'}, 'Scene unit scale must be positive'); return {'CANCELLED'}
        linear = src.matrix_world.to_3x3().to_4x4()
        coords = [linear @ v.co for v in src.data.vertices]
        longest = max(max(v[i] for v in coords)-min(v[i] for v in coords) for i in range(3))
        if longest <= 0:
            self.report({'ERROR'}, 'Source has zero size'); return {'CANCELLED'}
        target_units = (self.target_mm / 1000.0) / context.scene.unit_settings.scale_length
        factor = target_units / longest
        obj = src.copy(); obj.data = src.data.copy(); obj.name = src.name + ' - Mapping'; context.collection.objects.link(obj)
        obj.data.transform(Matrix.Scale(factor, 4) @ linear)
        obj.matrix_world = Matrix.Translation(src.matrix_world.translation)
        obj['ctm_mapper_version'] = 1; obj['ctm_target_longest_mm'] = self.target_mm; obj['ctm_source_name'] = src.name
        obj.data.attributes.new(ID_LAYER, 'INT', 'FACE')
        col = obj.data.color_attributes.new(name=COLOR_LAYER, type='BYTE_COLOR', domain='CORNER')
        for d in col.data: d.color = (0.32, 0.32, 0.32, 1.0)
        obj.data.color_attributes.active_color = col
        bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); context.view_layer.objects.active = obj
        src.hide_set(True); src.hide_render = True
        if context.area and context.area.type == 'VIEW_3D': context.space_data.shading.color_type = 'VERTEX'
        self.report({'INFO'}, 'Mapping copy created; original hidden. Set solid shading colour to Attribute if needed.')
        return {'FINISHED'}

class CTMMAP_OT_add(bpy.types.Operator):
    bl_idname = 'ctm_map.add'; bl_label = 'Add Part'; bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return active_map(context) is not None
    def execute(self, context):
        obj=active_map(context); ident=max([p.label_id for p in obj.ctm_parts],default=0)+1
        p=obj.ctm_parts.add();p.label_id=ident;p.name=f'Part {ident:02d}';p.color=(*colorsys.hsv_to_rgb((ident*.61803398875)%1,.65,.9),1);obj.ctm_part_index=len(obj.ctm_parts)-1
        return {'FINISHED'}

class CTMMAP_OT_expand(bpy.types.Operator):
    bl_idname='ctm_map.expand_islands';bl_label='Expand to Connected Islands';bl_description='Expand selected faces across shared edges on visible geometry';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context): return context.mode == 'EDIT_MESH' and active_map(context) is not None
    def execute(self,context):
        obj=active_map(context);bm,layer,colors=edit_mesh(obj);seed=[f for f in bm.faces if f.select and not f.hide]
        if not seed:self.report({'WARNING'},'Select at least one visible face first');return {'CANCELLED'}
        part=active_part(obj)
        if context.scene.ctm_map_protect_other_parts:
            allowed={0}
            if part: allowed.add(part.label_id)
            blocked=[f for f in seed if f[layer] not in allowed]
            seed=[f for f in seed if f[layer] in allowed]
            if not seed:
                self.report({'WARNING'}, 'No selected faces are unassigned or in the active part');return {'CANCELLED'}
        else: allowed=None
        if allowed is not None:
            for f in blocked:f.select_set(False)
        visited=set(seed);q=deque(seed)
        while q:
            for e in q.popleft().edges:
                for face in e.link_faces:
                    if not face.hide and face not in visited and (allowed is None or face[layer] in allowed):visited.add(face);q.append(face)
        for f in visited:f.select_set(True)
        bm.select_flush_mode();bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
        self.report({'INFO'},f'Selected {len(visited)} faces; review before assigning');return {'FINISHED'}

class CTMMAP_OT_assign(bpy.types.Operator):
    bl_idname='ctm_map.assign';bl_label='Assign Selected';bl_options={'REGISTER','UNDO'}
    erase: bpy.props.BoolProperty(default=False)
    @classmethod
    def poll(cls,context): return context.mode == 'EDIT_MESH' and active_map(context) is not None
    def execute(self,context):
        obj=active_map(context);p=active_part(obj);bm,layer,colors=edit_mesh(obj)
        if not self.erase and not p:self.report({'ERROR'},'Add a part first');return {'CANCELLED'}
        selected=[f for f in bm.faces if f.select and not f.hide]
        if not selected:self.report({'WARNING'},'Select visible faces first');return {'CANCELLED'}
        for f in selected:f[layer]=0 if self.erase else p.label_id
        recolor(obj,bm,layer,colors);self.report({'INFO'},f'Updated {len(selected)} faces');return {'FINISHED'}

class CTMMAP_OT_refresh(bpy.types.Operator):
    bl_idname='ctm_map.refresh';bl_label='Refresh Colours';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='EDIT_MESH' and active_map(context) is not None
    def execute(self,context):
        obj=active_map(context);bm,layer,colors=edit_mesh(obj);recolor(obj,bm,layer,colors);return {'FINISHED'}

class CTMMAP_OT_select(bpy.types.Operator):
    bl_idname='ctm_map.select_part';bl_label='Select Active Part';bl_options={'REGISTER','UNDO'}
    unassigned: bpy.props.BoolProperty(default=False)
    @classmethod
    def poll(cls,context):return context.mode=='EDIT_MESH' and active_map(context) is not None
    def execute(self,context):
        obj=active_map(context);p=active_part(obj)
        if not self.unassigned and not p:self.report({'ERROR'},'Add or select a part first');return {'CANCELLED'}
        bm,layer,colors=edit_mesh(obj);ident=0 if self.unassigned else p.label_id
        for f in bm.faces:f.select_set(not f.hide and f[layer]==ident)
        bm.select_flush_mode();bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False);return {'FINISHED'}

class CTMMAP_OT_visibility(bpy.types.Operator):
    bl_idname='ctm_map.visibility';bl_label='Part Visibility';bl_options={'REGISTER','UNDO'}
    action: bpy.props.EnumProperty(items=[('HIDE','Hide Active',''),('ISOLATE','Isolate Active',''),('UNASSIGNED','Show Unassigned',''),('REVEAL','Reveal All','')])
    @classmethod
    def poll(cls,context):return context.mode=='EDIT_MESH' and active_map(context) is not None
    def execute(self,context):
        obj=active_map(context);p=active_part(obj);bm,layer,colors=edit_mesh(obj)
        if self.action in {'HIDE','ISOLATE'} and not p:self.report({'ERROR'},'Select a part first');return {'CANCELLED'}
        for f in bm.faces:
            if self.action=='HIDE' and f[layer]==p.label_id:f.hide_set(True)
            elif self.action=='ISOLATE':f.hide_set(f[layer]!=p.label_id)
            elif self.action=='UNASSIGNED':f.hide_set(f[layer]!=0)
            elif self.action=='REVEAL':f.hide_set(False)
        bm.select_flush_mode();bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False);return {'FINISHED'}

class CTMMAP_OT_extract(bpy.types.Operator):
    """Create a reference copy of the active part, preserving mesh layers and source position"""
    bl_idname='ctm_map.extract_part';bl_label='Extract Active Part Copy';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and active_map(context) is not None
    def execute(self,context):
        obj=active_map(context);part=active_part(obj)
        if not part:self.report({'ERROR'},'Select a part first');return {'CANCELLED'}
        bm=bmesh.new();bm.from_mesh(obj.data);layer=bm.faces.layers.int.get(ID_LAYER)
        if not layer:bm.free();self.report({'ERROR'},'Mapping face IDs are missing');return {'CANCELLED'}
        keep=sum(f[layer]==part.label_id for f in bm.faces)
        if not keep:bm.free();self.report({'WARNING'},'This part has no faces');return {'CANCELLED'}
        remove=[f for f in bm.faces if f[layer]!=part.label_id]
        bmesh.ops.delete(bm,geom=remove,context='FACES')
        orphan=[v for v in bm.verts if not v.link_faces]
        if orphan:bmesh.ops.delete(bm,geom=orphan,context='VERTS')
        new_mesh=obj.data.copy();bm.to_mesh(new_mesh);bm.free();new_mesh.update()
        copy=bpy.data.objects.new(part.name+' - reference',new_mesh);context.collection.objects.link(copy);copy.matrix_world=obj.matrix_world.copy()
        copy['ctm_reference_only']=True;copy['ctm_source_part_id']=part.label_id;copy['ctm_source_object']=obj.name
        self.report({'INFO'},f'Created reference copy of {keep} faces; original mapping is unchanged')
        return {'FINISHED'}

class CTMMAP_OT_report(bpy.types.Operator,ExportHelper):
    """Export part labels, human notes and world-space bounds for an agent or reviewer"""
    bl_idname='ctm_map.export_report';bl_label='Export Mapping Report';filename_ext='.json'
    filter_glob: StringProperty(default='*.json',options={'HIDDEN'})
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and active_map(context) is not None
    def execute(self,context):
        obj=active_map(context);mesh=obj.data;attr=mesh.attributes.get(ID_LAYER)
        if not attr:self.report({'ERROR'},'Mapping face IDs are missing');return {'CANCELLED'}
        unit_mm=context.scene.unit_settings.scale_length*1000
        data={};vertex_ids=collections.defaultdict(set)
        for face in mesh.polygons:
            label=attr.data[face.index].value
            data[label]=data.get(label,0)+1;vertex_ids[label].update(face.vertices)
        entries=[]
        for p in obj.ctm_parts:
            pts=[obj.matrix_world @ mesh.vertices[v].co for v in vertex_ids.get(p.label_id,())]
            bounds=None
            if pts:
                bounds={'min':[round(min(v[i] for v in pts)*unit_mm,4) for i in range(3)],'max':[round(max(v[i] for v in pts)*unit_mm,4) for i in range(3)]}
            entries.append({'id':p.label_id,'name':p.name,'notes':p.description,'mapping_status':p.status,'face_count':data.get(p.label_id,0),'bounds_world_mm':bounds,'color_rgba':list(p.color)})
        known={p.label_id for p in obj.ctm_parts}
        report={'schema_version':1,'kind':'human_labelled_reference_mesh','blend_file':bpy.data.filepath or None,'mapping_object':obj.name,'source_object':obj.get('ctm_source_name'),'scale_basis':'Blender scene unit scale; world coordinates in mm','target_longest_mm_at_preparation':obj.get('ctm_target_longest_mm'),'total_faces':len(mesh.polygons),'unassigned_faces':data.get(0,0),'unknown_label_face_counts':{str(k):v for k,v in data.items() if k!=0 and k not in known},'parts':entries,'limitations':['Labels are human-selected reference faces, not verified complete assemblies or printable solids.','Bounds are axis-aligned world-space extents, not dimensions of a fitted joint.','Face indices and labels can change if topology is edited.']}
        try:
            with open(self.filepath,'w',encoding='utf-8') as output:json.dump(report,output,indent=2,ensure_ascii=False)
        except OSError as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},f'Exported {len(entries)} parts to {self.filepath}');return {'FINISHED'}

class CTMMAP_PT_panel(bpy.types.Panel):
    bl_label='CTM Part Mapper';bl_idname='CTMMAP_PT_panel';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='CTM Map'
    def draw(self,context):
        layout=self.layout;obj=active_map(context)
        if not obj:
            layout.label(text='Select the imported mesh in Object Mode.')
            layout.prop(context.scene, 'ctm_map_target_mm')
            op=layout.operator('ctm_map.prepare',icon='DUPLICATE');op.target_mm=context.scene.ctm_map_target_mm
            return
        layout.label(text='Mapping copy: '+obj.name,icon='MESH_DATA')
        row=layout.row();row.template_list('CTMMAP_UL_parts','',obj,'ctm_parts',obj,'ctm_part_index',rows=3);row.column().operator('ctm_map.add',text='',icon='ADD')
        part=active_part(obj)
        if part:
            layout.label(text='Active part: '+part.name, icon='CHECKMARK')
            layout.prop(part,'status');layout.prop(part,'description')
        if context.mode!='EDIT_MESH':
            layout.label(text='Enter Edit Mode, then select faces.')
            layout.operator('ctm_map.extract_part',icon='DUPLICATE')
            layout.operator('ctm_map.export_report',icon='EXPORT')
            return
        layout.label(text='Face select, box B, lasso Ctrl-drag.')
        layout.prop(context.scene,'ctm_map_protect_other_parts')
        layout.operator('ctm_map.expand_islands',icon='SELECT_EXTEND')
        row=layout.row(align=True);op=row.operator('ctm_map.assign',text='Assign');op.erase=False;op=row.operator('ctm_map.assign',text='Unassign');op.erase=True
        row=layout.row(align=True);op=row.operator('ctm_map.select_part',text='Select Part');op.unassigned=False;op=row.operator('ctm_map.select_part',text='Select Unassigned');op.unassigned=True
        row=layout.row(align=True);op=row.operator('ctm_map.visibility',text='Hide Part');op.action='HIDE';op=row.operator('ctm_map.visibility',text='Isolate');op.action='ISOLATE'
        row=layout.row(align=True);op=row.operator('ctm_map.visibility',text='Unassigned Only');op.action='UNASSIGNED';op=row.operator('ctm_map.visibility',text='Reveal All');op.action='REVEAL'
        layout.operator('ctm_map.refresh',icon='FILE_REFRESH');layout.label(text='Change part colours, then refresh.')
        layout.label(text='Solid shading: Colour > Attribute')

CLASSES=(CTMMAP_Part,CTMMAP_UL_parts,CTMMAP_OT_prepare,CTMMAP_OT_add,CTMMAP_OT_expand,CTMMAP_OT_assign,CTMMAP_OT_refresh,CTMMAP_OT_select,CTMMAP_OT_visibility,CTMMAP_OT_extract,CTMMAP_OT_report,CTMMAP_PT_panel)
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Object.ctm_parts=CollectionProperty(type=CTMMAP_Part)
    bpy.types.Object.ctm_part_index=IntProperty(default=0)
    bpy.types.Scene.ctm_map_target_mm=FloatProperty(name='Target length (mm)',default=875.0,min=0.001)
    bpy.types.Scene.ctm_map_protect_other_parts=bpy.props.BoolProperty(name='Protect Other Parts',description='Do not expand selection into faces assigned to other parts',default=True)
def unregister():
    del bpy.types.Scene.ctm_map_protect_other_parts
    del bpy.types.Scene.ctm_map_target_mm
    del bpy.types.Object.ctm_part_index;del bpy.types.Object.ctm_parts
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
if __name__=='__main__':register()
