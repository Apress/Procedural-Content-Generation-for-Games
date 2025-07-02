import bpy
import numpy as np

__all__ = (
    "get_context_override",
    "get_name_no_ext",
    "add_material_to_obj",
    "create_material",
    "create_texture_coords_mapping_nodes",
    "set_mapping_node_scale",
    "save_image_to_file"
    "find_min_max"
    )
            
def get_context_override(context, area_type, region_type):
    override = context.copy()
    for area in override['screen'].areas:
        if area.type == area_type: # e.g. 'VIEW_3D' for viewport, 'IMAGE_EDITOR' for UV/Image Editor, etc.
            override['area'] = area
            break
    for region in override['area'].regions:
        if region.type == region_type: # e.g. 'WINDOW'
            override['region'] = region
            break
    return override

def get_name_no_ext(filepath):
    delimiter = "/" if "/" in filepath else "\\"
    filename_no_ext = filepath.split(delimiter)[-1].split(".")[0]
    return filename_no_ext

def set_viewport_material_preview(context):
    for a in context.window.screen.areas:
        if a.type == 'VIEW_3D':
            for s in a.spaces:
                if s.type == 'VIEW_3D':
                    s.shading.type = 'MATERIAL'
                    
def rearrange_nodes(nodes):
    for i in range(len(nodes)):
        n = nodes[i]
        n.select = False
        if i > 0:
            prev_n = nodes[i-1]
            n.location = prev_n.location
            n.location[0] += (n.width + prev_n.width)*0.5*1.5
            
def add_material_to_obj(obj, mat):
    mat_index = obj.data.materials.find(mat.name)
    if mat_index < 0:
        obj.data.materials.append(mat)
        mat_index = obj.data.materials.find(mat.name)
        
    obj.active_material_index = mat_index
    mat.use_nodes = True

def create_material(obj, mat_name):
    if bpy.data.materials.find(mat_name) < 0:
        bpy.data.materials.new(mat_name)
    mat = bpy.data.materials[mat_name]
    add_material_to_obj(obj, mat)

    nodes = mat.node_tree.nodes
    bsdf_index = nodes.find('Principled BSDF')
    node_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled') if bsdf_index < 0 else nodes[bsdf_index]
    
    out_index = nodes.find('Material Output')
    node_output = nodes.new(type='ShaderNodeOutputMaterial') if out_index < 0 else nodes[out_index]  
    links = mat.node_tree.links
    links.new(node_bsdf.outputs['BSDF'], node_output.inputs['Surface'])
    return mat 

def create_texture_coords_mapping_nodes(obj, mat):
    nodes = mat.node_tree.nodes
    node_tc = nodes.new(type='ShaderNodeTexCoord')
    node_tc.object = obj
    
    node_mapping = nodes.new(type='ShaderNodeMapping')
    links = mat.node_tree.links
    links.new(node_tc.outputs['UV'], node_mapping.inputs['Vector'])
    
    return node_tc, node_mapping

def set_mapping_node_scale(mat, scale):
    nodes = mat.node_tree.nodes
    node_mapping = nodes['Mapping']
    node_mapping.inputs['Scale'].default_value = scale
    
def save_image_to_file(dir, image_block, name):
    image_block.filepath_raw = dir + '\\' + name + ".png"
    image_block.file_format = 'PNG'
    image_block.save()
    
def find_min_max(points, axis):
    return np.min(points[:, axis]), np.max(points[:, axis])
    