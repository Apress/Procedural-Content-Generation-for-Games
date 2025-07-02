import numpy as np

import bmesh
import bpy
from mathutils import Vector
from mathutils import noise

from enum import Enum, unique
from math import ceil, floor, log2, pow
import timeit
import random

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
            
#------------------------------------------------------------------------------------------------------------------            
bl_noise_basis_options = ['BLENDER','PERLIN_ORIGINAL','PERLIN_NEW','VORONOI_F1','VORONOI_F2','VORONOI_F3','VORONOI_F4',\
    'VORONOI_F2F1','VORONOI_CRACKLE','CELLNOISE']

@unique
class ElevType(str, Enum):
    Random = "random"
    DiamondSquare = "diamond_square"
    HybridMultiFractal = "hybrid_multi_fractal"
    BlenderMultiFractal = "blender_multi_fractal"
    BlenderHeteroTerrain = "blender_hetero_terrain"
    
@unique
class InterpType(str, Enum):
    Bilinear = "bilinear"
    Bicubic = "bicubic"

#------------------------------------------------------------------------------------------------------------------

def cubic(x):
    return -2*pow(x, 3) + 3*pow(x, 2)

def bidir_interp(interp_type, verts, row_lines, col_lines, step_size):
    half_step = step_size/2
    for row in range(row_lines):
        for col in range(col_lines):
            rq = row//step_size
            rr = row%step_size
            r_sm = step_size*rq
            r_lg = r_sm+step_size
            r_lg = np.clip(r_lg, r_sm, row_lines-1)
            r_cls = r_sm if rr <= half_step else r_lg
            
            cq = col//step_size
            cr = col%step_size
            c_sm = step_size*cq
            c_lg = c_sm+step_size
            c_lg = np.clip(c_lg, c_sm, col_lines-1)
            c_cls = c_sm if cr <= half_step else c_lg
            h_itrp, v_itrp = 0, 0
            
            dc_s = 1-((col-c_sm)/step_size)
            dc_l = 1-((c_lg-col)/step_size)
            dr_s = 1-((row-r_sm)/step_size)
            dr_l = 1-((r_lg-row)/step_size)
            
            h_sm = r_cls*col_lines + c_sm
            h_lg = r_cls*col_lines + c_lg
            v_sm = r_sm*col_lines + c_cls
            v_lg = r_lg*col_lines + c_cls
            
            match interp_type:
                case InterpType.Bilinear:
                    h_itrp = dc_s*verts[h_sm][2] + dc_l*verts[h_lg][2]
                    v_itrp = dr_s*verts[v_sm][2] + dr_l*verts[v_lg][2]
                case InterpType.Bicubic:
                    h_itrp = cubic(dc_s)*verts[h_sm][2] + cubic(dc_l)*verts[h_lg][2]
                    v_itrp = cubic(dr_s)*verts[v_sm][2] + cubic(dr_l)*verts[v_lg][2]                               
            
            verts[row*row_lines + col][2] = (h_itrp+v_itrp)*0.5
            
#--------------------------------------------------------------------------------------------------------
            
def gen_random_map(num_pts, h_min, h_max, noise_basis, x, y):
    if noise_basis=='UNIFORM':
        z = np.random.uniform(h_min, h_max, (num_pts,))
        verts = np.stack([x, y, z], axis=-1).reshape(num_pts, 3)
        return verts
    else:
        z = np.zeros(num_pts)
        verts = np.stack([x, y, z], axis=-1).reshape(num_pts, 3)
        z = np.array([noise.noise([v[0]*0.05, v[1]*0.05, 1], noise_basis=noise_basis)*20 for v in verts])
        verts = np.stack([x, y, z], axis=-1).reshape(num_pts, 3)
        return verts
            
def fbm_sum(verts, interp_type, noise_basis, unit_size, h_min, h_max, num_octaves, row_lines, col_lines, num_pts, x, y):
    if unit_size < 1 or num_octaves < 1:
        return
    div_pow = [int(pow(2, i)) for i in range(0, num_octaves)]
    for dp in div_pow:
        step_size = floor(unit_size//dp)
        if step_size < 1:
            break
        
        verts_this_oct = gen_random_map(num_pts, h_min, h_max, noise_basis, x, y)
        bidir_interp(interp_type, verts_this_oct, row_lines, col_lines, step_size)
        verts += (1/dp)*verts_this_oct
        
#--------------------------------------------------------------------------------------------------------

def sample_ds_noise(h_min, h_max):
    dsn = (h_max-h_min)*np.random.sample()+h_min
    return dsn

def diamond_square_step(s, grid, h_min, h_max):
    h, w  = grid.shape
    for r in range(0, h, s):
        for c in range(0, w, s):
            r_s = (r+s)%h
            c_s = (c+s)%w
            square = np.array([grid[r][c], grid[r][c_s], grid[r_s][c_s], grid[r_s][c]])
            hs = s//2
            sc = np.mean(square) + sample_ds_noise(h_min, h_max)
            r_hs = (r+hs)%h
            c_hs = (c+hs)%w
            grid[r_hs][c_hs] = sc
                      
            diamond_0 = np.array([grid[r_hs][(c-hs)%w], grid[r][c], sc, grid[r_s][c]])
            grid[r_hs][c] = np.mean(diamond_0) + np.random.uniform(h_min, h_max)
            
            diamond_1 = np.array([grid[r][c], grid[(r-hs)%h][c_hs], grid[r][c_s], sc])
            grid[r][c_hs] = np.mean(diamond_1) + np.random.uniform(h_min, h_max)
            
            diamond_2 = np.array([sc, grid[r][c_s], grid[r_hs][(c+s+hs)%w], grid[r_s][c_s]])
            grid[r_hs][c_s] = np.mean(diamond_2) + np.random.uniform(h_min, h_max)
            
            diamond_3 = np.array([grid[r_s][c], sc, grid[r_s][c_s], grid[(r+s+hs)%h][c_hs]])
            grid[r_s][c_hs] = np.mean(diamond_3) + np.random.uniform(h_min, h_max)
            
def diamond_square(n, grid, h_min, h_max, r_decay_factor):
    step = n-1
    while step >= 1:
        diamond_square_step(step, grid, h_min, h_max)
        step = step//2
        decay = pow(2, -r_decay_factor)
        h_min *= decay
        h_max *= decay
        
    return grid

def gen_diamond_square_map(row_lines, num_pts, h_min, h_max):
    n = row_lines
    ds_grid = np.zeros((n,n), dtype=np.float16)
    h_range = h_max-h_min

    ds_grid[0, 0] = sample_ds_noise(h_min, h_max)
    ds_grid[0, n-1] = sample_ds_noise(h_min, h_max)
    ds_grid[n-1, 0] = sample_ds_noise(h_min, h_max)
    ds_grid[n-1, n-1] = sample_ds_noise(h_min, h_max)
    
    diamond_square(n, ds_grid, h_min, h_max, 0.3)
    z = ds_grid.flatten()
    return z
    
#-------------------------------------------------------------------------------------------------------

def hybrid_multi_fractal2(v, H=0.25, lacunarity=2, octaves=10, offset=0.7, noise_basis='BLENDER'):
    exp_array = []
    frequency = 1.0
    for i in range(octaves+1):
        exp_array.append(pow(frequency, -H))
        frequency *= lacunarity

    for i in range(octaves):
        if i == 0:
            altitude = (noise.noise(v, noise_basis=noise_basis) + offset) * exp_array[0]
            weight = altitude
        else:
            weight = min(weight, 1.0)
            signal = (noise.noise(v, noise_basis=noise_basis) + offset) * exp_array[i]
            altitude += weight * signal
            weight *= signal

        v = [v[i]*lacunarity for i in range(3)]

    return altitude

#-------------------------------------------------------------------------------------------------------

def create_blank_height_map(rows, cols, elev_type):
    if elev_type == ElevType.DiamondSquare:
        rows = 2**ceil(log2(rows-1))
        cols = rows
    row_lines = rows + 1
    col_lines = cols + 1
    num_pts = row_lines*col_lines
    
    v_indices = np.arange(0, num_pts, 1).reshape((row_lines, col_lines))
    h_edges = np.zeros((row_lines, cols*2), dtype=np.int32)
    v_edges = np.zeros((rows, col_lines*2), dtype=np.int32)

    for i in range(row_lines):
        h_edges[i][0::2] = v_indices[i][:-1]
        h_edges[i][1::2] = v_indices[i][1:]
        if i < rows:
            v_edges[i][0::2] = v_indices[i]
            v_edges[i][1::2] = v_indices[i+1]
    
    num_edges = row_lines*cols + rows*col_lines
    edges = np.concatenate((h_edges.flatten(), v_edges.flatten())).reshape(num_edges, 2).tolist()
    
    x = np.arange(0, col_lines, 1)
    x = np.stack([x for i in range(row_lines)]).flatten()
    y = np.arange(0, row_lines, 1).reshape((row_lines, 1))
    y = np.hstack([y for i in range(col_lines)]).reshape((row_lines, col_lines)).flatten()
    z = np.zeros(num_pts)
        
    return row_lines, col_lines, num_pts, edges, x, y, z

def create_mesh_obj(context, elev_type, noise_basis, verts, edges):
    grid_mesh_data = bpy.data.meshes.new(name=elev_type+"_"+noise_basis+"_grid_mesh")
    grid_mesh_data.from_pydata(verts, edges, [])
    grid_mesh_data.update(calc_edges=True)
    grid_mesh_obj = bpy.data.objects.new(name=elev_type+"_"+noise_basis+"_grid_obj", object_data=grid_mesh_data)
    context.collection.objects.link(grid_mesh_obj)
    return grid_mesh_obj

def add_border(z, row_lines, col_lines, elev_type):
    zero_row = np.zeros(col_lines)
    border = 5 if elev_type == ElevType.Random or elev_type == ElevType.DiamondSquare else 1
    zero_border = np.zeros(border)

    for r in range(row_lines):
        i = col_lines*r
        top_border = r < border
        bot_border = r >= row_lines-border
        if top_border or bot_border:
                z[i:(i+col_lines)] = zero_row
        else:
            z[i:(i+border)] = zero_border
            z[(i+col_lines-border):(i+col_lines)] = zero_border
            
def resize_move_and_fill(context, grid_mesh_obj, cell_width, origin):
    for obj in context.view_layer.objects:
        obj.select_set(False)
    context.view_layer.objects.active = grid_mesh_obj
    grid_mesh_obj.select_set(True)
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**c_o):
        bpy.ops.object.mode_set(mode='OBJECT')
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with context.temp_override(**c_o):        
        bpy.ops.transform.resize(value=(cell_width, cell_width, 1))
        bpy.ops.transform.translate(value=origin)
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**c_o):
        bpy.ops.object.mode_set(mode='EDIT')
        
    c_o = get_context_override(context, 'VIEW_3D', 'WINDOW')
    with bpy.context.temp_override(**c_o):
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.edge_face_add()
        bpy.ops.object.mode_set(mode='OBJECT')
        
#-------------------------------------------------------------------------------------------------------

def add_modifiers(is_fractal, grid_mesh_obj):
    if is_fractal:
        subsurf_mod = grid_mesh_obj.modifiers.new(grid_mesh_obj.name+"_subsurf_mod", 'SUBSURF')
        subsurf_mod.levels = 1
    else:
        decimate_mod = grid_mesh_obj.modifiers.new(grid_mesh_obj.name+"_decimate_mod", 'DECIMATE')
        decimate_mod.decimate_type = 'UNSUBDIV'
        decimate_mod.iterations = 3
    
        subsurf_mod = grid_mesh_obj.modifiers.new(grid_mesh_obj.name+"_subsurf_mod", 'SUBSURF')
        subsurf_mod.levels = 2  

def finish_mesh(context, cell_width, origin, elev_type, chop_border, noise_basis, row_lines, col_lines, num_pts, edges, x, y, z, is_fractal):
    if chop_border:
        add_border(z, row_lines, col_lines, elev_type)    
    verts = np.stack([x, y, z], axis=-1).reshape(num_pts, 3)
    verts = verts.tolist()
    
    grid_mesh_obj = create_mesh_obj(context, elev_type, noise_basis, verts, edges)    
    resize_move_and_fill(context, grid_mesh_obj, cell_width, origin)
    add_modifiers(is_fractal, grid_mesh_obj) 

def gen_hybrid_multi_fractal_mesh(context, rows, cols, cell_width, origin, chop_border, noise_basis, \
    xy_scale=0.025, lacunarity=3, octaves=5, offset=0.25, z_scale=1):
    elev_type = ElevType.HybridMultiFractal
    row_lines, col_lines, num_pts, edges, x, y, z = create_blank_height_map(rows, cols, elev_type)
    verts = np.stack([x, y, z], axis=-1).reshape(num_pts, 3)
    verts = verts.tolist()

    z = [hybrid_multi_fractal2([v[0]*xy_scale, v[1]*xy_scale, 1], H=0.25, lacunarity=lacunarity, octaves=octaves, offset=offset, noise_basis=noise_basis)*z_scale for v in verts]
    
    finish_mesh(context, cell_width, origin, elev_type, chop_border, noise_basis, row_lines, col_lines, num_pts, edges, x, y, z, True)

def gen_bl_fractal_mesh(context, rows, cols, cell_width, origin, elev_type=ElevType.HybridMultiFractal, \
    chop_border=True, noise_basis='PERLIN_NEW', z_scale=1):
    
    row_lines, col_lines, num_pts, edges, x, y, z = create_blank_height_map(rows, cols, elev_type)
    verts = np.stack([x, y, z], axis=-1).reshape(num_pts, 3)
    verts = verts.tolist()
    
    match elev_type:
        case ElevType.BlenderMultiFractal:
            z = [noise.multi_fractal((v[0]*0.01, v[1]*0.01, 1), 0.7, 2.0, 8, noise_basis=noise_basis)*z_scale for v in verts]
        case ElevType.BlenderHeteroTerrain:
            z = [noise.hetero_terrain((v[0]*0.01, v[1]*0.01, 1), 0.25, 2, 10, 0.5, noise_basis=noise_basis)*z_scale for v in  verts]
    
    finish_mesh(context, cell_width, origin, elev_type, chop_border, noise_basis, row_lines, col_lines, num_pts, edges, x, y, z, True)

def gen_ds_mesh(context, rows, cols, cell_width, origin, unit_size=10, h_min=-50, h_max=50, chop_border=True):
    elev_type = ElevType.DiamondSquare
    row_lines, col_lines, num_pts, edges, x, y, z = create_blank_height_map(rows, cols, elev_type)
    z = gen_diamond_square_map(row_lines, num_pts, h_min, h_max)
    verts = np.stack([x, y, z], axis=-1).reshape(num_pts, 3)
    bidir_interp(InterpType.Bicubic, verts, row_lines, col_lines, unit_size)
    z = verts[:,2]
    finish_mesh(context, cell_width, origin, elev_type, chop_border, 'UNIFORM', row_lines, col_lines, num_pts, edges, x, y, z, False)
    
def gen_random_fbm_mesh(context, rows, cols, cell_width, origin, noise_basis, unit_size=5, h_min=-50, h_max=50, num_octaves=4, chop_border=True):
    elev_type = ElevType.Random
    row_lines, col_lines, num_pts, edges, x, y, z = create_blank_height_map(rows, cols, elev_type)
    
    verts = np.zeros((num_pts, 3))
    fbm_unit_size = pow(2, num_octaves-1)*unit_size
    fbm_sum(verts, InterpType.Bicubic, noise_basis, fbm_unit_size, h_min, h_max, num_octaves, row_lines, col_lines, num_pts, x, y)

    z = verts[:,2]
    finish_mesh(context, cell_width, origin, elev_type, chop_border, noise_basis+"_"+str(num_octaves), row_lines, col_lines, \
        num_pts, edges, x, y, z, False)
    
def gen_random_mesh(context, rows, cols, cell_width, origin, noise_basis, unit_size=5, h_min=-50, h_max=50, chop_border=True):
    elev_type = ElevType.Random
    row_lines, col_lines, num_pts, edges, x, y, z = create_blank_height_map(rows, cols, elev_type)
    
    verts = gen_random_map(num_pts, h_min, h_max, noise_basis, x, y)
    bidir_interp(InterpType.Bicubic, verts, row_lines, col_lines, 10)

    z = verts[:,2]
    finish_mesh(context, cell_width, origin, elev_type, chop_border, noise_basis, row_lines, col_lines, num_pts, edges, x, y, z, False)
    
def test_random_fbm_ds():
    gen_random_mesh(bpy.context, rows=120, cols=120, cell_width=1, origin=(0,0,1), noise_basis='UNIFORM', unit_size=5, h_min=-50, h_max=50, chop_border=True)
    gen_random_fbm_mesh(bpy.context, rows=120, cols=120, cell_width=1, origin=(125,0,1), noise_basis='UNIFORM', unit_size=5, h_min=-50, h_max=50, num_octaves=3, chop_border=True)
    gen_random_fbm_mesh(bpy.context, rows=120, cols=120, cell_width=1, origin=(250,0,1), noise_basis='UNIFORM', unit_size=5, h_min=-50, h_max=50, num_octaves=4, chop_border=True)
    gen_ds_mesh(bpy.context, rows=100, cols=100, cell_width=1, origin=(375,0,1), h_min=-50, h_max=50, unit_size=5, chop_border=True)
    
    y = 135
    for i in range(len(bl_noise_basis_options)):
        noise_basis = bl_noise_basis_options[i]
        gen_random_fbm_mesh(bpy.context, rows=100, cols=100, cell_width=1, origin=(105*i,y,1), noise_basis=noise_basis, unit_size=1, \
            h_min=-25, h_max=50, num_octaves=4, chop_border=True)
            
    return y
    
def test_hybrid_multi_fractal(y, tile_w):
    spacing = tile_w+5
    y += spacing
    
    hmf_z_scale = {'BLENDER':15,'PERLIN_ORIGINAL':15,'PERLIN_NEW':15,'VORONOI_F1':15,'VORONOI_F2':10,'VORONOI_F3':5,'VORONOI_F4':5,\
        'VORONOI_F2F1':15,'VORONOI_CRACKLE':2.5,'CELLNOISE':10}
        
    for i in range(len(bl_noise_basis_options)):
        noise_basis = bl_noise_basis_options[i]
        z_scale = hmf_z_scale[noise_basis]
        gen_hybrid_multi_fractal_mesh(bpy.context, rows=tile_w, cols=tile_w, cell_width=1, origin=(spacing*i,y,1), chop_border=True, \
            noise_basis=noise_basis, xy_scale=0.025, lacunarity=3, octaves=5, offset=0.25, z_scale=z_scale)
        
    y += spacing
    for i in range(len(bl_noise_basis_options)):
        noise_basis = bl_noise_basis_options[i]
        z_scale = hmf_z_scale[noise_basis]*0.5
        gen_hybrid_multi_fractal_mesh(bpy.context, rows=tile_w, cols=tile_w, cell_width=1, origin=(spacing*i,y,1), chop_border=True, \
            noise_basis=noise_basis, xy_scale=0.05, lacunarity=2, octaves=8, offset=0.5, z_scale=z_scale)
            
    return y
            
def test_bl_fractal_functions(y, tile_w):
    spacing = tile_w+5
    y += spacing
    blmf_z_scale = {'BLENDER':10,'PERLIN_ORIGINAL':10,'PERLIN_NEW':10,'VORONOI_F1':10,'VORONOI_F2':5,'VORONOI_F3':2.5,'VORONOI_F4':2.5,\
        'VORONOI_F2F1':25,'VORONOI_CRACKLE':2,'CELLNOISE':5}
    for i in range(len(bl_noise_basis_options)):
        noise_basis = bl_noise_basis_options[i]
        z_scale = blmf_z_scale[noise_basis]
        gen_bl_fractal_mesh(bpy.context, rows=100, cols=100, cell_width=1, origin=(spacing*i,y,1), \
            elev_type=ElevType.BlenderMultiFractal, noise_basis=noise_basis, z_scale=z_scale)
            
    y += spacing
    blht_z_scale = {'BLENDER':1,'PERLIN_ORIGINAL':1,'PERLIN_NEW':1,'VORONOI_F1':1,'VORONOI_F2':0.1,'VORONOI_F3':0.05,'VORONOI_F4':0.05,\
        'VORONOI_F2F1':15,'VORONOI_CRACKLE':0.05,'CELLNOISE':0.5}
    for i in range(len(bl_noise_basis_options)):
        noise_basis = bl_noise_basis_options[i]
        z_scale = blht_z_scale[noise_basis]
        gen_bl_fractal_mesh(bpy.context, rows=100, cols=100, cell_width=1, origin=(spacing*i,y,1), \
            elev_type=ElevType.BlenderHeteroTerrain, noise_basis=noise_basis, z_scale=z_scale)
            
    return y
    
if __name__ == "__main__":
    start = timeit.default_timer()
    
    np.random.seed(100)
    y = test_random_fbm_ds()
    y = test_hybrid_multi_fractal(y, 100)
    test_bl_fractal_functions(y, 100)
            
    stop = timeit.default_timer()
    print("Gen all test models runime: ", stop - start)
    