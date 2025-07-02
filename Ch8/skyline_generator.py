import pandas as pd
import shapefile
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
import numpy as np

import bmesh
import bpy
from mathutils import Vector

import sys
import os
import timeit

import os
script_dir = ""
if bpy.context.space_data and bpy.context.space_data.text:
    script_filepath = bpy.context.space_data.text.filepath
    if script_filepath:
        script_dir = os.path.dirname(script_filepath)

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

def read_shp_file(shp_filepath: str):
    shp_file = shapefile.Reader(shp_filepath)
    shapes = shp_file.shapes()
    delimiter = "/" if "/" in shp_filepath else "\\"
    shp_filename = shp_filepath.split(delimiter)[-1].split(".")[0]
    return shp_file, shapes, shp_filename
    
def plot_shp_file(bbox, shapes, shp_filename):
    fig, axes = plt.subplots()
    x_min, y_min, x_max, y_max = bbox
    axes.set_xlim(x_min, x_max)
    axes.set_ylim(y_min, y_max)
    axes.set_title(shp_filename)
    
    for shape in shapes:
        points = shape.points
        polygon = Polygon(points, edgecolor='green', facecolor='lightgreen')
        axes.add_patch(polygon)
    plt.show()
    
def check_shp_file(shp_filepath: str):
    shp_file, shapes, shp_filename = read_shp_file(shp_filepath)
    plot_shp_file(shp_file.bbox, shapes, shp_filename)
    
def read_spreadsheet_pandas(xslx_filepath: str):
    wb = pd.read_excel(xslx_filepath)
    print(wb.head())
    
def calc_perimeter(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.edges.ensure_lookup_table()
    
    perimeter = 0
    for e in bm.edges:
        perimeter += e.calc_length()
        
    bm.free()
    return perimeter
    
def extrude_single_polygon(mesh, height, elev):
    bm = bmesh.new()
    bm.from_mesh(mesh)    
    bmesh.ops.edgeloop_fill(bm, edges=bm.edges)
    bm.faces.ensure_lookup_table()
    bmesh.ops.solidify(bm, geom=bm.faces, thickness=height)
    bm.verts.ensure_lookup_table()
    bmesh.ops.translate(bm, vec=Vector((0,0,elev)), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()

def extrude_two_polygons(mesh, height, elev, num_shp_edges):
    bm = bmesh.new()
    bm.from_mesh(mesh)    
    
    top = bmesh.ops.extrude_edge_only(bm, edges=bm.edges)
    bm.edges.ensure_lookup_table()
    bmesh.ops.translate(bm, vec=Vector((0,0,height)), verts=[v for v in top["geom"] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.bridge_loops(bm, edges=[e for e in top["geom"] if isinstance(e, bmesh.types.BMEdge)])
    
    bm.edges.ensure_lookup_table()
    bmesh.ops.bridge_loops(bm, edges=bm.edges[:num_shp_edges])
    
    bm.verts.ensure_lookup_table()
    bmesh.ops.translate(bm, vec=Vector((0,0,elev)), verts=bm.verts)

    bm.to_mesh(mesh)
    bm.free()

def extrude_multiple_polygons(context, mesh, loop_ref_edge_indices, height, elev):
    temp_obj = bpy.data.objects.new(name="temp", object_data=mesh)
    context.collection.objects.link(temp_obj)
    for obj in context.view_layer.objects:
        obj.select_set(False)
    context.view_layer.objects.active = temp_obj
    temp_obj.select_set(True)
    context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**context_override):
        bpy.ops.object.mode_set(mode='EDIT')
    
    bm = bmesh.from_edit_mesh(temp_obj.data)
    bm.edges.ensure_lookup_table()     
    
    for i in loop_ref_edge_indices:
        bm.edges[i].select = True
    bpy.ops.mesh.loop_multi_select(ring=False)
    bpy.ops.mesh.fill()
    
    bm.faces.ensure_lookup_table()
    bm.normal_update()      
    top = bmesh.ops.extrude_face_region(bm, geom=bm.faces)
    bmesh.ops.translate(bm, vec=Vector((0,0,height)), verts=[v for v in top["geom"] if isinstance(v, bmesh.types.BMVert)])
    bm.normal_update()
    
    bm.verts.ensure_lookup_table()
    bmesh.ops.translate(bm, vec=Vector((0,0,elev)), verts=bm.verts)
    bmesh.update_edit_mesh(temp_obj.data)

    context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**context_override):
        bpy.ops.object.mode_set(mode='OBJECT')
    
    context.collection.objects.unlink(temp_obj)
    context.view_layer.update()
    bpy.data.objects.remove(temp_obj)  

def add_shape_from_geojson(context, bm, idx, shp_geojson, location, x_min, y_min, height, elev):
    polygons = shp_geojson['coordinates']
    mesh = bpy.data.meshes.new(name=str(idx))
    verts = []
    edges = []

    num_polygons = len(polygons)
    loop_ref_edge_indices = []
    for i in range(num_polygons):
        p = polygons[i]        
        num_verts_in_p = len(p)
        if num_verts_in_p < 3:
            continue
        
        vert_idx_start_for_p = len(verts)
        verts.extend([(p[i][0]-x_min, p[i][1]-y_min, 0) for i in range(num_verts_in_p)])
        
        for j in range(num_verts_in_p-1):
            edge_ends = [vert_idx_start_for_p+j, vert_idx_start_for_p+j+1]
            edges.append(edge_ends)
            
        edges.append([vert_idx_start_for_p+num_verts_in_p-1, vert_idx_start_for_p])
        loop_ref_edge_indices.append(vert_idx_start_for_p)
        
    mesh.from_pydata(verts, edges, [])
    mesh.update(calc_edges=True)
    
    perimeter = calc_perimeter(mesh) if idx==0 else 0
    
    if num_polygons == 1:
        extrude_single_polygon(mesh, height, elev)
        bm.from_mesh(mesh)
    elif num_polygons == 2:
        extrude_two_polygons(mesh, height, elev, len(edges))
        bm.from_mesh(mesh)
    else:
        extrude_multiple_polygons(context, mesh, loop_ref_edge_indices, height, elev)
        bm.from_mesh(mesh)
    bpy.data.meshes.remove(mesh)

    if idx == 0:
        return perimeter
    
def get_sample(num_items, max, min):
    span = max-min
    return np.random.random_sample(num_items)*span+min

def create_buildings_mesh(context, shp_file_name, target_len: float, shapes, bbox, wb, scale, elev_scale, roof_h_key, \
    gnd_elev_key, shp_len_key, location, rand_roof_h_range, rand_gnd_elev_range):
    x_min, y_min, x_max, y_max = bbox
    x_span = x_max-x_min
    y_span = y_max-y_min
    num_shapes = len(shapes)    
    mesh_data = bpy.data.meshes.new(name=shp_file_name+"_data")
    mesh_obj = bpy.data.objects.new(name=shp_file_name, object_data=mesh_data)
    context.collection.objects.link(mesh_obj)
    bm = bmesh.new()
    
    roof_h_min, roof_h_max = rand_roof_h_range
    roof_heights = wb[roof_h_key] if roof_h_key in wb.keys() else get_sample(num_shapes, roof_h_max, roof_h_min)
    gnd_elev_min, gnd_elev_max = rand_gnd_elev_range
    ground_elevs = wb[gnd_elev_key] if gnd_elev_key in wb.keys() else get_sample(num_shapes, gnd_elev_max, gnd_elev_min)
    scale_factor = 1
    for i in range(num_shapes):
        shp_geojson = shapes[i].__geo_interface__
        height = roof_heights[i]*scale
        elev = ground_elevs[i]*scale*elev_scale
            
        if i == 0:
            perimeter = add_shape_from_geojson(context, bm, i, shp_geojson, location, x_min, y_min, height, elev)
            shp_len0 = wb[shp_len_key][0] if shp_len_key in wb.keys() else -1
            xy_scale = shp_len0/perimeter*scale if shp_len0 > 0 else target_len/max(x_span, y_span)
        else:
            add_shape_from_geojson(context, bm, i, shp_geojson, location, x_min, y_min, height, elev)
        
    bm.to_mesh(mesh_data)
    
    for obj in context.view_layer.objects:
        obj.select_set(False)
    context.view_layer.objects.active = mesh_obj
    mesh_obj.select_set(True)
        
    context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**context_override):
        bpy.ops.object.mode_set(mode='OBJECT')
        
    context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**context_override):        
        bpy.ops.transform.resize(value=(xy_scale, xy_scale, 1))
        bpy.ops.transform.translate(value=location)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
    
def gen_skyline(shp_filepath: str, wb_filepath: str, target_len: float, context, elev_scale, roof_h_key, gnd_elev_key, shp_len_key, \
    location=(0,0,0), rand_roof_h_range=(30,60), rand_gnd_elev_range=(10,30)):

    shp_file, shapes, shp_filename = read_shp_file(shp_filepath)
    wb = pd.read_excel(wb_filepath)
    create_buildings_mesh(context, shp_filename, target_len, shapes, shp_file.bbox, wb, 0.1, elev_scale, \
        roof_h_key, gnd_elev_key, shp_len_key, location, rand_roof_h_range, rand_gnd_elev_range) 
            
if __name__ == "__main__":    
    start = timeit.default_timer()
    
    gen_skyline(script_dir+"/qgis_battery_park.shp", script_dir+"/qgis_battery_park.xlsx", 100.0, bpy.context, 1, \
        "heightroof", "groundelev", "shape_len")

    gen_skyline(script_dir+"/havana.shp", script_dir+"/havana.xlsx", 200.0, bpy.context, 1, "", "", "", (-170,0,0), (40,100), (10,30))
        
    end = timeit.default_timer()
    print("Runtime: " + str(end-start)) 
