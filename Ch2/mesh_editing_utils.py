# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import bmesh

def get_placeholder_mesh_obj_and_bm(context, name, location):
    mesh_placeholder = bpy.data.meshes.new(name=name)
    obj_placeholder = bpy.data.objects.new(name=name, object_data=mesh_placeholder)
    obj_placeholder.location = location
    context.collection.objects.link(obj_placeholder)
    for o in context.scene.objects:
        o.select_set(False)
    context.view_layer.objects.active = obj_placeholder
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(mesh_placeholder)
    return bm, obj_placeholder

#========= Accessing Edge Loops =============================
def get_edge_loops(bm, ref_edges, select_rings=False):
    loops = []
    for re in ref_edges:
        bpy.ops.mesh.select_all(action='DESELECT')
        re.select = True
        bpy.ops.mesh.loop_multi_select(ring=select_rings)
        this_loop = []
        for e in bm.edges:
            if e.select:
                this_loop.append(e)
        loops.append(this_loop)
    bpy.ops.mesh.select_all(action='DESELECT')
    return loops

def select_edge_loops(bm, ref_edges, select_rings=False):
    bpy.ops.mesh.select_all(action='DESELECT')
    for re in ref_edges:
        re.select = True
    bpy.ops.mesh.loop_multi_select(ring=select_rings)
    
    loop_edges = []  
    for e in bm.edges:
        if e.select:
            loop_edges.append(e)
        
    return loop_edges

#========= Extrusion =========================================
def extrude_edge_loop_copy_move(bm, ref_edge, direction, scale_factor):
    select_edge_loops(bm, [ref_edge], select_rings=False)
    bpy.ops.mesh.duplicate()
    bpy.ops.transform.translate(value=direction)
    bpy.ops.transform.resize(value=scale_factor)

    new_edge_loop = []
    for e in bm.edges:
        if e.select:
            new_edge_loop.append(e)

    select_edge_loops(bm, [new_edge_loop[0], ref_edge])
    bpy.ops.mesh.bridge_edge_loops()
    for e in new_edge_loop:
        e.select = False
    return new_edge_loop

def loop_extrude_region_move(bm, ref_edge, direction):
    select_edge_loops(bm, [ref_edge], select_rings = False)
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": direction})
