import bpy
import numpy as np
from mathutils import Vector
from copy import deepcopy

import os, sys
script_dir = ""
if bpy.context.space_data and bpy.context.space_data.text:
    script_filepath = bpy.context.space_data.text.filepath
    if script_filepath:
        script_dir = os.path.dirname(script_filepath)
        if not script_dir in sys.path:
            sys.path.append(script_dir)

from material_and_image_utils import get_context_override, find_min_max

def set_length_units(context):
    context.scene.unit_settings.system = 'METRIC'
    context.scene.unit_settings.scale_length = 1
    context.scene.unit_settings.length_unit = 'METERS'
    
def get_dim_XYZ(obj):
    bbox = [[v[0], v[1], v[2]] for v in obj.bound_box]
    bbox_verts = np.array(bbox).reshape(len(bbox), 3)
    x_min, x_max = find_min_max(bbox_verts, 0)
    y_min, y_max = find_min_max(bbox_verts, 1)
    z_min, z_max = find_min_max(bbox_verts, 2)
    return (x_max-x_min), (y_max-y_min), (z_max-z_min)    

def post_process_objs_for_export(context, objs_to_join, target_length=-1):
    if len(objs_to_join) < 1:
        return None

    for obj in context.view_layer.objects:
        obj.select_set(False)
        
    filtered_objs_to_join = []
    for obj in objs_to_join:
        if obj.type != 'MESH':
            continue
        
        filtered_objs_to_join.append(obj)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        
        c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**c_o):
            bpy.ops.object.mode_set(mode='OBJECT')
            
        c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**c_o):                    
            # Triangulate by adding and applying a Triangulate modifier
            # Properties editor--Modifier tab--Add Modifier--Generate--Triangulate
            tri_mod = obj.modifiers.new(obj.name+"_tri_mod", 'TRIANGULATE')
            
            # Apply all modifiers - otherwise some objs' modifiers will go missing when they are joined.
            # (Properties Editor--Modifier tab--click on v at the upper right of each modifier--Apply)
            for m in obj.modifiers:
                bpy.ops.object.modifier_apply(modifier=m.name)
            # Apply all transforms (Ctrl-A--All Transforms, or Object--Apply--All Transforms)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            # Object--Set Origin--Origin to Center of Mass (Volume)
            bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME', center='MEDIAN')
            
        obj.select_set(False)
        
    if len(filtered_objs_to_join) < 1:
        return None
                
    # Combine the given list of mesh objects into a sinlge object 
    # (In Object mode, deselect all, select passed-in list of objects, and Ctrl-J to Join)
    context.view_layer.objects.active = filtered_objs_to_join[-1]
    # The name of the joined obj is the same as the LAST selected obj before Ctrl-J.
    name_of_joined_obj = filtered_objs_to_join[-1].name
    
    for obj in filtered_objs_to_join:
        obj.select_set(True)
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**c_o):
        bpy.ops.object.join()
    
    if context.view_layer.objects.find(name_of_joined_obj) < 0:
        return None
    
    joined_obj = context.view_layer.objects[name_of_joined_obj]
    
    # Calculate scale factor based on target_length if necessary.
    if target_length > 0:
        x_dim, y_dim, z_dim = get_dim_XYZ(joined_obj)
        scale_factor = target_length/max(x_dim, y_dim)

        c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**c_o):
            bpy.ops.transform.resize(value=(scale_factor, scale_factor, scale_factor))
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)      
    
    return context.view_layer.objects[name_of_joined_obj]

def move_to_world_origin(context, obj_to_move):
    for obj in context.scene.objects:
        obj.select_set(False)
    context.view_layer.objects.active = obj_to_move
    obj_to_move.select_set(True)
    obj_orig_loc = deepcopy(obj_to_move.location)
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**c_o):
        bpy.ops.object.mode_set(mode='OBJECT')
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**c_o):
        bpy.ops.transform.translate(value=Vector((0,0,0))-obj_orig_loc)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    
    return obj_orig_loc

def move_to(context, obj_to_move, location):
    for obj in context.scene.objects:
        obj.select_set(False)
    context.view_layer.objects.active = obj_to_move
    obj_to_move.select_set(True)
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**c_o):
        bpy.ops.object.mode_set(mode='OBJECT')
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**c_o):
        bpy.ops.transform.translate(value=location)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        
def move_objs_pre_export(context, objs_to_export, obj_orig_locs):
    for obj in objs_to_export:
        obj_orig_locs.append(move_to_world_origin(context, obj))

def move_objs_post_export(context, objs_to_export, obj_orig_locs):
    for obj, loc in zip(objs_to_export, obj_orig_locs):
        move_to(context, obj, loc)  
        
def get_ready_for_export(context, objs_to_export, obj_orig_locs):
    if len(objs_to_export) < 1:
        return
    
    # Take note of the obj's location, move it to the world origin (0,0,0), export, then move it back.
    # Move to world origin (aligh origin to world (0,0,0))
    move_objs_pre_export(context, objs_to_export, obj_orig_locs)
    
    for obj in context.scene.objects:
        obj.select_set(False)
        
    context.view_layer.objects.active = objs_to_export[0]
    objs_to_export[0].select_set(True)
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**c_o):
        bpy.ops.object.mode_set(mode='OBJECT')
    
    for obj in objs_to_export:
        obj.select_set(True)   

def export_fbx(context, fp, objs_to_export):
    obj_orig_locs = []
    get_ready_for_export(context, objs_to_export, obj_orig_locs)
    
    # File-Export-FBX(.fbx)
    # https://docs.blender.org/api/current/bpy.ops.export_scene.html
    #
    # Path Mode: select Copy, click "Embed Textures" button
    # Batch Mode: select Off
    #
    # Include
    # ----Limit to: check "Selected Objects"
    # 
    # Transform
    # ----Forward: select "-X Forward"
    # ----Up: Select "Z Up"
    #
    # Geometry
    # ----Smoothing: check "Apply Modifiers"
    #
    # Uncheck "Animaion" box
    bpy.ops.export_scene.fbx(filepath=fp, path_mode='COPY', embed_textures=True, batch_mode='OFF', use_selection=True, \
        bake_space_transform=False, use_mesh_modifiers=True, bake_anim=False, axis_forward='-X', axis_up='Z')
    
    # Restore objs' original locations before the export
    move_objs_post_export(context, objs_to_export, obj_orig_locs)

def export_gltf(context, fp, objs_to_export):
    obj_orig_locs = []
    get_ready_for_export(context, objs_to_export, obj_orig_locs)
    
    # File-Export-glTF 2.0 (.glb/.gltf)
    # https://docs.blender.org/api/current/bpy.ops.export_scene.html
    #
    # Format: select "glTF Binary (.glb)"
    # (Optional) check "Remember Export Settings" box to remember export settings
    #
    # Include
    # ----Limit to: check "Selected Objects"
    # ----Data: check "Custom Properties" ? Export custom properties as glTF extras
    #
    # Transform: check "+Y Up" box
    #
    # Data
    # ----Mesh
    # --------check "Apply Modifiers" (export_apply=True, default False) Apply modifiers (excluding Armatures) to mesh objects -WARNING: prevents exporting shape keys
    # --------check "UVs" (export_texcoords=True, default True)
    # --------check "Normals" (export_normals=True, default True)
    # ----Material
    # --------Materials: select "Export" (export_materials='EXPORT', default)
    # --------Images: select "JPEG Format (.jpg)", default is "Automatic" (export_image_format='JPEG', default is 'AUTO')
    # --------Image Quality: set to 100 (export_jpeg_quality=100, int in [0,100], default is 75)
    #
    # Uncheck "Animaion" box
    bpy.ops.export_scene.gltf(filepath=fp, export_format='GLB', will_save_settings=True, use_selection=True, export_extras=True, \
        export_yup=True, export_apply=True, export_texcoords=True, export_normals=True, export_materials='EXPORT', \
        export_image_format='JPEG', export_jpeg_quality=100, export_animations=False)

    # Restore objs' original locations before the export
    move_objs_post_export(context, objs_to_export, obj_orig_locs)
