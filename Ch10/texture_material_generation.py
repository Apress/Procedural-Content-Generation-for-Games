import numpy as np
import bmesh
import bpy
from mathutils import Vector

from math import floor, pow
import timeit
import random

import os, sys
script_dir = ""
if bpy.context.space_data and bpy.context.space_data.text:
    script_filepath = bpy.context.space_data.text.filepath
    if script_filepath:
        script_dir = os.path.dirname(script_filepath)
        if not script_dir in sys.path:
            sys.path.append(script_dir)
            
from mesh_editing_utils import get_placeholder_mesh_obj_and_bm
from material_and_image_utils import get_context_override, get_name_no_ext, rearrange_nodes, create_material, \
create_texture_coords_mapping_nodes, set_mapping_node_scale, save_image_to_file, find_min_max

def bake_normal_map_from_given_mesh(context, mesh_obj, grid_size):        
    for obj in context.view_layer.objects:
        obj.select_set(False)
    mesh_obj.select_set(True)
    context.view_layer.objects.active = mesh_obj
    
    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**viewport_co):
        bpy.ops.object.mode_set(mode='OBJECT')
        
    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**viewport_co):
        for m in mesh_obj.modifiers:
            bpy.ops.object.modifier_apply(modifier=m.name)
            
    bb = np.array(mesh_obj.bound_box)
    z_min, z_max = find_min_max(bb, 2)
    plane_loc = Vector(mesh_obj.location)
    plane_loc[2] += (0.5*(z_max-z_min) + 0.15)
    bm, plane_obj = get_placeholder_mesh_obj_and_bm(context, mesh_obj.name+"_plane", plane_loc)
    grid_size /= 2
    segments = floor(grid_size)
    bmesh.ops.create_grid(bm, x_segments=segments, y_segments=segments, size=grid_size, calc_uvs=True)
    bmesh.update_edit_mesh(plane_obj.data)
    bm.free()
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project()
    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**viewport_co):
        bpy.ops.object.mode_set(mode='OBJECT')

    plane_mat = create_material(plane_obj, plane_obj.name+"_mat")
    nodes = plane_mat.node_tree.nodes
    node_tex_img = nodes.new(type='ShaderNodeTexImage')
    image_block = bpy.data.images.new(mesh_obj.name+"_normal_map", 1024, 1024)
    image_block.generated_type = 'BLANK'
    node_tex_img.image = image_block
    rearrange_nodes(nodes)    
    node_tex_img.select = True
        
    mesh_obj.select_set(True)
    plane_obj.select_set(True)
    context.view_layer.objects.active = plane_obj
    
    context.scene.render.engine = 'CYCLES'
    context.scene.cycles.device = 'GPU'
    context.scene.cycles.bake_type = 'NORMAL'
    context.scene.render.bake.normal_space = 'TANGENT'
    context.scene.render.bake.use_selected_to_active = True
    context.scene.render.bake.cage_extrusion = 0.1
    context.scene.render.bake.margin = 0
    bpy.ops.object.bake(type='NORMAL')
    
    save_image_to_file(script_dir, image_block, image_block.name)
    
    return image_block
    
def create_grip(obj, mat, color, normal_map_filepath):    
    node_tc, node_mapping = create_texture_coords_mapping_nodes(obj, mat)
    set_mapping_node_scale(mat, (2,1,1))
    
    nodes = mat.node_tree.nodes
    node_tex_img = nodes.new(type='ShaderNodeTexImage')
    image_block = bpy.data.images.load(normal_map_filepath)
    image_block.name = get_name_no_ext(normal_map_filepath)
    image_block.colorspace_settings.name = 'Non-Color'
    node_tex_img.image = image_block
    
    node_normal_map = nodes.new(type='ShaderNodeNormalMap')
    links = mat.node_tree.links
    links.new(node_mapping.outputs['Vector'], node_tex_img.inputs['Vector'])
    links.new(node_tex_img.outputs['Color'], node_normal_map.inputs['Color'])
    node_bsdf = nodes['Principled BSDF']
    links.new(node_normal_map.outputs['Normal'], node_bsdf.inputs['Normal'])
    
    node_bsdf.inputs['Metallic'].default_value = 0.0
    node_bsdf.inputs['Roughness'].default_value = 0.5
    node_bsdf.inputs['Base Color'].default_value = color
    
    node_out = nodes['Material Output']
    nodes_to_arrange = [node_tc, node_mapping, node_tex_img, node_normal_map, node_bsdf, node_out]
    rearrange_nodes(nodes_to_arrange)

def create_shiny_metal(mat, color):
    nodes = mat.node_tree.nodes
    node_bsdf = nodes['Principled BSDF']
    node_bsdf.inputs['Metallic'].default_value = 1.0
    node_bsdf.inputs['Roughness'].default_value = 0.0
    node_bsdf.inputs['Base Color'].default_value = color
    
def create_brushed_metal(obj, mat, color):
    node_tc, node_mapping = create_texture_coords_mapping_nodes(obj, mat)
    set_mapping_node_scale(mat, (100,100,100))
    
    nodes = mat.node_tree.nodes
    node_noise = nodes.new(type='ShaderNodeTexNoise')
    node_noise.noise_dimensions = '3D'
    node_noise.noise_type = 'FBM'
    node_noise.normalize = True
    node_noise.inputs['Roughness'].default_value = 1.0
    
    links = mat.node_tree.links
    links.new(node_mapping.outputs['Vector'], node_noise.inputs['Vector'])
    
    node_bump = nodes.new(type='ShaderNodeBump')
    node_bump.inputs[0].default_value = 0.1 #'Strength'
    links.new(node_noise.outputs['Fac'], node_bump.inputs['Height'])
    
    node_bsdf = nodes['Principled BSDF']
    links.new(node_bump.outputs['Normal'], node_bsdf.inputs['Normal'])
    node_bsdf.inputs['Metallic'].default_value = 1.0
    node_bsdf.inputs['Roughness'].default_value = 0.2
    node_bsdf.inputs['Base Color'].default_value = color
    
    node_out = nodes['Material Output']
    nodes_to_arrange = [node_tc, node_mapping, node_noise, node_bump, node_bsdf, node_out]
    rearrange_nodes(nodes_to_arrange)
    
def create_fine_grid_metal(obj, mat, color):
    node_tc, node_mapping = create_texture_coords_mapping_nodes(obj, mat)
    set_mapping_node_scale(mat, (75,75,75))
    
    nodes = mat.node_tree.nodes
    node_vor = nodes.new(type='ShaderNodeTexVoronoi')
    node_vor.voronoi_dimensions = '3D'
    node_vor.distance = 'EUCLIDEAN'
    node_vor.feature = 'F1'
    node_vor.normalize = True
    node_vor.inputs['Roughness'].default_value = 0.5
    node_vor.inputs['Randomness'].default_value = 0.0
    
    links = mat.node_tree.links
    links.new(node_mapping.outputs['Vector'], node_vor.inputs['Vector'])
    
    node_bump = nodes.new(type='ShaderNodeBump')
    node_bump.inputs[0].default_value = 0.1 # 'Strength'
    links.new(node_vor.outputs['Color'], node_bump.inputs['Height'])
    
    node_bsdf = nodes['Principled BSDF']
    links.new(node_bump.outputs['Normal'], node_bsdf.inputs['Normal'])
    node_bsdf.inputs['Metallic'].default_value = 1.0
    node_bsdf.inputs['Roughness'].default_value = 0.2
    node_bsdf.inputs['Base Color'].default_value = color
    
    node_out = nodes['Material Output']
    nodes_to_arrange = [node_tc, node_mapping, node_vor, node_bump, node_bsdf, node_out]
    rearrange_nodes(nodes_to_arrange)

if __name__ == "__main__":
    bake_normal_map_from_given_mesh(bpy.context, bpy.data.objects["round_bumps"], 10)
    #bake_normal_map_from_given_mesh(bpy.context, bpy.data.objects["cross_motif_grid"], 10)