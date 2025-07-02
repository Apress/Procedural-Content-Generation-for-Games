import rasterio as ri
import matplotlib.pyplot as plt
import numpy as np

import bmesh
import bpy
from mathutils import Vector

import sys
import os
import timeit
from math import sqrt, floor

script_dir = ""
if bpy.context.space_data and bpy.context.space_data.text:
    script_filepath = bpy.context.space_data.text.filepath
    if script_filepath:
        script_dir = os.path.dirname(script_filepath)
        if not script_dir in sys.path:
            sys.path.append(script_dir)
            
from material_and_image_utils import get_context_override, get_name_no_ext, rearrange_nodes, create_material, \
create_texture_coords_mapping_nodes, find_min_max

def create_mat_with_img_texture(obj, mat_name, txt_img_block):    
    mat = create_material(obj, mat_name)
    node_tc, node_mapping = create_texture_coords_mapping_nodes(obj, mat)
    
    nodes = mat.node_tree.nodes
    node_tex_img = nodes.new(type='ShaderNodeTexImage')
    node_tex_img.image = txt_img_block
    
    node_bsdf = nodes['Principled BSDF']  
    links = mat.node_tree.links
    links.new(node_mapping.outputs['Vector'], node_tex_img.inputs['Vector'])
    links.new(node_tex_img.outputs['Color'], node_bsdf.inputs['Base Color'])
    
    node_out = nodes['Material Output']
    nodes_to_arrange = [node_tc, node_mapping, node_tex_img, node_bsdf, node_out]
    rearrange_nodes(nodes_to_arrange)    
    
def unwrap_and_add_mat(context, obj_to_unwrap, uv_map_name, txt_img_blk, mat_name):
    mesh_to_unwrap = obj_to_unwrap.data
    uv_map_idx = mesh_to_unwrap.uv_layers.find(uv_map_name)
    if uv_map_idx < 0:
        mesh_to_unwrap.uv_layers.new(name=uv_map_name)
        uv_map_idx = mesh_to_unwrap.uv_layers.find(uv_map_name)
        
    uv_map = mesh_to_unwrap.uv_layers[uv_map_name]
    uv_map.active_render = True
    # Make sure the right UV Map index is selected in Properties window -> Object data -> UV Maps, so the subsequent 
    # set of UVs unwrapped goes to it.
    mesh_to_unwrap.uv_layers.active_index = uv_map_idx

    # Switch obj_to_unwrap in Edit mode to unwrap.
    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**viewport_co):
        bpy.ops.object.mode_set(mode='EDIT')
            
    # Now that obj_to_unwrap is in Edit mode, select all, and use View -> Frame Selected to adjust zoom.
    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**viewport_co):
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.view3d.view_selected(use_all_regions=False)
            
    # Set the viewport to the top View.
    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**viewport_co):
        bpy.ops.view3d.view_axis(type='TOP')
            
    # Make the viewport update() to ensure the view_axis change takes effect, and set shading to Material Preview.
    for a in context.window.screen.areas:
        if a.type=='VIEW_3D':
            for s in a.spaces:
                if s.type=='VIEW_3D':
                    s.region_3d.update()
                    s.shading.type = 'MATERIAL'

    # Unwrap by projecting from view.
    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**viewport_co):
        bpy.ops.uv.project_from_view(camera_bounds=False, correct_aspect=True, scale_to_bounds=True)
                        
    context.scene.render.engine = 'CYCLES'
    create_mat_with_img_texture(obj_to_unwrap, mat_name, txt_img_blk)
    bpy.ops.object.material_slot_assign()

    viewport_co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**viewport_co):
        bpy.ops.object.mode_set(mode='OBJECT')
    
def apply_mod_and_add_mat(context, terrain_obj, geo_nodes_mod, txt_img_blk, mat_name):
    for obj in context.view_layer.objects:
        obj.select_set(False)
    context.view_layer.objects.active = terrain_obj
    terrain_obj.select_set(True)
    
    co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**co):
        bpy.ops.object.mode_set(mode='OBJECT')
    
    bpy.ops.object.modifier_apply(modifier=geo_nodes_mod.name)
    unwrap_and_add_mat(context, terrain_obj, terrain_obj.name+"_top_uvs", txt_img_blk, mat_name)   
    
def create_voxelizer_node_tree(terrain_obj, voxel_size):
    geo_nodes_mod = terrain_obj.modifiers.new(name=terrain_obj.name+"_geo_nodes_mod", type='NODES')
    node_group = bpy.data.node_groups.new(terrain_obj.name+"_geo_nodes_mod", 'GeometryNodeTree')
    geo_nodes_mod.node_group = node_group
    
    node_group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    node_group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    input_node = node_group.nodes.new('NodeGroupInput')
    
    pts_to_vol_node = node_group.nodes.new('GeometryNodePointsToVolume')
    pts_to_vol_node.resolution_mode = 'VOXEL_SIZE'
    pts_to_vol_node.inputs['Density'].default_value = 1.000
    pts_to_vol_node.inputs['Voxel Size'].default_value = voxel_size
    pts_to_vol_node.inputs['Radius'].default_value = 0.6
    
    vol_to_mesh_node = node_group.nodes.new('GeometryNodeVolumeToMesh')
    vol_to_mesh_node.resolution_mode = 'GRID'
    vol_to_mesh_node.inputs['Threshold'].default_value = 0.1
    
    output_node = node_group.nodes.new('NodeGroupOutput')
    
    input_node.location = Vector((0, 0))
    pts_to_vol_node.location = Vector((input_node.width*1.5, 0))
    vol_to_mesh_node.location = Vector((pts_to_vol_node.location[0]+pts_to_vol_node.width*1.5, 0))
    output_node.location = Vector((vol_to_mesh_node.location[0]+vol_to_mesh_node.width*1.5, 0))

    node_group.links.new(input_node.outputs['Geometry'], pts_to_vol_node.inputs['Points'])    
    node_group.links.new(pts_to_vol_node.outputs['Volume'], vol_to_mesh_node.inputs['Volume'])
    node_group.links.new(vol_to_mesh_node.outputs['Mesh'], output_node.inputs['Geometry'])
    return geo_nodes_mod

def mesh_from_points(context, dem_name, points, mins, location, xy_scale, z_scale, voxel_size):
    terrain_mesh_data = bpy.data.meshes.new(name=dem_name+"_data")
    offset = np.full(points.shape, mins)
    verts = np.subtract(points, offset)
    verts_z_scale = verts*z_scale
    verts = np.stack([verts[:,0],verts[:,1]*-1,verts_z_scale[:,2]], axis=-1).reshape(len(points), 3)
    terrain_mesh_data.from_pydata(verts, [], [])
    terrain_mesh_data.update(calc_edges=True)
    terrain_obj = bpy.data.objects.new(name=dem_name, object_data=terrain_mesh_data)
    context.collection.objects.link(terrain_obj)
    
    for obj in context.view_layer.objects:
        obj.select_set(False)
    context.view_layer.objects.active = terrain_obj
    terrain_obj.select_set(True)
        
    co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**co):
        bpy.ops.object.mode_set(mode='OBJECT')
        
    co = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**co):        
        bpy.ops.transform.resize(value=(xy_scale, xy_scale, xy_scale))
        bpy.ops.transform.translate(value=location)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)

    geo_nodes_mod = create_voxelizer_node_tree(terrain_obj, voxel_size)
    
    return terrain_obj, geo_nodes_mod
    
def plt_dem_image(dem_filepath:str, band_num:int):
    dem_file = ri.open(dem_filepath)
    band = dem_file.read(band_num)

    eight_bit = (band * (255/np.max(band))).astype(np.uint8)
    plt.imshow(eight_bit)
    plt.axis('off')
    
    dem_filename_no_ext = get_name_no_ext(dem_filepath)
    plt.savefig(script_dir+"/"+dem_filename_no_ext+"_plt_color.png", bbox_inches='tight', transparent=True, pad_inches=0)
    plt.show()
    
def elev_band_to_XYZ(context, dir:str, dem_filepath:str, target_len:float, sample_step=1000, verbose=True):
    dem_file = ri.open(dem_filepath)
    num_rows, num_cols = dem_file.height, dem_file.width
    band1 = dem_file.read(1)
    
    mask_has_data = band1!=dem_file.nodata
    z = band1[mask_has_data]
    row_indices, col_indices = np.where(mask_has_data)
    x, y = ri.transform.xy(dem_file.transform, row_indices, col_indices)
    
    points = np.stack([x,y,z], axis=-1).reshape(len(x), 3)
    x_min, x_max = find_min_max(points, 0)
    y_min, y_max = find_min_max(points, 1)
    z_min, z_max = find_min_max(points, 2)
    xy_scale = target_len/max(x_max-x_min, y_max-y_min)
    points_subsampled = points[::sample_step] if sample_step > 0 else points
    
    if verbose:
        print("\n" + get_name_no_ext(dem_filepath) + ":")
        print("band1.shape = " + str(band1.shape))
        print("points.shape = " + str(points.shape))
        print("points_subsampled.shape " + str(points_subsampled.shape) + "\n")
    
# Modified version of save_image_to_file() from /Ch4/material_and_image_utils.py
def save_image_to_file(dir, img_blk, trailing_name):
    img_blk.filepath_raw = dir+"/"+img_blk.name+"_"+trailing_name+".png"
    img_blk.file_format = 'PNG'
    img_blk.save()

def create_grayscale_image_from_array(intensities, h, w, name, dir):
    max = intensities.max()
    min = intensities.min()
    span = max-min
    normed_its = (intensities-min)*(1.0/span)

    image_block = bpy.data.images.new(name, w, h)
    alpha = np.ones(normed_its.shape)
    normed_its_arr = [normed_its, normed_its, normed_its, alpha]
    image_block.pixels = np.stack(normed_its_arr, axis=-1).reshape(h, w, 4).ravel()
    image_block.update()
    save_image_to_file(dir, image_block, "grayscale")
    return image_block

def test_np_where():
    points = np.array([(9, -2), (11, 7), (0, 12), (3, 7), (-5, 1)])
    print("points = " + str(points))
    
    row_indices, col_indices = np.where(points < 5)
    print("row_indices = " + str(row_indices))
    print("col_indices = " + str(col_indices))
    
    matches = list(zip(row_indices.tolist(), col_indices.tolist()))
    print("np.where(points < 5) = " + str(matches)) 
        
def gen_dem_mesh(context, dir:str, dem_filepath:str, target_len:float, sample_step=1000, location=(0,0,0), z_scale=0.000015, voxel_size=0.1, add_mat=True):
    dem_file = ri.open(dem_filepath)
    num_rows, num_cols = dem_file.height, dem_file.width
    band1 = dem_file.read(1)
    
    mask_has_data = band1!=dem_file.nodata
    z = band1[mask_has_data]
    row_indices, col_indices = np.where(mask_has_data)
    x, y = ri.transform.xy(dem_file.transform, row_indices, col_indices)
    
    points = np.stack([x,y,z], axis=-1).reshape(len(x), 3)
    x_min, x_max = find_min_max(points, 0)
    y_min, y_max = find_min_max(points, 1)
    z_min, z_max = find_min_max(points, 2)
    xy_scale = target_len/max(x_max-x_min, y_max-y_min)
    points_subsampled = points[::sample_step] if sample_step > 0 else points
    
    dem_filename_no_ext = get_name_no_ext(dem_filepath)
    terrain_obj, geo_nodes_mod = mesh_from_points(context, dem_filename_no_ext, points_subsampled, (x_min,y_min,z_min), \
        location, xy_scale, z_scale, voxel_size)
        
    if add_mat:
        row_indices_no_data, col_indices_no_data = np.where(band1==dem_file.nodata)
        band1[row_indices_no_data, col_indices_no_data] = z_min
        dem_img_blk = create_grayscale_image_from_array(band1, num_rows, num_cols, dem_filename_no_ext, dir)
        mat_name = dem_filename_no_ext + "_mat"
        apply_mod_and_add_mat(context, terrain_obj, geo_nodes_mod, dem_img_blk, mat_name)
    
def plot_provided_dems():
    plt_dem_image(script_dir+"/USGS_13_n39w106_20230602.tif", 1)
    plt_dem_image(script_dir+"/DTEEC_041878_1460_041021_1460_G01.IMG", 1)
    
def print_data_shapes():
    elev_band_to_XYZ(bpy.context, script_dir, script_dir+"/USGS_13_n39w106_20230602.tif", 100.0, 1000, True)
    elev_band_to_XYZ(bpy.context, script_dir, script_dir+"/DTEEC_041878_1460_041021_1460_G01.IMG", 100.0, 100, True)
    
def gen_provided_dems(add_mat:bool):
    start = timeit.default_timer()

    gen_dem_mesh(bpy.context, script_dir, script_dir+"/USGS_13_n39w106_20230602.tif", 100.0, voxel_size=0.2, add_mat=add_mat)
    gen_dem_mesh(bpy.context, script_dir, script_dir+"/DTEEC_041878_1460_041021_1460_G01.IMG", 100.0, 100, location=(-75,0,0), z_scale=1, add_mat=add_mat)    

    end = timeit.default_timer()
    print("Runtime = " + str(end-start))
    
if __name__ == "__main__":
#    test_np_where()
#    plot_provided_dems()
#    print_data_shapes()
    gen_provided_dems(add_mat=True)
