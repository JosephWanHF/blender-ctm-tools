"""End-to-end mapper handoff test; run with Blender's Python in background."""
import bpy, bmesh, sys, json, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'addons'));import ctm_part_mapper as a;a.register()
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);bpy.ops.mesh.primitive_cube_add(size=2);source=bpy.context.object
source.data.uv_layers.new(name='Keep UVs')
bpy.context.scene.unit_settings.scale_length=.001
assert bpy.ops.ctm_map.prepare(target_mm=100)=={'FINISHED'}
o=bpy.context.object;assert bpy.ops.ctm_map.add()=={'FINISHED'};assert bpy.ops.ctm_map.add()=={'FINISHED'}
o.ctm_parts[0].name='Hull';o.ctm_parts[0].description='Human note';o.ctm_parts[0].status='REVIEW'
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='DESELECT');bm=bmesh.from_edit_mesh(o.data);bm.faces.ensure_lookup_table();bm.select_mode={'FACE'};bm.faces[0].select_set(True);bmesh.update_edit_mesh(o.data);o.ctm_part_index=1;assert bpy.ops.ctm_map.assign()=={'FINISHED'}
bpy.ops.mesh.select_all(action='DESELECT');bm.faces[1].select_set(True);bmesh.update_edit_mesh(o.data);o.ctm_part_index=0;assert bpy.ops.ctm_map.expand_islands()=={'FINISHED'}
assert not bm.faces[0].select, 'protected assigned face should not be selected'
assert sum(f.select for f in bm.faces)==5
assert bpy.ops.ctm_map.assign()=={'FINISHED'};layer=bm.faces.layers.int['ctm_part_id'];assert bm.faces[0][layer]==2 and all(f[layer]==1 for f in list(bm.faces)[1:])
bpy.ops.object.mode_set(mode='OBJECT');prior=[x.value for x in o.data.attributes['ctm_part_id'].data]
assert bpy.ops.ctm_map.extract_part()=={'FINISHED'}
ex=bpy.data.objects['Hull - reference'];assert len(ex.data.polygons)==5 and 'Keep UVs' in ex.data.uv_layers
assert [x.value for x in o.data.attributes['ctm_part_id'].data]==prior
with tempfile.TemporaryDirectory() as d:
 path=str(Path(d)/'report.json');assert bpy.ops.ctm_map.export_report(filepath=path)=={'FINISHED'}
 data=json.loads(Path(path).read_text());assert data['total_faces']==6 and data['unassigned_faces']==0
 assert data['parts'][0]['face_count']==5 and data['parts'][0]['notes']=='Human note' and data['parts'][0]['mapping_status']=='REVIEW'
 assert data['parts'][0]['bounds_world_mm']['max']==[50.0,50.0,50.0]
print('MAPPING_HANDOFF_PASS')
