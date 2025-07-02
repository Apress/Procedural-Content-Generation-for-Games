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
from enum import IntEnum, unique
from math import asin, cos, isclose, radians, sqrt
from mathutils import Matrix, Vector

import os, sys
script_dir = ""
if bpy.context.space_data and bpy.context.space_data.text:
    script_filepath = bpy.context.space_data.text.filepath
    if script_filepath:
        script_dir = os.path.dirname(script_filepath)
        if not script_dir in sys.path:
            sys.path.append(script_dir)

from mesh_editing_utils import get_placeholder_mesh_obj_and_bm, select_edge_loops, extrude_edge_loop_copy_move

unit_x = Vector((1,0,0))
unit_y = Vector((0,1,0))
    
@unique
class Side(IntEnum):
    Top = 0
    Bottom = 1
    
def add_bevel_modifier(obj, width=2, segments=3):
    bevel_mod = obj.modifiers.new(obj.name+"_bevel_mod", 'BEVEL')
    bevel_mod.affect = 'EDGES'
    bevel_mod.width = width
    bevel_mod.segments = segments
    return bevel_mod

def add_simple_deform_taper_modifier(obj):
    taper_deform_mod = obj.modifiers.new(obj.name+"_taper_simple_deform_mod", 'SIMPLE_DEFORM')
    taper_deform_mod.deform_method = 'TAPER'
    taper_deform_mod.factor = 0.135
    taper_deform_mod.deform_axis = 'X'
    return taper_deform_mod
    
def get_pos_inside_face_loop(faces, num_pos, y_width):
    ref_faces = sorted(faces, key=lambda f: max([f.verts[i].co[0] for i in range(4)]))
    
    # Take the faces at the two X extremes (largest and smallest X).
    verts_far_ends = list(ref_faces[0].verts)
    verts_far_ends.extend(ref_faces[-1].verts)
    # Take the 4 verts closest to the origin (in terms of Y), then sort them descendingly based on Z.
    verts_far_ends = sorted(verts_far_ends, key=lambda v: abs(v.co[1]))[:4]
    verts_far_ends = sorted(verts_far_ends, key=lambda v: v.co[2], reverse=True)
    # The center of the opening of the passed in face loop, is then the mid point of the average of the two verts at the opposite 
    # extremes of X, with the smallest Z and closest to the origin in terms of Y.
    center = (verts_far_ends[0].co+verts_far_ends[1].co)/2
    
    circle_radius = y_width/(num_pos*2)
    start = center - Vector((0, y_width/2-circle_radius, 0))
    pos_list = [start + Vector((0, circle_radius*2*i, 0)) for i in range(num_pos)]
    
    return center, pos_list, circle_radius

def get_y_span(faces, side, num_front_faces):
    ref_faces = sorted(faces, key=lambda f: max([f.verts[i].co[0] for i in range(4)]))
    
    end_verts = set()
    forward_most_faces = ref_faces[:num_front_faces]
    for f in forward_most_faces:
        end_verts.update(f.verts)
        
    to_reverse = True if side.value == Side.Top.value else False
    end_verts = sorted(list(end_verts), key=lambda v: v.co[2], reverse=to_reverse)[:num_front_faces+1]
    end_verts = sorted(end_verts, key=lambda v: v.co[1], reverse=to_reverse)
    span = abs(end_verts[0].co[1]-end_verts[-1].co[1])
    return end_verts[0], end_verts[-1], span

def create_finger_pull_xz(context, x_start, x_end, bm, x_offset=0, pull_thickness=1):
    num_divs = 10
    x_step = (x_end-x_start)/num_divs
    x_steps = [x_start+x_step*i for i in range(num_divs+1)]
    # Formula for parabola is z = 0.35x^2-2
    for x in x_steps:
        bmesh.ops.create_vert(bm, co=Vector((x+x_offset, 0, 0.35*x*x-2)))
    bm.verts.ensure_lookup_table()
    start_v_idx = len(bm.verts)-(num_divs+1)
    for i in range(start_v_idx, start_v_idx+num_divs, 1):
        bmesh.ops.contextual_create(bm, geom=[bm.verts[i], bm.verts[i+1]], mat_nr=0, use_smooth=False)
        
    # Duplicate the partial parabola.
    context.tool_settings.mesh_select_mode = [True, False, False]
    bm.verts.ensure_lookup_table()
    bm.verts[-1].select = True
    bpy.ops.mesh.select_linked()
    bpy.ops.mesh.duplicate_move(MESH_OT_duplicate={"mode":1}, TRANSFORM_OT_translate={"value":(0, 0, 0)})

    # Select the duplicated parabola, by selecting the last vert created, then select linked (L key).
    bpy.ops.mesh.select_all(action='DESELECT')
    bm.verts.ensure_lookup_table()
    bm.verts[-1].select = True
    bpy.ops.mesh.select_linked()
    # Rotate the duplicate by 30 deg, pivoted at the vert that coincide with the original.
    rot = Matrix.Rotation(radians(-30.0), 3, 'Y')
    bmesh.ops.rotate(bm, cent=bm.verts[-1].co, matrix=rot, verts=bm.verts[len(bm.verts)-(num_divs+1):])

    # After the rotation, the duplicate is still selected. We select the original by selecting its last vert, then select linked (L key).
    bm.verts[len(bm.verts)-(num_divs+1)-1].select = True
    bpy.ops.mesh.select_linked()

    # With both the original and the duplicate selected, Edge -> Bridge Edge Loops to add faces between then, then merge the 
    # faces into an N-gon with X (Delete) -> Dissolve Faces. We want an n-gon so it is easier to identify the opposing face 
    # and extrude it the other way. In addition, bpy.ops.mesh.edge_face_add() (F key) sometimes does not behave well.
    bpy.ops.mesh.bridge_edge_loops()
    bpy.ops.mesh.dissolve_faces()

    # Remove the vert at the tip that overlap between the original and the duplicate.
    bpy.ops.mesh.remove_doubles()
    
    # Since the face is located at the center of the trigger box, we extrude along the face normal half way, then the opposite dir half way.
    half_pull_thickness = pull_thickness/2
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value":(0, 0, half_pull_thickness), "orient_type":'NORMAL', "orient_matrix_type":'NORMAL', "constraint_axis":(False, False, True)})
    
    # After the extrusion, the verts framing the face will still be selected at the end of the extrusion. We select to Mesh Selection Mode - Face
    # so the face becomes selected.
    context.tool_settings.mesh_select_mode = [False, False, True]

    # We then find the opposite face, which is the face with its normal pointing in the opposite dir.
    # Since we removed doubles, geometry may have changed, we refresh the face indices on the bm instance.
    bm.faces.ensure_lookup_table()
    selected_f_normal = None
    selected_f_area = 0
    for f in bm.faces:
        if f.select:
            selected_f_normal = f.normal.normalized()
            selected_f_area = f.calc_area()
            break
    cos_150 = cos(radians(150))
    if selected_f_normal:
        for f in bm.faces:
            if not f.select:
                if isclose(f.calc_area(), selected_f_area, rel_tol=0.05) and f.normal.normalized().dot(selected_f_normal) < cos_150:
                    bpy.ops.mesh.select_all(action='DESELECT')
                    f.select = True
                    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value":(0, 0, half_pull_thickness), "orient_type":'NORMAL', "orient_matrix_type":'NORMAL', "constraint_axis":(False, False, True)})
                    bpy.ops.mesh.select_all(action='DESELECT')
                    break
                
#=========== PROCEDURAL GUN GENERATOR W/ PARAMETRIC CONTROLS ===========================================
def generate_gun(context, name, location=(0, 0, 0), num_cir_segments=32, grip_radius=3, num_grip_levels=6, \
    stylize=True, grip_bent_factor=1, side_rib_only=False, num_barrels=2, ratio_frame_to_grip=1.5, \
    slide_back_multiplier=1.0, grip_width_multiplier=1.75):
    
    bm, grip_obj = get_placeholder_mesh_obj_and_bm(context, name=name, location=location)
    base_radius = grip_radius*ratio_frame_to_grip
    bmesh.ops.create_circle(bm, cap_ends=False, cap_tris=False, segments=num_cir_segments, radius=base_radius)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.resize(value=(grip_width_multiplier, 1, 1), orient_type='GLOBAL', constraint_axis=(True, True, True), mirror=True, snap_target='CLOSEST', use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True)
    bpy.ops.mesh.select_all(action='DESELECT')
    
    # Make the gun barrel axis aligned to the X-axis. Group verts/edges based on location (center) of the circle
    bm.verts.ensure_lookup_table()
    base_front_verts = []
    base_back_verts = []
    curvature_threshold = (grip_width_multiplier*base_radius)*0.8
    verts_to_straighten_y = []
    for v in bm.verts:
        x_dist_from_center = abs(v.co[0])
        if v.co[0] >= 0:
            if x_dist_from_center > curvature_threshold:
                base_front_verts.append(v)
            else:
                verts_to_straighten_y.append(v)
        else:
            if x_dist_from_center > curvature_threshold:
                base_back_verts.append(v)
            else:
                verts_to_straighten_y.append(v)

    for v in verts_to_straighten_y:
        if v.co[1] > 0:
            v.select = True
    bpy.ops.transform.resize(value=(1, 0, 1), orient_type='GLOBAL', constraint_axis=(False, True, False), mirror=True, use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True)
    bpy.ops.mesh.select_all(action='DESELECT')

    for v in verts_to_straighten_y:
        if v.co[1] <= 0:
            v.select = True
    bpy.ops.transform.resize(value=(1, 0, 1), orient_type='GLOBAL', constraint_axis=(False, True, False), mirror=True, use_snap_self=True, use_snap_edit=True, use_snap_nonedit=True)
    bpy.ops.mesh.select_all(action='DESELECT')
    
    for v in base_front_verts:
        v.select = True
    base_front_scale = 1.25
    bpy.ops.transform.resize(value=(base_front_scale, 1, 1), orient_type='GLOBAL', constraint_axis=(True, False, False), mirror=True)
    bpy.ops.mesh.select_all(action='DESELECT')
    
    for v in base_back_verts:
        v.select = True
    base_back_scale = 0.7
    bpy.ops.transform.resize(value=(base_back_scale, 1, 1), orient_type='GLOBAL', constraint_axis=(True, False, False), mirror=True)
            
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.edge_face_add() # Fill with n-gon
    bm.edges.ensure_lookup_table()
    ref_edge = bm.edges[0]      

    # -------------------------- GRIP -----------------------------
    context.tool_settings.mesh_select_mode = [False, False, True]
    grip_level_height = grip_radius*1.15
    face_loop_grip_top = []
    # Extrude the given number of grip levels, then 2 additional levels for the "lip", and 1 level for transitioning into the bottom of the barrel.
    num_grip_levels = max(1, num_grip_levels) # At least one level.
    total_levels = num_grip_levels+3
    safety_loops = []
    for i in range(total_levels):
        z_offset = grip_level_height
        # Bottom of the barrel is taller.
        if i == total_levels-1:
            z_offset *= 2
        # The "lip" protroding backwards at the top of the grip is shorter per level.
        elif i >= total_levels-3 and i < total_levels-1:
            z_offset = grip_level_height*0.35
        # stylize is when grip curves (+X, then -X num_grip_levels-1, then lip +X,-X.
        if stylize:            
            skew = 5 if i==total_levels-2 else grip_radius*0.5*grip_bent_factor
            direction = Vector((-skew, 0, z_offset))
            if i==0 or i==total_levels-3: # grip bends the other way at the bottom and at the "lip" bottom.
                direction = Vector((skew, 0, z_offset)) 
            elif i==total_levels-1:
                direction = Vector((0, 0, z_offset))
        else: # Extrude the whole grip straight up.
            direction = Vector((0, 0, z_offset))
        
        sx = slide_back_multiplier if i==(total_levels-1) else 1
        if i >= (num_grip_levels-2):
            sx = 0.9 if i < num_grip_levels else 1.05
        sy = slide_back_multiplier if i==(total_levels-1) else 1
            
        scale = Vector((sx, sy, 1))
        extrusion = extrude_edge_loop_copy_move(bm, ref_edge, direction, scale)
        ref_edge = extrusion[0]
                    
        if i==total_levels-1:
            face_idx = 0
            for f in bm.faces:
                if f.select:
                    face_loop_grip_top.append(f)
                face_idx += 1
                    
        if i==total_levels-2 or i==total_levels-3:
            safety_loops.append(extrusion)

    bpy.ops.mesh.select_all(action='DESELECT')
    for e in safety_loops[-1]:
        for v in e.verts:
            v.select = True
    bpy.ops.transform.resize(value=(1.25, ratio_frame_to_grip, 1), orient_type='GLOBAL')
    bpy.ops.mesh.select_all(action='DESELECT')
    for e in safety_loops[-2]:
        for v in e.verts:
            v.select = True
    bpy.ops.transform.resize(value=(1.45, ratio_frame_to_grip, 1), orient_type='GLOBAL')
    bpy.ops.mesh.select_all(action='DESELECT')
    
    bmesh.update_edit_mesh(grip_obj.data)
    # ------------------------ TOP OF GRIP, TRANSITION INTO FRAME AND BACK OF SLIDE --------------------------
    # Count the number of faces at the front.
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    if bm.faces[0].normal[2] > 0:
        bpy.ops.mesh.flip_normals()

    bpy.ops.mesh.select_all(action='DESELECT')
    
    num_front_faces = 0
    for f in face_loop_grip_top:
        if f.normal.normalized().dot(-unit_x) > cos(radians(45)):
            f.select = True
            num_front_faces += 1

    _, _, grip_top_y_span = get_y_span(face_loop_grip_top, Side.Top, num_front_faces)
    # Since we position the starting end of the barrel cylinder(s) at the center of the grip top loop, we want to record 
    # the distance from the center to the loop's rim so it can be added to the total barrel length later.
    barrel_locs_center, barrel_loc_list, barrel_radius = get_pos_inside_face_loop(face_loop_grip_top, num_barrels, grip_top_y_span)

    # Flatten out the front-most 4 faces of the top row in the YZ plane.
    bpy.ops.transform.resize(value=(0, 1, 1), orient_type='GLOBAL')
    # Extrude out the frame in -X.
    frame_len = grip_radius*2*ratio_frame_to_grip * 5
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value":(-frame_len, -0, -0), "orient_type":'GLOBAL'})  

    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles()
    bpy.ops.mesh.select_all(action='DESELECT')

    # With remove doubles, the geometry may have changed, so we have to look up and re-select the faces at the tip of the barrel bottom.
    bmesh.update_edit_mesh(grip_obj.data)
    bm.faces.ensure_lookup_table()
    frame_front_faces = sorted(bm.faces, key=lambda f: sum([f.verts[i].co[0] for i in range(len(f.verts))]))[:num_front_faces]

    # Rotate the faces at the from of the barrel bottom so they tilt inward.
    frame_front_rot = 30
    for f in frame_front_faces:
        f.select = True
    bpy.ops.transform.rotate(value=radians(frame_front_rot), orient_axis='Y', orient_type='GLOBAL')
    
    bpy.ops.mesh.select_all(action='DESELECT')
    context.tool_settings.mesh_select_mode = [False, True, False]
    frame_bot_v1, frame_bot_v2, _ = get_y_span(frame_front_faces, Side.Bottom, num_front_faces)
    frame_side_faces = [f for f in bm.faces if ((frame_bot_v1 in f.verts) or (frame_bot_v2 in f.verts)) \
        and abs(f.normal.normalized().dot(unit_y)) > cos(radians(30))]
                
    # We'll bevel the two edges framing the bottom of the barrel bottom.
    frame_bot_start_verts = []
    for f in frame_side_faces:
        for e in f.edges:
            for i in range(2):
                v = e.verts[i]
                if frame_bot_v1==v or frame_bot_v2==v:
                    if abs(e.verts[0].co[2]-e.verts[1].co[2])<1:
                        e.select = True
                        frame_bot_start_verts.append(e.verts[1-i])

    frame_top_v1, _, _ = get_y_span(frame_front_faces, Side.Top, num_front_faces)
    frame_x_extent = frame_top_v1.co[0]
    frame_top_z = frame_top_v1.co[2]
    for i in range(len(barrel_loc_list)):
        barrel_loc_list[i][2] = frame_top_z
    frame_height = abs(frame_top_z - frame_bot_v1.co[2])
    grip_height = frame_bot_start_verts[0].co[2]
    trigger_radius = min(grip_height, abs(frame_x_extent))/8
    trigger_loc = (frame_bot_start_verts[0].co+frame_bot_start_verts[1].co)/2
    trigger_loc[2] -= trigger_radius
    # If grip is not bent, need to shift trigger box over so it doesn't overlap the grip.
    if not stylize:
        trigger_loc[0] -= (grip_radius*grip_width_multiplier)

    # Estimate the amount of bevel along either side of the outer bottom edges of the barrel bottom, based 
    # on roughly how wide each face is (across Y) at the tip.
    frame_bevel_offset = (grip_top_y_span/num_front_faces)*0.9
    bpy.ops.mesh.bevel(offset=frame_bevel_offset, segments=1, loop_slide=False)
    bpy.ops.mesh.select_all(action='DESELECT')

    # --------------------------------- CREATE BACK OF SLIDE W/ RIBBEDD DETAIL --------------------------------
    slide_back_face_loops = []
    slide_back_main_loop = []
    slide_back_radius = grip_radius
    pcrt_of_sphere = 0.6
    
    # Extrude the back of the slide.
    z_offset = slide_back_radius*pcrt_of_sphere
    theta = asin(z_offset/slide_back_radius)
    r_at_level = slide_back_radius*cos(theta)
    level_scale_factor = r_at_level/slide_back_radius
    scale = Vector((level_scale_factor, level_scale_factor, 1))
    direction = Vector((0, 0, grip_level_height*slide_back_multiplier))
    extrusion = extrude_edge_loop_copy_move(bm, ref_edge, direction, scale)
    ref_edge = extrusion[0]
    slide_back_height = direction[2]*scale[2]
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        if f.select:
            f_normal_dot_unit_x = f.normal.normalized().dot(-unit_x)
            # If side only, then face normals need to point in either Y or -Y (therefore dot(unit_x) is 0.
            if side_rib_only:
                if abs(f_normal_dot_unit_x) < 0.1:
                    slide_back_face_loops.append(f)
            else: # If sides and back, then face normals need to NOT point in X (which is barrel dir).
                if f_normal_dot_unit_x < 0.1:
                    slide_back_face_loops.append(f)
            slide_back_main_loop.append(f)
            
    _, _, barrel_back_y_span = get_y_span(slide_back_main_loop, Side.Top, num_front_faces)
            
    # Create an additional level for capped detail.
    direction = Vector((0, 0, slide_back_radius*0.2))
    extrusion = extrude_edge_loop_copy_move(bm, ref_edge, direction, Vector((1, 1, 1)))
    ref_edge = extrusion[0]
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": Vector((0, 0, 0))})

    bpy.ops.mesh.select_all(action='DESELECT')
    select_edge_loops(bm, [ref_edge], select_rings=False)
    bpy.ops.mesh.edge_collapse()

    # Inset top back of barrel to create ridged detail.
    fl = sorted(slide_back_face_loops, key=lambda f: max([f.verts[i].co[1] for i in range(4)]))
    num_half = int(len(fl)/2)
    fl_first_half = sorted(fl[:num_half], key=lambda f: max([f.verts[i].co[0] for i in range(4)]))
    fl_sec_half = sorted(fl[num_half:], key=lambda f: max([f.verts[i].co[0] for i in range(4)]))
    fl_first_half_to_inset = [fl_first_half[i] for i in range(num_half) if i%2==1]
    bmesh.ops.inset_region(bm, faces=fl_first_half_to_inset, thickness=0.2, depth=0.3)
    fl_sec_half_to_inset = [fl_sec_half[i] for i in range(num_half) if i%2==1]
    bmesh.ops.inset_region(bm, faces=fl_sec_half_to_inset, thickness=0.2, depth=0.3)
        
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.remove_doubles()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.update_edit_mesh(grip_obj.data)    
    bpy.ops.object.mode_set(mode='OBJECT')

    # ----------------------------------------------- CREATE BARREL ------------------------------------------------------
    bm2, barrel_obj = get_placeholder_mesh_obj_and_bm(context, name=name+"_barrel", location=barrel_locs_center+Vector(location))
    barrel_thickness_pcrt = 0.3
    
    for barrel_loc in barrel_loc_list:
        bpy.ops.mesh.select_all(action='DESELECT')
        bmesh.ops.create_circle(bm2, cap_ends=False, cap_tris=False, segments=num_cir_segments, radius=barrel_radius)
        context.tool_settings.mesh_select_mode = [True, False, False]
        bm2.verts.ensure_lookup_table()
        bm2.verts[-1].select = True
        bpy.ops.mesh.select_linked()
        offset = barrel_loc - barrel_locs_center
        bpy.ops.transform.translate(value=(offset[0],offset[1],offset[2]), orient_type='GLOBAL')
        bpy.ops.transform.rotate(value=1.5708, orient_axis='Y', orient_type='LOCAL', constraint_axis=(False, True, False), mirror=True)
        this_barrel_len = abs(frame_x_extent - barrel_loc[0])
        bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value":(-this_barrel_len, -0, -0)})
        bm2.faces.ensure_lookup_table()
        bm2.faces[-1].select = True
        bpy.ops.mesh.select_linked()
        context.tool_settings.mesh_select_mode = [False, False, True]
        barrel_thickness = barrel_thickness_pcrt*barrel_radius
        bpy.ops.mesh.extrude_region_shrink_fatten(TRANSFORM_OT_shrink_fatten={"value":-barrel_thickness, "use_even_offset":False, "mirror":False})
    
    bm2.faces.ensure_lookup_table()
    bpy.ops.mesh.select_all(action='SELECT')
    raw_barrel_width = barrel_radius*2*num_barrels
    raw_barrel_height = barrel_radius*2
    target_height = min(max(raw_barrel_height, slide_back_height), slide_back_height)
    height_scale = target_height/raw_barrel_height
    target_width = min(1, height_scale)*(barrel_back_y_span-grip_top_y_span)+grip_top_y_span    
    width_scale = target_width/raw_barrel_width
    barrel_scale = min(height_scale, width_scale)
    
    bpy.ops.transform.translate(value=(0,0,barrel_radius*barrel_scale), orient_type='GLOBAL')
    bpy.ops.transform.resize(value=(1, barrel_scale, barrel_scale), orient_type='GLOBAL')
    
    bpy.ops.mesh.remove_doubles()
    bmesh.ops.recalc_face_normals(bm2, faces=bm2.faces)
    bmesh.update_edit_mesh(barrel_obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # ----------------------------------------------- CREATE TRIGGER -----------------------------------------------------
    bm3, trigger_obj = get_placeholder_mesh_obj_and_bm(context, name=name+"_trigger", location=trigger_loc+Vector(location))
    cir_radius = trigger_radius*(1/cos(radians(45)))
    trigger_frame_thickness = base_radius/2
    bmesh.ops.create_cone(bm3, cap_ends=False, cap_tris=False, segments=4, radius1=cir_radius, radius2=cir_radius, depth=trigger_frame_thickness)
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.rotate(value=radians(45), orient_axis='Z', orient_type='GLOBAL')
    bpy.ops.transform.rotate(value=radians(90), orient_axis='X', orient_type='GLOBAL')
    bpy.ops.transform.resize(value=(1.5, 1, 1), orient_type='GLOBAL', constraint_axis=(True, False, False), mirror=True) 
    bpy.ops.mesh.extrude_region_shrink_fatten(TRANSFORM_OT_shrink_fatten={"value":trigger_radius*0.5, "use_even_offset":False, "mirror":False})
    bpy.ops.mesh.select_all(action='DESELECT')
    
    # 0.35*x*x-2 = trigger_radius
    # x = sqrt((trigger_radius+2)/0.35)
    pull_z_tolerance = frame_height
    x_start = sqrt((trigger_radius+pull_z_tolerance+2)/0.35)
    x_end = -(x_start/5)
    finger_pull_thickness = trigger_frame_thickness/2
    x_offset = 0 if stylize else -0.5*trigger_radius
    create_finger_pull_xz(context, x_start, x_end, bm3, x_offset, finger_pull_thickness)

    bpy.ops.mesh.remove_doubles()
    bmesh.ops.recalc_face_normals(bm3, faces=bm3.faces)
    bmesh.update_edit_mesh(trigger_obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # ---------------------------- APPLY LOCATION TRANSFORMS & MODIFIERS TO ALL GENERATED OBJECTS ------------------------------------
    bpy.ops.object.select_all(action='DESELECT')
        
    gun_objs = [grip_obj, barrel_obj, trigger_obj]
    bevel_width = [2, 2, 1]
    for i in range(len(gun_objs)):
        obj = gun_objs[i]
        obj.select_set(True)
        add_bevel_modifier(obj, width=bevel_width[i], segments=3)
        
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME', center='MEDIAN')
    add_simple_deform_taper_modifier(trigger_obj)
    
    bpy.ops.object.select_all(action='DESELECT')
    
    # --------------------------------------------------------------------------------------------------------------------

def test_gen_gun_row(context):
    spacing = 5 * 2 * 3
    
    generate_gun(context, "0_default_gun", location=(-5, 2*spacing, -8))

    generate_gun(context, "1", location=(-35, spacing, 8), num_cir_segments=24, grip_radius=6, num_grip_levels=3, \
        stylize=True, grip_bent_factor=0.5, side_rib_only=False, num_barrels=2, ratio_frame_to_grip=0.8, \
        slide_back_multiplier=1.0, grip_width_multiplier=1.25)
        
    generate_gun(context, "2", location=(0, 0, 0), num_cir_segments=32, grip_radius=4, num_grip_levels=8, \
        stylize=True, grip_bent_factor=1.5, side_rib_only=True, num_barrels=1, ratio_frame_to_grip=1.0, \
        slide_back_multiplier=0.8, grip_width_multiplier=2.5)
        
    generate_gun(context, "3", location=(-35, -spacing, 8), num_cir_segments=24, grip_radius=6, num_grip_levels=3, \
        stylize=True, grip_bent_factor=0, side_rib_only=False, num_barrels=2, ratio_frame_to_grip=0.8, \
        slide_back_multiplier=1.0, grip_width_multiplier=1.25)
        
    generate_gun(context, "4", location=(0, -spacing*2, 0), num_cir_segments=32, grip_radius=4, num_grip_levels=8, \
        stylize=True, grip_bent_factor=-0.5, side_rib_only=True, num_barrels=1, ratio_frame_to_grip=1.0, \
        slide_back_multiplier=1.8, grip_width_multiplier=2.5)
        
    generate_gun(context, "5", location=(0, -spacing*3, 0), num_cir_segments=40, grip_radius=2, num_grip_levels=10, \
        stylize=True, grip_bent_factor=0.8, side_rib_only=False, num_barrels=3, ratio_frame_to_grip=2.5, \
        slide_back_multiplier=2.0, grip_width_multiplier=1.75)
        
    generate_gun(context, "6", location=(0, -spacing*4, 0), num_cir_segments=56, grip_radius=3, num_grip_levels=12, \
        stylize=True, grip_bent_factor=-1.8, side_rib_only=True, num_barrels=4, ratio_frame_to_grip=2, \
        slide_back_multiplier=1.25, grip_width_multiplier=1.5)
        
    generate_gun(context, "7", location=(0, -spacing*5, 0), num_cir_segments=40, grip_radius=5, num_grip_levels=10, \
        stylize=False, grip_bent_factor=1, side_rib_only=True, num_barrels=3, ratio_frame_to_grip=1, \
        slide_back_multiplier=2.0, grip_width_multiplier=1.0)
        
    generate_gun(context, "8", location=(0, -spacing*7, 0), num_cir_segments=40, grip_radius=5, num_grip_levels=10, \
        stylize=False, grip_bent_factor=1, side_rib_only=True, num_barrels=3, ratio_frame_to_grip=2.5, \
        slide_back_multiplier=2.0, grip_width_multiplier=1.75)

def test_gen_gun_grid(context):
    x_cell = 50
    z_cell = 65
    
    generate_gun(context, "0_default_gun", location=(-x_cell, 0, 2*z_cell))
    
    generate_gun(context, "1", location=(-x_cell, 0, z_cell), num_cir_segments=24, grip_radius=6, num_grip_levels=3, \
        stylize=True, grip_bent_factor=0.5, side_rib_only=False, num_barrels=2, ratio_frame_to_grip=0.8, \
        slide_back_multiplier=1.0, grip_width_multiplier=1.25)
        
    generate_gun(context, "2", location=(-x_cell, 0, 0), num_cir_segments=32, grip_radius=4, num_grip_levels=8, \
        stylize=True, grip_bent_factor=1.5, side_rib_only=True, num_barrels=1, ratio_frame_to_grip=1.0, \
        slide_back_multiplier=0.8, grip_width_multiplier=2.5)
        
    generate_gun(context, "3", location=(-x_cell, 0, -z_cell), num_cir_segments=24, grip_radius=6, num_grip_levels=3, \
        stylize=True, grip_bent_factor=0, side_rib_only=False, num_barrels=2, ratio_frame_to_grip=0.8, \
        slide_back_multiplier=1.0, grip_width_multiplier=1.25)
        
    generate_gun(context, "4", location=(x_cell, 0, 1.75*z_cell), num_cir_segments=32, grip_radius=4, num_grip_levels=8, \
        stylize=True, grip_bent_factor=-0.5, side_rib_only=True, num_barrels=1, ratio_frame_to_grip=1.0, \
        slide_back_multiplier=1.8, grip_width_multiplier=2.5)
        
    generate_gun(context, "5", location=(x_cell, 0, z_cell), num_cir_segments=40, grip_radius=2, num_grip_levels=10, \
        stylize=True, grip_bent_factor=0.8, side_rib_only=False, num_barrels=3, ratio_frame_to_grip=2.5, \
        slide_back_multiplier=2.0, grip_width_multiplier=1.75)
        
    generate_gun(context, "6", location=(x_cell, 0, 0), num_cir_segments=56, grip_radius=3, num_grip_levels=12, \
        stylize=True, grip_bent_factor=-1.8, side_rib_only=True, num_barrels=4, ratio_frame_to_grip=2, \
        slide_back_multiplier=1.25, grip_width_multiplier=1.5)
        
    generate_gun(context, "7", location=(x_cell, 0, -1.5*z_cell), num_cir_segments=40, grip_radius=5, num_grip_levels=10, \
        stylize=False, grip_bent_factor=1, side_rib_only=True, num_barrels=3, ratio_frame_to_grip=1, \
        slide_back_multiplier=2.0, grip_width_multiplier=1.0)
        
    generate_gun(context, "8", location=(x_cell, 0, -3*z_cell), num_cir_segments=40, grip_radius=5, num_grip_levels=10, \
        stylize=False, grip_bent_factor=1, side_rib_only=True, num_barrels=3, ratio_frame_to_grip=2.5, \
        slide_back_multiplier=2.0, grip_width_multiplier=1.75)

#=============================================================================================
if __name__ == "__main__":
    test_gen_gun_row(bpy.context)
    #test_gen_gun_grid(bpy.context)
