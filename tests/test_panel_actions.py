"""Run with Blender --background --factory-startup --python-exit-code 1 --python ..."""
import bpy, sys
from types import SimpleNamespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'addons'))
import ctm_part_mapper as addon
addon.register()
bpy.ops.mesh.primitive_cube_add();bpy.ops.ctm_map.prepare(target_mm=100);obj=bpy.context.object
bpy.ops.ctm_map.add();bpy.ops.object.mode_set(mode='EDIT')
# Exercise the actual panel's draw code with recorded prior operator settings,
# as UI button construction may retain the most recently used operator values.
class FakeLayout:
    def __init__(self): self.buttons=[]
    def row(self,**kwargs):return self
    def column(self,**kwargs):return self
    def template_list(self,*args,**kwargs):pass
    def label(self,*args,**kwargs):pass
    def prop(self,*args,**kwargs):pass
    def operator(self,name,**kwargs):
        props=SimpleNamespace(erase=True,unassigned=True,action=None)
        self.buttons.append((name,kwargs.get('text'),props));return props
layout=FakeLayout();addon.CTMMAP_PT_panel.draw(SimpleNamespace(layout=layout),bpy.context)
buttons={(n,t):p for n,t,p in layout.buttons}
assert buttons['ctm_map.assign','Assign'].erase is False, 'Assign button inherits erase=True after Unassign'
assert buttons['ctm_map.assign','Unassign'].erase is True
assert buttons['ctm_map.select_part','Select Part'].unassigned is False
assert buttons['ctm_map.select_part','Select Unassigned'].unassigned is True
print('PANEL_ACTIONS_PASS')
