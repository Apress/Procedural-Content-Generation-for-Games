import bpy
import bmesh
from math import radians
from mathutils import Matrix
from mathutils import Vector
import copy
from copy import deepcopy
import os, sys
from random import uniform
from typing import List

script_dir = ""
if bpy.context.space_data and bpy.context.space_data.text:
    script_filepath = bpy.context.space_data.text.filepath
    if script_filepath:
        script_dir = os.path.dirname(script_filepath)
        if not script_dir in sys.path:
            sys.path.append(script_dir)

d = 3
theta_90 = [90.0, 90.0, 90.0] #degs
theta_60 = [60.0, 60.0, 60.0] #degs
theta_30 = [30.0, 30.0, 30.0] #degs
theta_22_5 = [22.5, 22.5, 22.5]

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

def rewrite(axiom: str, rewriting_rules: dict, num_iter: int):
    str_output = axiom
    for i in range(num_iter):
        str_this_iter = ""
        for c in str_output:
            rewritten = False            
            for predecessor, successor in rewriting_rules.items():
                if c == predecessor:
                    str_this_iter += successor
                    rewritten = True
                    break
            if not rewritten:
                str_this_iter += c
        str_output = str_this_iter

    return str_output

class turtle_2D:
    def __init__(self, context, axiom: str, rewriting_rules: dict, num_iters: int, theta: List[float], step_dist: float, \
        curve_obj_name: str, origin: Vector):
        self.cur_str = rewrite(axiom, rewriting_rules, num_iters)
        self.theta = theta
        self.step_dist = step_dist
        
        curve_data = bpy.data.curves.new(name=curve_obj_name+"_data", type='CURVE')
        curve_data.dimensions = '3D'
        self.curve_obj = bpy.data.objects.new(name=curve_obj_name, object_data=curve_data)
        spline_data = self.curve_obj.data.splines.new(type='POLY')
        spline_data.points[0].co = [origin[0], origin[1], origin[2], 0]
        context.collection.objects.link(self.curve_obj)
        
        self.heading = Vector((0.0, 0.0, 1.0))
        self.lcs = self.curve_obj.matrix_local.copy().to_3x3()

    def draw(self):
        for c in self.cur_str:                
            if c == "F":
                self.one_step_forward()
            elif c == "+": # Turn LEFT
                mat_rot = Matrix.Rotation(radians(-self.theta[2]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "-": # Turn RIGHT
                mat_rot = Matrix.Rotation(radians(self.theta[2]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()

    def one_step_forward(self):
        spline_data = self.curve_obj.data.splines[-1]
        last_spline_pt = spline_data.points[-1]
        start_pt = Vector((last_spline_pt.co[0], last_spline_pt.co[1], last_spline_pt.co[2]))
        trans_vec = self.heading * self.step_dist
        end_pt = start_pt + trans_vec
        spline_data.points.add(1)
        spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]

class turtle_2D_skip:
    def __init__(self, context, axiom: str, rewriting_rules: dict, num_iters: int, theta: List[float], step_dist: float, \
        curve_obj_name: str, origin: Vector):
        self.cur_str = rewrite(axiom, rewriting_rules, num_iters)
        self.theta = theta
        self.step_dist = step_dist
        
        curve_data = bpy.data.curves.new(name=curve_obj_name+"_data", type='CURVE')
        curve_data.dimensions = '3D'
        self.curve_obj = bpy.data.objects.new(name=curve_obj_name, object_data=curve_data)
        spline_data = self.curve_obj.data.splines.new(type='POLY')
        spline_data.points[0].co = [origin[0], origin[1], origin[2], 0]
        context.collection.objects.link(self.curve_obj)
        
        self.heading = Vector((0.0, 0.0, 1.0))
        self.lcs = self.curve_obj.matrix_local.copy().to_3x3()

    def draw(self):
        for c in self.cur_str:
            if c == "F":
                self.one_step_forward(True)
            elif c == "f":
                self.one_step_forward(False)
            elif c == "+": # Turn LEFT
                mat_rot = Matrix.Rotation(radians(-self.theta[2]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "-": # Turn RIGHT
                mat_rot = Matrix.Rotation(radians(self.theta[2]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()

    def one_step_forward(self, should_draw: bool=True):
        spline_data = self.curve_obj.data.splines[-1]
        last_spline_pt = spline_data.points[-1]
        start_pt = Vector((last_spline_pt.co[0], last_spline_pt.co[1], last_spline_pt.co[2]))
        trans_vec = self.heading * self.step_dist
        end_pt = start_pt + trans_vec
            
        if should_draw:
            spline_data.points.add(1)
        else: # Start a new spline at the end point.
            spline_data = self.curve_obj.data.splines.new(type='POLY')
            
        spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]
            
class turtle_2D_branching:
    def __init__(self, context, axiom: str, rewriting_rules: dict, num_iters: int, theta: List[float], step_dist: float, \
        curve_obj_name: str, origin: Vector):
        self.cur_str = rewrite(axiom, rewriting_rules, num_iters)
        self.theta = theta
        self.step_dist = step_dist
        
        curve_data = bpy.data.curves.new(name=curve_obj_name+"_data", type='CURVE')
        curve_data.dimensions = '3D'
        self.curve_obj = bpy.data.objects.new(name=curve_obj_name, object_data=curve_data)
        spline_data = self.curve_obj.data.splines.new(type='POLY')
        spline_data.points[0].co = [origin[0], origin[1], origin[2], 0]
        context.collection.objects.link(self.curve_obj)
        
        self.heading = Vector((0.0, 0.0, 1.0))
        self.lcs = self.curve_obj.matrix_local.copy().to_3x3()
        
        self.stack = []
        self.prev_popped_pt = []
        self.prev_step_popped = False
        self.last_pt_stats = [0, 0]
                
    def draw(self):
        for c in self.cur_str:
            if self.prev_step_popped:
                self.last_pt_stats[0], self.last_pt_stats[1], self.heading, self.lcs = self.prev_popped_pt
                self.prev_step_popped = False
                self.prev_popped_pt.clear()
                
            last_spline_pt = self.curve_obj.data.splines[self.last_pt_stats[0]].points[self.last_pt_stats[1]]
                
            if c == "[":
                self.stack.append([self.last_pt_stats[0], self.last_pt_stats[1], copy.deepcopy(self.heading), copy.deepcopy(self.lcs)])
                spline_data = self.curve_obj.data.splines.new(type='POLY')
                spline_data.points[-1].co = last_spline_pt.co
                self.last_pt_stats = [len(self.curve_obj.data.splines)-1, 0]
            elif c == "]":
                if len(self.stack) > 0:
                    self.prev_popped_pt = self.stack.pop()
                    self.prev_step_popped = True                    
            elif c == "F":
                self.one_step_forward(True, last_spline_pt)
            elif c == "f":
                self.one_step_forward(False, last_spline_pt)
            elif c == "+":
                mat_rot = Matrix.Rotation(radians(-self.theta[2]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "-":
                mat_rot = Matrix.Rotation(radians(self.theta[2]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()

    def one_step_forward(self, should_draw: bool, last_spline_pt):
        start_pt = Vector((last_spline_pt.co[0], last_spline_pt.co[1], last_spline_pt.co[2]))
        if should_draw:
            spline_data = self.curve_obj.data.splines[self.last_pt_stats[0]]
            trans_vec = self.heading * self.step_dist
            end_pt = start_pt + trans_vec
            spline_data.points.add(1)
            spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]
            self.last_pt_stats[1] = len(spline_data.points) - 1
        else: 
            spline_data = self.curve_obj.data.splines.new(type='POLY')
            trans_vec = self.heading * self.step_dist
            end_pt = start_pt + trans_vec
            spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]
            self.last_pt_stats = [len(self.curve_obj.data.splines) - 1, 0]
            
class turtle_3D:
    def __init__(self, context, axiom: str, rewriting_rules: dict, num_iters: int, theta: List[float], step_dist: float, \
        curve_obj_name: str, origin: Vector):
        self.cur_str = rewrite(axiom, rewriting_rules, num_iters)
        self.theta = theta
        self.step_dist = step_dist
        
        curve_data = bpy.data.curves.new(name=curve_obj_name+"_data", type='CURVE')
        curve_data.dimensions = '3D'
        self.curve_obj = bpy.data.objects.new(name=curve_obj_name, object_data=curve_data)
        spline_data = self.curve_obj.data.splines.new(type='POLY')
        spline_data.points[0].co = [origin[0], origin[1], origin[2], 0]
        context.collection.objects.link(self.curve_obj)
        
        self.heading = Vector((0.0, 0.0, 1.0))
        self.lcs = self.curve_obj.matrix_local.copy().to_3x3()
        
        self.stack = []
        self.prev_popped_pt = []
        self.prev_step_popped = False
        self.last_pt_stats = [0, 0]

    def draw(self):
        for c in self.cur_str:
            if self.prev_step_popped:
                self.last_pt_stats[0], self.last_pt_stats[1], self.heading, self.lcs = self.prev_popped_pt
                self.prev_step_popped = False
                self.prev_popped_pt.clear()
                
            last_spline_pt = self.curve_obj.data.splines[self.last_pt_stats[0]].points[self.last_pt_stats[1]]
                
            if c == "[":
                self.stack.append([self.last_pt_stats[0], self.last_pt_stats[1], copy.deepcopy(self.heading), copy.deepcopy(self.lcs)])
                spline_data = self.curve_obj.data.splines.new(type='POLY')
                spline_data.points[-1].co = last_spline_pt.co
                self.last_pt_stats = [len(self.curve_obj.data.splines)-1, 0]
            elif c == "]":
                if len(self.stack) > 0:
                    self.prev_popped_pt = self.stack.pop()
                    self.prev_step_popped = True                    
            elif c == "F":
                self.one_step_forward(True, last_spline_pt)
            elif c == "f":
                self.one_step_forward(False, last_spline_pt)
            elif c == "+": # Turn LEFT
                mat_rot = Matrix.Rotation(radians(-self.theta[1]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "-": # Turn RIGHT
                mat_rot = Matrix.Rotation(radians(self.theta[1]), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "&": # Pitch down
                mat_rot = Matrix.Rotation(radians(self.theta[0]), 3, 'X')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "^": # Pitch up
                mat_rot = Matrix.Rotation(radians(-self.theta[0]), 3, 'X')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "\\": # Roll left
                mat_rot = Matrix.Rotation(radians(-self.theta[2]), 3, 'Z')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "/": # Roll right
                mat_rot = Matrix.Rotation(radians(self.theta[2]), 3, 'Z')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "|": # Turn around
                mat_rot = Matrix.Rotation(radians(180), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()                                

    def one_step_forward(self, should_draw: bool, last_spline_pt):
        start_pt = Vector((last_spline_pt.co[0], last_spline_pt.co[1], last_spline_pt.co[2]))
        if should_draw:
            spline_data = self.curve_obj.data.splines[self.last_pt_stats[0]]
            trans_vec = self.heading * self.step_dist
            end_pt = start_pt + trans_vec
            spline_data.points.add(1)
            spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]
            self.last_pt_stats[1] = len(spline_data.points) - 1
        else: 
            spline_data = self.curve_obj.data.splines.new(type='POLY')
            trans_vec = self.heading * self.step_dist
            end_pt = start_pt + trans_vec
            spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]
            self.last_pt_stats = [len(self.curve_obj.data.splines) - 1, 0]
            
    def pipe(self, context, subsurf_level=1, solidify_thickness=1, apply_modifiers=True):
        for obj in context.view_layer.objects:
            obj.select_set(False)
        context.view_layer.objects.active = self.curve_obj
        self.curve_obj.select_set(True)
        
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.mode_set(mode='OBJECT')
            
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.convert(target='MESH')

        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.mode_set(mode='EDIT')
            
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles()
            bpy.ops.mesh.normals_make_consistent(inside=False)
            
        self.mesh_obj = context.view_layer.objects[self.curve_obj.name]
        
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            skin_mod = self.mesh_obj.modifiers.new("skin_mod", 'SKIN')
            skin_mod.branch_smoothing = 1
            
            solidify_mod = self.mesh_obj.modifiers.new("solidify_mod", 'SOLIDIFY')
            solidify_mod.offset = 0
            solidify_mod.thickness = solidify_thickness
            
            weld_mod = self.mesh_obj.modifiers.new("weld_mod", 'WELD')
                     
            subsurf_mod = self.mesh_obj.modifiers.new("subsurf_mod", 'SUBSURF')
            subsurf_mod.levels = subsurf_level
            subsurf_mod.render_levels = subsurf_level
            subsurf_mod.subdivision_type = 'CATMULL_CLARK'
            
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.mode_set(mode='OBJECT')
            
            
        if apply_modifiers:
            context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
            with bpy.context.temp_override(**context_override):
                bpy.ops.object.modifier_apply(modifier=skin_mod.name)
                bpy.ops.object.modifier_apply(modifier=solidify_mod.name)
                bpy.ops.object.modifier_apply(modifier=weld_mod.name)
                bpy.ops.object.modifier_apply(modifier=subsurf_mod.name)
                
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
            bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
            
class turtle_3D_sample_ranges:
    def __init__(self, context, axiom: str, rewriting_rules: dict, num_iters: int, theta: List, step_dist: List, \
        curve_obj_name: str, origin: Vector):
        self.cur_str = rewrite(axiom, rewriting_rules, num_iters)
        self.theta = theta
        self.step_dist = step_dist
        
        curve_data = bpy.data.curves.new(name=curve_obj_name+"_data", type='CURVE')
        curve_data.dimensions = '3D'
        self.curve_obj = bpy.data.objects.new(name=curve_obj_name, object_data=curve_data)
        spline_data = self.curve_obj.data.splines.new(type='POLY')
        spline_data.points[0].co = [origin[0], origin[1], origin[2], 0]
        context.collection.objects.link(self.curve_obj)
        
        self.heading = Vector((0.0, 0.0, 1.0))
        self.lcs = self.curve_obj.matrix_local.copy().to_3x3()
        
        self.stack = []
        self.prev_popped_pt = []
        self.prev_step_popped = False
        self.last_pt_stats = [0, 0]

    def draw(self):
        for c in self.cur_str:
            if self.prev_step_popped:
                self.last_pt_stats[0], self.last_pt_stats[1], self.heading, self.lcs = self.prev_popped_pt
                self.prev_step_popped = False
                self.prev_popped_pt.clear()
                
            last_spline_pt = self.curve_obj.data.splines[self.last_pt_stats[0]].points[self.last_pt_stats[1]]
                
            if c == "[":
                self.stack.append([self.last_pt_stats[0], self.last_pt_stats[1], copy.deepcopy(self.heading), copy.deepcopy(self.lcs)])
                spline_data = self.curve_obj.data.splines.new(type='POLY')
                spline_data.points[-1].co = last_spline_pt.co
                self.last_pt_stats = [len(self.curve_obj.data.splines)-1, 0]
            elif c == "]":
                if len(self.stack) > 0:
                    self.prev_popped_pt = self.stack.pop()
                    self.prev_step_popped = True                    
            elif c == "F":
                self.one_step_forward(True, last_spline_pt)
            elif c == "f":
                self.one_step_forward(False, last_spline_pt)
            elif c == "+": # Turn LEFT
                angle_deg = uniform(self.theta[1][0], self.theta[1][1])
                mat_rot = Matrix.Rotation(radians(-angle_deg), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "-": # Turn RIGHT
                angle_deg = uniform(self.theta[1][0], self.theta[1][1])
                mat_rot = Matrix.Rotation(radians(angle_deg), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "&": # Pitch down
                angle_deg = uniform(self.theta[0][0], self.theta[0][1])
                mat_rot = Matrix.Rotation(radians(angle_deg), 3, 'X')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "^": # Pitch up
                angle_deg = uniform(self.theta[0][0], self.theta[0][1])
                mat_rot = Matrix.Rotation(radians(-angle_deg), 3, 'X')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "\\": # Roll left
                angle_deg = uniform(self.theta[2][0], self.theta[2][1])
                mat_rot = Matrix.Rotation(radians(-angle_deg), 3, 'Z')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "/": # Roll right
                angle_deg = uniform(self.theta[2][0], self.theta[2][1])
                mat_rot = Matrix.Rotation(radians(angle_deg), 3, 'Z')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()
            elif c == "|": # Turn around
                mat_rot = Matrix.Rotation(radians(180), 3, 'Y')
                self.lcs.rotate(mat_rot)
                self.heading = self.lcs[2]
                self.heading.normalize()                                

    def one_step_forward(self, should_draw: bool, last_spline_pt):
        start_pt = Vector((last_spline_pt.co[0], last_spline_pt.co[1], last_spline_pt.co[2]))
        if should_draw:
            spline_data = self.curve_obj.data.splines[self.last_pt_stats[0]]
            trans_vec = self.heading * uniform(self.step_dist[0], self.step_dist[1])
            end_pt = start_pt + trans_vec
            spline_data.points.add(1)
            spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]
            self.last_pt_stats[1] = len(spline_data.points) - 1
        else: 
            spline_data = self.curve_obj.data.splines.new(type='POLY')
            trans_vec = self.heading * uniform(self.step_dist[0], self.step_dist[1])
            end_pt = start_pt + trans_vec
            spline_data.points[-1].co = [end_pt[0], end_pt[1], end_pt[2], 0]
            self.last_pt_stats = [len(self.curve_obj.data.splines) - 1, 0]
            
    def pipe(self, context, subsurf_level=1, solidify_thickness=1, apply_modifiers=True):
        for obj in context.view_layer.objects:
            obj.select_set(False)
        context.view_layer.objects.active = self.curve_obj
        self.curve_obj.select_set(True)
        
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.mode_set(mode='OBJECT')
            
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.convert(target='MESH')

        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.mode_set(mode='EDIT')
            
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles()
            bpy.ops.mesh.normals_make_consistent(inside=False)
            
        self.mesh_obj = context.view_layer.objects[self.curve_obj.name]
        
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            skin_mod = self.mesh_obj.modifiers.new("skin_mod", 'SKIN')
            skin_mod.branch_smoothing = 1
            
            solidify_mod = self.mesh_obj.modifiers.new("solidify_mod", 'SOLIDIFY')
            solidify_mod.offset = 0
            solidify_mod.thickness = solidify_thickness
            
            weld_mod = self.mesh_obj.modifiers.new("weld_mod", 'WELD')
                     
            subsurf_mod = self.mesh_obj.modifiers.new("subsurf_mod", 'SUBSURF')
            subsurf_mod.levels = subsurf_level
            subsurf_mod.render_levels = subsurf_level
            subsurf_mod.subdivision_type = 'CATMULL_CLARK'
            
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.mode_set(mode='OBJECT')
            
            
        if apply_modifiers:
            context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
            with bpy.context.temp_override(**context_override):
                bpy.ops.object.modifier_apply(modifier=skin_mod.name)
                bpy.ops.object.modifier_apply(modifier=solidify_mod.name)
                bpy.ops.object.modifier_apply(modifier=weld_mod.name)
                bpy.ops.object.modifier_apply(modifier=subsurf_mod.name)
                
        context_override = get_context_override(context, 'VIEW_3D', 'WINDOW')
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
            bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
                             
def test_rewrite():
    axiom = "b"
    rewriting_rules = {"a": "ab", "b": "a"}
    
    for i in range(5):
        print("expansion " + str(i) + ": " + rewrite(axiom, rewriting_rules, i))
              
turtle_axiom_koch = "F"
turtle_rewriting_rules_koch = {"F": "F+F--F+F"}

# From p.10 of the book "The Algorithmic Beauty of Plants".
turtle_axiom_islands_lakes = "F+F+F+F"
turtle_rewriting_rules_islands_lakes = {"F": "F+f-FF+F+FF+Ff+FF-f+FF-F-FF-Ff-FFF", "f": "ffffff"}
                
def test_2D():    
    # n = 4, theta = 60
    t_koch_2D = turtle_2D(bpy.context, turtle_axiom_koch, turtle_rewriting_rules_koch, 4, theta_60, d, "2D_Koch_4", Vector((100, 100, 0)))
    t_koch_2D.draw()
    
def test_Koch_iterations():
    # n = 0, theta = 60
    t_koch_2D_0 = turtle_2D(bpy.context, turtle_axiom_koch, turtle_rewriting_rules_koch, 0, theta_60, d, "2D_Koch_0", Vector((100, 0, 0)))
    t_koch_2D_0.draw()
    
    # n = 1, theta = 60
    t_koch_2D_1 = turtle_2D(bpy.context, turtle_axiom_koch, turtle_rewriting_rules_koch, 1, theta_60, d, "2D_Koch_1", Vector((150, 0, 0)))
    t_koch_2D_1.draw()
    
    # n = 2, theta = 60
    t_koch_2D_2 = turtle_2D(bpy.context, turtle_axiom_koch, turtle_rewriting_rules_koch, 2, theta_60, d, "2D_Koch_2", Vector((200, 0, 0)))
    t_koch_2D_2.draw()
    
    # n = 3, theta = 60
    t_koch_2D_3 = turtle_2D(bpy.context, turtle_axiom_koch, turtle_rewriting_rules_koch, 3, theta_60, d, "2D_Koch_3", Vector((250, 0, 0)))
    t_koch_2D_3.draw()
    
    # n = 4, theta = 60
    t_koch_2D_4 = turtle_2D(bpy.context, turtle_axiom_koch, turtle_rewriting_rules_koch, 4, theta_60, d, "2D_Koch_4", Vector((350, 0, 0)))
    t_koch_2D_4.draw()
    
def test_2D_skip():
    t_2D_islands_lakes = turtle_2D_skip(bpy.context, turtle_axiom_islands_lakes, turtle_rewriting_rules_islands_lakes, 2, theta_90, \
        d, "2D_Island_Lakes_2", Vector((100, -100, 0)))
    t_2D_islands_lakes.draw()
    
def test_islands_lakes_iterations():    
    t_2D_islands_lakes_0 = turtle_2D_skip(bpy.context, turtle_axiom_islands_lakes, turtle_rewriting_rules_islands_lakes, 0, theta_90, \
        d, "2D_Island_Lakes_0", Vector((0, 0, 0)))
    t_2D_islands_lakes_0.draw()
    
    t_2D_islands_lakes_0 = turtle_2D_skip(bpy.context, turtle_axiom_islands_lakes, turtle_rewriting_rules_islands_lakes, 1, theta_90, \
        d, "2D_Island_Lakes_1", Vector((50, 0, 0)))
    t_2D_islands_lakes_0.draw()
    
    t_2D_islands_lakes_0 = turtle_2D_skip(bpy.context, turtle_axiom_islands_lakes, turtle_rewriting_rules_islands_lakes, 2, theta_90, \
        d, "2D_Island_Lakes_2", Vector((150, 0, 0)))
    t_2D_islands_lakes_0.draw()
    
def test_2D_branching():
    turtle_axiom_2d_tree1 = "X"
    turtle_rewriting_rules_2d_tree1 = {"X": "F[+X][-X]FX", "F": "FF"}
    t_2D_tree1 = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1, turtle_rewriting_rules_2d_tree1, 2, theta_22_5, 1, \
        "2D_Tree1_2", Vector((0, 100, 0)))
    t_2D_tree1.draw()
    
    turtle_axiom_2d_tree1 = "X"
    turtle_rewriting_rules_2d_tree1 = {"X": "F[+X][-X]FX", "F": "FF"}
    t_2D_tree1 = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1, turtle_rewriting_rules_2d_tree1, 3, theta_22_5, 1, \
        "2D_Tree1_3", Vector((15, 100, 0)))
    t_2D_tree1.draw()
    
    turtle_axiom_2d_tree1 = "X"
    turtle_rewriting_rules_2d_tree1 = {"X": "F[+X][-X]FX", "F": "FF"}
    t_2D_tree1 = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1, turtle_rewriting_rules_2d_tree1, 4, theta_22_5, 1, \
        "2D_Tree1_4", Vector((30, 100, 0)))
    t_2D_tree1.draw()
    
def trees_2D_variations():
    turtle_axiom_2d_tree1 = "X"
    turtle_rewriting_rules_2d_tree1 = {"X": "F[+X][-X]FX", "F": "FF"}
    t_2D_tree1_7iters = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1, turtle_rewriting_rules_2d_tree1, 7, theta_22_5, 1, \
        "2D_Tree1_7iters", Vector((0, 100, 0)))
    t_2D_tree1_7iters.draw()
    
    turtle_axiom_2d_tree1_3Fs = "X"
    turtle_rewriting_rules_2d_tree1_3Fs = {"X": "F[+X][-X]FX", "F": "FFF"}
    t_2D_tree1_3Fs_7iters = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1_3Fs, turtle_rewriting_rules_2d_tree1_3Fs, 7, theta_22_5, 1, \
        "2D_Tree1_3Fs_7iters", Vector((-700, 100, 0)))
    t_2D_tree1_3Fs_7iters.draw()

    turtle_axiom_2d_tree1_longer_L_branches = "X"
    turtle_rewriting_rules_2d_tree1_longer_L_branches = {"X": "F[+X+X][-X]FX", "F": "FF"}
    t_2D_tree1_longer_L_branches_7iters = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1_longer_L_branches, \
        turtle_rewriting_rules_2d_tree1_longer_L_branches, 7, theta_22_5, 1, "2D_Tree1_longer_L_branches", Vector((-250, 100, 0)))
    t_2D_tree1_longer_L_branches_7iters.draw()
    
    turtle_axiom_2d_tree1_multi_R_branches = "X"
    turtle_rewriting_rules_2d_tree1_multi_R_branches = {"X": "F[+X][-X][--X]FX", "F": "FF"}
    t_2D_tree1_multi_R_branches_7iters = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1_multi_R_branches, \
        turtle_rewriting_rules_2d_tree1_multi_R_branches, 7, theta_22_5, 1, "2D_Tree1_multi_R_branches", Vector((-400, 100, 0)))
    t_2D_tree1_multi_R_branches_7iters.draw()
    
    turtle_axiom_2d_tree1_nested_R_branches = "X"
    turtle_rewriting_rules_2d_tree1_nested_R_branches = {"X": "[F[+X][-X][--X]]FX", "F": "FF"}
    t_2D_tree1_nested_R_branches_7iters = turtle_2D_branching(bpy.context, turtle_axiom_2d_tree1_nested_R_branches, \
        turtle_rewriting_rules_2d_tree1_nested_R_branches, 7, theta_22_5, 1, "2D_Tree1_nested_R_branches", Vector((-550, 100, 0)))
    t_2D_tree1_nested_R_branches_7iters.draw()
    
def test_3D_tree():        
    turtle_axiom_3d_tree = "F"
    turtle_rewriting_rules_3d_tree = {"F": "F[-&\F][\++&F][/--^F]||F[--&/F][++^\F][+&F]"}

    t_3D_tree = turtle_3D(bpy.context, turtle_axiom_3d_tree, turtle_rewriting_rules_3d_tree, 3, theta_22_5, 10, "3D_Tree_3", \
        Vector((-100, 200, 0)))
    t_3D_tree.draw()
    t_3D_tree.pipe(bpy.context, subsurf_level=1, solidify_thickness=2, apply_modifiers=False)
    
def test_3D_tree_sample_range():        
    turtle_axiom_3d_tree = "F"
    turtle_rewriting_rules_3d_tree = {"F": "F[-&\F][\++&F][/--^F]||F[--&/F][++^\F][+&F]"}

    theta_ranges_1 = [[30, 60], [20, 40], [30, 60]]
    dist_range_1 = [10, 30]
    t_3D_tree_1 = turtle_3D_sample_ranges(bpy.context, turtle_axiom_3d_tree, turtle_rewriting_rules_3d_tree, 3, \
        theta_ranges_1, dist_range_1, "3D_Tree_3_sample_ranges_1", Vector((-300, 200, 0)))
    t_3D_tree_1.draw()
    t_3D_tree_1.pipe(bpy.context, subsurf_level=1, solidify_thickness=2, apply_modifiers=False)
    
    theta_ranges_2 = [[15, 45], [20, 40], [15, 45]]
    dist_range_2 = [5, 25]
    t_3D_tree_2 = turtle_3D_sample_ranges(bpy.context, turtle_axiom_3d_tree, turtle_rewriting_rules_3d_tree, 3, \
        theta_ranges_2, dist_range_2, "3D_Tree_3_sample_ranges_2", Vector((-500, 200, 0)))
    t_3D_tree_2.draw()
    t_3D_tree_2.pipe(bpy.context, subsurf_level=1, solidify_thickness=2, apply_modifiers=False)

#=============================================================================================
if __name__ == "__main__":
#    test_rewrite()
#    test_2D()
#    test_2D_skip()
#    test_islands_lakes_iterations()
    test_2D_branching()
    trees_2D_variations()
    test_3D_tree()
#    test_3D_tree_sample_range()
#    test_Koch_iterations()
    
