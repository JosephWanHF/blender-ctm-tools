import bpy,bmesh,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'addons'));import ctm_part_mapper as addon;addon.register()
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);bpy.ops.mesh.primitive_cube_add();bpy.ops.ctm_map.prepare(target_mm=120);o=bpy.context.object
bpy.ops.ctm_map.add();bpy.ops.ctm_map.add();o.ctm_part_index=0
bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='DESELECT');bm=bmesh.from_edit_mesh(o.data);bm.faces.ensure_lookup_table();bm.faces[0].select_set(True);bmesh.update_edit_mesh(o.data)
bpy.ops.ctm_map.assign();bm=bmesh.from_edit_mesh(o.data);bm.faces.ensure_lookup_table();bm.faces[1].select_set(True);bmesh.update_edit_mesh(o.data)
bpy.ops.ctm_map.assign(erase=True);o.ctm_part_index=1;print('AFTER_ERASE_ACTIVE_INDEX',o.ctm_part_index,'PARTS',[(x.name,x.label_id) for x in o.ctm_parts]);bpy.ops.ctm_map.assign()
bm=bmesh.from_edit_mesh(o.data);bm.faces.ensure_lookup_table();layer=bm.faces.layers.int['ctm_part_id'];print('LABELS',[(f.index,f[layer],f.select) for f in bm.faces]);assert bm.faces[0][layer]==2 and bm.faces[1][layer]==2,'mixed reassignment failed'
print('MIXED_REASSIGN_PASS')
