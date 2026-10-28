"""
Parametric folding CNC table base.

Rebuilds the plywood folding cart from TableComplete.FCStd so table-top
length and width drive the side plates, legs, and cross-members.
Plywood thickness is a separate input: it changes extrusion, box-joint
depth, and cross-member span, and does not scale with length or width.
Hole diameters, tab lengths, and fold angles stay at the source values.

Run inside FreeCAD, via FreeCAD MCP execute_code, or with freecadcmd.
All user-editable parameters are grouped at the bottom of this file.
"""

import math
import os

import FreeCAD as App
import Part


WOOD_TOP = (0.78, 0.64, 0.42)
WOOD_LEG = (0.70, 0.54, 0.32)
WOOD_BLACK = (0.12, 0.11, 0.10)
WOOD_STRUT = (0.18, 0.16, 0.14)
WOOD_CASTER = (0.22, 0.20, 0.18)
GHOST = (0.55, 0.62, 0.72)
CNC = (0.40, 0.70, 0.88)


def v(x, y, z=0.0):
    return App.Vector(float(x), float(y), float(z))


def add_part(doc, group, name, shape, color, transparency=0):
    obj = doc.addObject("Part::Feature", name)
    obj.Label = name
    obj.Shape = shape
    if obj.ViewObject:
        obj.ViewObject.ShapeColor = color
        obj.ViewObject.Transparency = transparency
    if group is not None:
        group.addObject(obj)
    return obj


def polygon_face(points):
    closed = list(points)
    if closed[0].distanceToPoint(closed[-1]) > 1e-6:
        closed.append(closed[0])
    return Part.Face(Part.makePolygon(closed))


def rect_face(x0, y0, x1, y1):
    return polygon_face([v(x0, y0), v(x1, y0), v(x1, y1), v(x0, y1)])


def circle_face(cx, cy, radius):
    return Part.Face(Part.Wire([Part.makeCircle(radius, v(cx, cy))]))


def cut_circles(face, holes):
    result = face
    for cx, cy, diameter in holes:
        if diameter > 0.05:
            result = result.cut(circle_face(cx, cy, diameter / 2.0))
    return result


def cut_rects(face, rects):
    result = face
    for x0, y0, x1, y1 in rects:
        result = result.cut(rect_face(x0, y0, x1, y1))
    return result


def unit(vec):
    n = App.Vector(vec)
    if n.Length < 1e-9:
        return App.Vector(1, 0, 0)
    n.normalize()
    return n


def arc_edge(cx, cy, radius, a0, a1):
    """Sweep from a0 to a1. If a1 < a0, take the short signed delta (not a full turn)."""
    delta = a1 - a0
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta < -math.pi:
        delta += 2.0 * math.pi
    # Keep the source 125 deg hinge boss, which is still under 180 deg.
    am = a0 + 0.5 * delta
    a1u = a0 + delta
    p0 = v(cx + radius * math.cos(a0), cy + radius * math.sin(a0))
    pm = v(cx + radius * math.cos(am), cy + radius * math.sin(am))
    p1 = v(cx + radius * math.cos(a1u), cy + radius * math.sin(a1u))
    return Part.Arc(p0, pm, p1).toShape()


def p_on_arc(cx, cy, radius, ang):
    return v(cx + radius * math.cos(ang), cy + radius * math.sin(ang))


def line_edge(p0, p1):
    return Part.makeLine(p0, p1)


def add_line(edges, p0, p1, tol=1e-4):
    if p0.distanceToPoint(p1) > tol:
        edges.append(line_edge(p0, p1))


def face_from_edges(edges):
    wire = Part.Wire(Part.__sortEdges__(edges))
    face = Part.Face(wire)
    if not face.isValid():
        face.fix(1e-4, 1e-4, 1e-4)
    return face


def notch_face(origin, along, inward, length, depth):
    a = unit(along) * length
    n = unit(inward) * depth
    p0 = App.Vector(origin)
    return polygon_face([p0, p0 + a, p0 + a + n, p0 + n])


def diagonal_notch(cfg, g):
    """Notch on the side-plate diagonal, in YZ stored as XY (x=Y, y=Z)."""
    bump_y = g["sy"](cfg["ref_bump_y"])
    boss = g["boss_r"]
    fillet_a = cfg["ref_diag_fillet_angle"]
    diag_y = bump_y + boss * math.cos(fillet_a)
    diag_z = g["pivot_z"] + boss * math.sin(fillet_a)
    diag_u = unit(v(g["front_y"] - diag_y, g["front_top_z"] - diag_z))
    inward = v(-diag_u.y, diag_u.x)
    if inward.x * (g["inner_y"] - diag_y) + inward.y * (g["shelf_z"] - diag_z) < 0:
        inward = v(-inward.x, -inward.y)
    origin = v(diag_y, diag_z) + diag_u * cfg["diag_notch_from_fillet_mm"]
    return origin, diag_u, inward, diag_y, diag_z


def strut_notches(cfg, g):
    """Named (origin, along, inward) notches that take a 50 mm stretcher."""
    h = cfg["strut_height_mm"]
    strut_z1 = g["strut_z_c"] + h / 2.0 + g["play"]
    origin_diag, diag_u, inward_diag, _, _ = diagonal_notch(cfg, g)
    items = [
        ("StrutInner", v(g["inner_y"], strut_z1), v(0, -1), v(1, 0)),
        ("StrutShelf", v(g["inner_y"], g["shelf_z"]), v(-1, 0), v(0, -1)),
        ("StrutDiag", origin_diag, diag_u, inward_diag),
    ]
    bot_z = g["sz"](cfg["ref_leg_front_bot_cz"]) + cfg["leg_fillet_mm"] * math.sin(
        cfg["ref_leg_front_bot_a1"]
    )
    for i, (y0_ref, y1_ref) in enumerate(cfg["ref_leg_notches_y"], 1):
        y0 = g["sy"](y0_ref)
        y1 = g["sy"](y1_ref)
        items.append(("StrutLeg%d" % i, v(min(y0, y1), bot_z), v(1, 0), v(0, 1)))
    return items


def place_strut(face, thickness, origin, along, inward, notch_length):
    """Seat an XY strut (X=span, Y=50 mm, Z=thickness) into a YZ notch."""
    solid = extrude_xy(face, thickness)
    a = unit(along)
    n = unit(inward)
    mid = notch_length / 2.0
    m = App.Matrix()
    m.A11 = 1.0
    m.A22 = a.x
    m.A32 = a.y
    m.A23 = n.x
    m.A33 = n.y
    m.A24 = origin.x + a.x * mid
    m.A34 = origin.y + a.y * mid
    return solid.transformGeometry(m)


def rotate_yz(y, z, pivot_y, pivot_z, degrees):
    rad = math.radians(degrees)
    c = math.cos(rad)
    s = math.sin(rad)
    dy = y - pivot_y
    dz = z - pivot_z
    return pivot_y + c * dy - s * dz, pivot_z + s * dy + c * dz


def export_dxf_objects(objects, path):
    try:
        import importDXF
        importDXF.export(objects, path)
        return True
    except Exception as exc:
        App.Console.PrintWarning("DXF export failed for %s: %s\n" % (path, exc))
        return False


def export_dxf_face(doc, face, path):
    tmp = doc.addObject("Part::Feature", "DXF_Temp")
    tmp.Shape = face
    ok = export_dxf_objects([tmp], path)
    doc.removeObject(tmp.Name)
    return ok


def derived(cfg):
    s = cfg["table_length_mm"] / cfg["ref_length_mm"]
    top = cfg["top_thickness_mm"]
    plywood = cfg["plywood_thickness_mm"]
    gap = cfg["side_gap_mm"]
    play = cfg["joinery_play_mm"]
    pivot_z = top / 2.0
    pivot_y = cfg["ref_pivot_y"] * s
    half_w = cfg["table_width_mm"] / 2.0
    side_inner = half_w + gap
    side_outer = side_inner + plywood

    def sy(y_ref):
        return y_ref * s

    def sz(z_ref):
        return pivot_z + s * (z_ref - cfg["ref_pivot_z"])

    floor_z = sz(cfg["ref_floor_z"])
    front_y = sy(cfg["ref_front_y"])
    back_y = sy(cfg["ref_back_y"])
    front_top_z = floor_z + cfg["front_height_mm"]
    hinge2_y = sy(cfg["ref_hinge2_y"])
    inner_y = sy(cfg["ref_inner_y"])
    shelf_z = sz(cfg["ref_shelf_z"])
    # One sheet of skirt below the bin floor, then a floor panel one sheet thick.
    base_bottom_z = floor_z + plywood
    base_top_z = base_bottom_z + plywood
    tab_z1 = front_top_z - (cfg["tab_from_top_mm"] + play)
    tab_z0 = tab_z1 - (cfg["tab_length_mm"] + 2.0 * play)
    strut_z_c = sz(cfg["ref_strut_z_center"])
    return {
        "s": s,
        "top": top,
        "plywood": plywood,
        "gap": gap,
        "play": play,
        "pivot_y": pivot_y,
        "pivot_z": pivot_z,
        "half_w": half_w,
        "side_inner": side_inner,
        "side_outer": side_outer,
        "half_len": cfg["table_length_mm"] / 2.0,
        "sy": sy,
        "sz": sz,
        "floor_z": floor_z,
        "front_y": front_y,
        "back_y": back_y,
        "front_top_z": front_top_z,
        "hinge2_y": hinge2_y,
        "inner_y": inner_y,
        "shelf_z": shelf_z,
        "base_bottom_z": base_bottom_z,
        "base_top_z": base_top_z,
        "slot_z0": base_bottom_z - play,
        "slot_z1": base_top_z + play,
        "tab_z0": tab_z0,
        "tab_z1": tab_z1,
        "strut_z_c": strut_z_c,
        "cross_len": 2.0 * side_outer,
        "base_x": side_inner - cfg["panel_clearance_mm"],
        "slot_w": cfg["base_tab_width_mm"] + 2.0 * play,
        "slot_d": plywood + 2.0 * play,
        "notch_l": cfg["tab_length_mm"] + 2.0 * play,
        "notch_d": plywood + play,
        "screw_inset": plywood / 2.0,
        "boss_r": cfg["hinge_boss_radius_mm"],
        "hinge_d": cfg["hinge_hole_mm"],
        "screw_d": cfg["screw_hole_mm"],
    }


def side_face(cfg, g):
    sy, sz = g["sy"], g["sz"]
    boss = g["boss_r"]
    pivot = (g["pivot_y"], g["pivot_z"])
    bump_y = sy(cfg["ref_bump_y"])
    bump = (bump_y, g["pivot_z"])
    fillet_a = cfg["ref_diag_fillet_angle"]
    diag_y = bump_y + boss * math.cos(fillet_a)
    diag_z = g["pivot_z"] + boss * math.sin(fillet_a)
    hinge_end_a = cfg["ref_hinge_arc_end"]
    hinge_end = (
        g["pivot_y"] + boss * math.cos(hinge_end_a),
        g["pivot_z"] + boss * math.sin(hinge_end_a),
    )
    slope_y = sy(cfg["ref_slope_y"])
    slope_z = sz(cfg["ref_slope_z"])
    inner_top_z = sz(cfg["ref_inner_top_z"])
    edges = [
        arc_edge(pivot[0], pivot[1], boss, math.pi / 2.0, hinge_end_a),
        line_edge(v(pivot[0], pivot[1] + boss), v(bump_y, g["pivot_z"] + boss)),
        arc_edge(bump[0], bump[1], boss, fillet_a, math.pi / 2.0),
        line_edge(v(diag_y, diag_z), v(g["front_y"], g["front_top_z"])),
        line_edge(v(g["front_y"], g["front_top_z"]), v(g["front_y"], g["floor_z"])),
        line_edge(v(g["front_y"], g["floor_z"]), v(g["back_y"], g["floor_z"])),
        line_edge(v(g["back_y"], g["floor_z"]), v(g["back_y"], g["front_top_z"])),
        line_edge(v(g["back_y"], g["front_top_z"]), v(slope_y, slope_z)),
        line_edge(v(slope_y, slope_z), v(g["inner_y"], g["shelf_z"])),
        line_edge(v(g["inner_y"], g["shelf_z"]), v(g["inner_y"], inner_top_z)),
        line_edge(v(g["inner_y"], inner_top_z), v(hinge_end[0], hinge_end[1])),
    ]
    face = face_from_edges(edges)

    along_front = v(0, -1)
    inward_front = v(-1, 0)
    face = face.cut(notch_face(
        v(g["front_y"], g["tab_z1"]), along_front, inward_front, g["notch_l"], g["notch_d"]
    ))
    face = face.cut(notch_face(
        v(g["back_y"], g["tab_z1"]), along_front, v(1, 0), g["notch_l"], g["notch_d"]
    ))

    strut_z1 = g["strut_z_c"] + cfg["strut_height_mm"] / 2.0 + g["play"]
    face = face.cut(notch_face(
        v(g["inner_y"], strut_z1),
        v(0, -1),
        v(1, 0),
        g["notch_l"],
        g["notch_d"],
    ))
    face = face.cut(notch_face(
        v(g["inner_y"], g["shelf_z"]),
        v(-1, 0),
        v(0, -1),
        g["notch_l"],
        g["notch_d"],
    ))

    notch_origin, diag_u, inward, _, _ = diagonal_notch(cfg, g)
    face = face.cut(notch_face(notch_origin, diag_u, inward, g["notch_l"], g["notch_d"]))

    slot_centers_y = [sy(y) for y in cfg["ref_base_slot_centers_y"]]
    for cy in slot_centers_y:
        face = face.cut(rect_face(
            cy - g["slot_w"] / 2.0,
            g["slot_z0"],
            cy + g["slot_w"] / 2.0,
            g["slot_z1"],
        ))

    holes = [(g["pivot_y"], g["pivot_z"], g["hinge_d"])]
    base_hole_z = 0.5 * (g["base_bottom_z"] + g["base_top_z"])
    for y_ref, z_ref in cfg["ref_side_holes"]:
        holes.append((sy(y_ref), base_hole_z, g["screw_d"]))
    # Keep the front/back tab screws on the restored 134.4 mm wall.
    holes.append((sy(cfg["ref_front_tab_hole_y"]), (g["tab_z0"] + g["tab_z1"]) / 2.0, g["screw_d"]))
    holes.append((sy(cfg["ref_back_tab_hole_y"]), (g["tab_z0"] + g["tab_z1"]) / 2.0, g["screw_d"]))
    return cut_circles(face, holes)


def front_face(cfg, g):
    x_in = g["side_inner"]
    x_out = g["side_outer"]
    z0 = g["floor_z"]
    z1 = g["front_top_z"]
    tz0, tz1 = g["tab_z0"], g["tab_z1"]
    pts = [
        v(x_in, z1),
        v(-x_in, z1),
        v(-x_in, tz1),
        v(-x_out, tz1),
        v(-x_out, tz0),
        v(-x_in, tz0),
        v(-x_in, z0),
        v(x_in, z0),
        v(x_in, tz0),
        v(x_out, tz0),
        v(x_out, tz1),
        v(x_in, tz1),
    ]
    face = polygon_face(pts)
    slot_centers = [0.0, -cfg["ref_front_slot_offset"], cfg["ref_front_slot_offset"]]
    rects = []
    for cx in slot_centers:
        rects.append((
            cx - g["slot_w"] / 2.0,
            g["slot_z0"],
            cx + g["slot_w"] / 2.0,
            g["slot_z1"],
        ))
    face = cut_rects(face, rects)
    slot_hole_z = 0.5 * (g["base_bottom_z"] + g["base_top_z"])
    inset = g["screw_inset"]
    holes = [
        (-x_out + inset, (tz0 + tz1) / 2.0, g["screw_d"]),
        (x_out - inset, (tz0 + tz1) / 2.0, g["screw_d"]),
        (-cfg["ref_front_slot_offset"] - 50.0 * g["s"], slot_hole_z, g["screw_d"]),
        (-cfg["ref_front_inner_hole_x"] * g["s"], slot_hole_z, g["screw_d"]),
        (cfg["ref_front_inner_hole_x"] * g["s"], slot_hole_z, g["screw_d"]),
        (cfg["ref_front_slot_offset"] + 50.0 * g["s"], slot_hole_z, g["screw_d"]),
    ]
    return cut_circles(face, holes)


def base_face(cfg, g):
    x = g["base_x"]
    y_front = g["front_y"] - g["plywood"] - cfg["panel_clearance_mm"]
    y_back = g["back_y"] + g["plywood"] + cfg["panel_clearance_mm"]
    tab = cfg["base_tab_width_mm"]
    depth = g["plywood"]
    # Panel rectangle, then in-plane tabs.
    face = rect_face(-x, y_back, x, y_front)
    y_centers = [g["sy"](c) for c in cfg["ref_base_slot_centers_y"]]
    x_centers = [0.0, -cfg["ref_front_slot_offset"], cfg["ref_front_slot_offset"]]
    for cy in y_centers:
        face = face.fuse(rect_face(-g["side_outer"], cy - tab / 2.0, g["side_outer"], cy + tab / 2.0))
    for cx in x_centers:
        face = face.fuse(rect_face(cx - tab / 2.0, y_front, cx + tab / 2.0, y_front + depth))
        face = face.fuse(rect_face(cx - tab / 2.0, y_back - depth, cx + tab / 2.0, y_back))
    return face.removeSplitter()


def strut_face(cfg, g):
    half = g["cross_len"] / 2.0
    h = cfg["strut_height_mm"]
    face = rect_face(-half, -h / 2.0, half, h / 2.0)
    inset_x = g["screw_inset"]
    inset_z = 12.0
    holes = [
        (-half + inset_x, h / 2.0 - inset_z, g["screw_d"]),
        (-half + inset_x, -h / 2.0 + inset_z, g["screw_d"]),
        (half - inset_x, h / 2.0 - inset_z, g["screw_d"]),
        (half - inset_x, -h / 2.0 + inset_z, g["screw_d"]),
    ]
    return cut_circles(face, holes)


def table_top_face(cfg, g):
    return rect_face(-g["half_w"], -g["half_len"], g["half_w"], g["half_len"])


def table_edge_face(cfg, g):
    """Side-view of the 70 mm top with hinge holes, for reviewing drill stations."""
    face = rect_face(-g["half_len"], 0.0, g["half_len"], g["top"])
    holes = [
        (g["pivot_y"], g["pivot_z"], g["hinge_d"]),
        (g["hinge2_y"], g["pivot_z"], g["hinge_d"]),
    ]
    return cut_circles(face, holes)


def caster_face_simple(cfg):
    half = cfg["caster_plate_mm"] / 2.0
    r = cfg["caster_fillet_mm"]
    pts = []
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    # Build a rounded rectangle with four quarter arcs.
    edges = []
    angs = [math.pi, 1.5 * math.pi, 0.0, 0.5 * math.pi]
    centers = [
        (-half + r, -half + r),
        (half - r, -half + r),
        (half - r, half - r),
        (-half + r, half - r),
    ]
    for i in range(4):
        c0 = centers[i]
        c1 = centers[(i + 1) % 4]
        a0 = angs[i]
        a1 = angs[i] + 0.5 * math.pi
        edges.append(arc_edge(c0[0], c0[1], r, a0, a1))
        p_end = v(c0[0] + r * math.cos(a1), c0[1] + r * math.sin(a1))
        p_next = v(c1[0] + r * math.cos(angs[(i + 1) % 4]), c1[1] + r * math.sin(angs[(i + 1) % 4]))
        if p_end.distanceToPoint(p_next) > 1e-4:
            edges.append(line_edge(p_end, p_next))
    face = face_from_edges(edges)
    holes = []
    s = cfg["caster_screw_spacing_mm"] / 2.0
    for x in (-s, s):
        for y in (-s, s):
            holes.append((x, y, cfg["caster_corner_hole_mm"]))
    holes.append((-cfg["caster_axle_hole_x"], 0.0, cfg["caster_axle_hole_mm"]))
    holes.append((cfg["caster_axle_hole_x"], 0.0, cfg["caster_axle_hole_mm"]))
    return cut_circles(face, holes)


def leg_face(cfg, g):
    sy, sz = g["sy"], g["sz"]
    hinge = (sy(cfg["ref_hinge2_y"]), g["pivot_z"])
    boss = g["boss_r"]
    fr = cfg["leg_fillet_mm"]
    c_inner = (sy(cfg["ref_leg_inner_cx"]), sz(cfg["ref_leg_inner_cz"]))
    c_front_top = (sy(cfg["ref_leg_front_top_cx"]), sz(cfg["ref_leg_front_top_cz"]))
    c_front_bot = (sy(cfg["ref_leg_front_bot_cx"]), sz(cfg["ref_leg_front_bot_cz"]))
    c_back_bot = (sy(cfg["ref_leg_back_bot_cx"]), sz(cfg["ref_leg_back_bot_cz"]))
    a0, a1 = cfg["ref_leg_arc0_start"], cfg["ref_leg_arc0_end"]
    edges = [
        arc_edge(hinge[0], hinge[1], boss, a0, a1),
    ]
    add_line(edges, p_on_arc(hinge[0], hinge[1], boss, a1), p_on_arc(c_inner[0], c_inner[1], fr, cfg["ref_leg_inner_a1"]))
    edges.append(arc_edge(c_inner[0], c_inner[1], fr, cfg["ref_leg_inner_a1"], cfg["ref_leg_inner_a0"]))
    add_line(edges, p_on_arc(c_inner[0], c_inner[1], fr, cfg["ref_leg_inner_a0"]),
             p_on_arc(c_front_top[0], c_front_top[1], fr, cfg["ref_leg_front_top_a0"]))
    edges.append(arc_edge(c_front_top[0], c_front_top[1], fr, cfg["ref_leg_front_top_a0"], cfg["ref_leg_front_top_a1"]))
    add_line(edges, p_on_arc(c_front_top[0], c_front_top[1], fr, cfg["ref_leg_front_top_a1"]),
             p_on_arc(c_front_bot[0], c_front_bot[1], fr, cfg["ref_leg_front_bot_a0"]))
    edges.append(arc_edge(c_front_bot[0], c_front_bot[1], fr, cfg["ref_leg_front_bot_a0"], cfg["ref_leg_front_bot_a1"]))
    bot_z = c_front_bot[1] + fr * math.sin(cfg["ref_leg_front_bot_a1"])
    add_line(edges, p_on_arc(c_front_bot[0], c_front_bot[1], fr, cfg["ref_leg_front_bot_a1"]),
             p_on_arc(c_back_bot[0], c_back_bot[1], fr, cfg["ref_leg_back_bot_a0"]))
    edges.append(arc_edge(c_back_bot[0], c_back_bot[1], fr, cfg["ref_leg_back_bot_a0"], cfg["ref_leg_back_bot_a1"]))
    add_line(edges, p_on_arc(c_back_bot[0], c_back_bot[1], fr, cfg["ref_leg_back_bot_a1"]),
             p_on_arc(hinge[0], hinge[1], boss, a0))
    face = face_from_edges(edges)
    face = cut_circles(face, [(hinge[0], hinge[1], g["hinge_d"])])
    for y0_ref, y1_ref in cfg["ref_leg_notches_y"]:
        mid = 0.5 * (sy(y0_ref) + sy(y1_ref))
        half = g["notch_l"] / 2.0
        face = face.cut(rect_face(mid - half, bot_z, mid + half, bot_z + g["notch_d"]))
    return face


def extrude_xy(face, thickness):
    return face.extrude(v(0, 0, thickness))


def map_yz_to_3d(face_yz, x0, thickness):
    """YZ profile stored as XY (x=Y, y=Z), extruded along world X from x0."""
    solid = extrude_xy(face_yz, thickness)
    m = App.Matrix()
    m.A11 = 0.0
    m.A12 = 0.0
    m.A13 = 1.0
    m.A14 = x0
    m.A21 = 1.0
    m.A22 = 0.0
    m.A23 = 0.0
    m.A24 = 0.0
    m.A31 = 0.0
    m.A32 = 1.0
    m.A33 = 0.0
    m.A34 = 0.0
    return solid.transformGeometry(m)


def map_xz_to_3d(face_xz, y0, thickness):
    """XZ profile stored as XY (x=X, y=Z), extruded along world Y from y0."""
    solid = extrude_xy(face_xz, thickness)
    m = App.Matrix()
    m.A11 = 1.0
    m.A12 = 0.0
    m.A13 = 0.0
    m.A14 = 0.0
    m.A21 = 0.0
    m.A22 = 0.0
    m.A23 = 1.0
    m.A24 = y0
    m.A31 = 0.0
    m.A32 = 1.0
    m.A33 = 0.0
    m.A34 = 0.0
    return solid.transformGeometry(m)


def make_profiles(cfg):
    g = derived(cfg)
    profiles = {
        "table_top": table_top_face(cfg, g),
        "table_edge": table_edge_face(cfg, g),
        "side_plate": side_face(cfg, g),
        "front_back": front_face(cfg, g),
        "base": base_face(cfg, g),
        "strut": strut_face(cfg, g),
        "leg": leg_face(cfg, g),
        "caster": caster_face_simple(cfg),
    }
    return profiles, g


def measure(cfg):
    profiles, g = make_profiles(cfg)
    side = profiles["side_plate"]
    # Diagonal angle from the 30 mm bump fillet to the restored front top.
    bump_y = g["sy"](cfg["ref_bump_y"])
    boss = g["boss_r"]
    fillet_a = cfg["ref_diag_fillet_angle"]
    dy = g["front_y"] - (bump_y + boss * math.cos(fillet_a))
    dz = g["front_top_z"] - (g["pivot_z"] + boss * math.sin(fillet_a))
    angle = math.degrees(math.atan2(-dz, dy))
    folded_min_z = None
    # Short end of the top after +90 deg fold about the pivot X-axis.
    y_short = -g["half_len"]
    z_short = 0.0
    _, z_fold = rotate_yz(y_short, z_short, g["pivot_y"], g["pivot_z"], 90.0)
    folded_min_z = z_fold
    return {
        "scale": g["s"],
        "table": (cfg["table_length_mm"], cfg["table_width_mm"], g["top"]),
        "plywood": g["plywood"],
        "slot_d": g["slot_d"],
        "notch_d": g["notch_d"],
        "hinge_spacing": g["hinge2_y"] - g["pivot_y"],
        "front_height": g["front_top_z"] - g["floor_z"],
        "side_bbox": (side.BoundBox.XLength, side.BoundBox.YLength),
        "cross_len": g["cross_len"],
        "strut_height": cfg["strut_height_mm"],
        "hinge_hole": g["hinge_d"],
        "screw_hole": g["screw_d"],
        "diag_angle_deg": angle,
        "floor_z": g["floor_z"],
        "folded_short_z": folded_min_z,
        "fold_clears_floor": folded_min_z > g["floor_z"] + 1.0,
        "front_width": profiles["front_back"].BoundBox.XLength,
        "base_bbox": (profiles["base"].BoundBox.XLength, profiles["base"].BoundBox.YLength),
    }


def add_params_object(doc, cfg, g):
    params = doc.addObject("App::FeaturePython", "TableParameters")
    params.Label = "Folding table parameters"
    params.addProperty("App::PropertyLength", "TableLength", "Setup")
    params.TableLength = cfg["table_length_mm"]
    params.addProperty("App::PropertyLength", "TableWidth", "Setup")
    params.TableWidth = cfg["table_width_mm"]
    params.addProperty("App::PropertyLength", "PlywoodThickness", "Setup")
    params.PlywoodThickness = cfg["plywood_thickness_mm"]
    params.addProperty("App::PropertyLength", "TopThickness", "Setup")
    params.TopThickness = cfg["top_thickness_mm"]
    params.addProperty("App::PropertyFloat", "LengthScale", "Setup")
    params.LengthScale = g["s"]
    params.addProperty("App::PropertyString", "Note", "Setup")
    params.Note = "Edit folding_table.py CONFIG and rebuild; this object is a snapshot."
    return params


def write_cut_list(path, cfg, g, dxf_ok):
    lines = [
        "FOLDING CNC TABLE — CUT LIST",
        "",
        "Table top: %.0f x %.0f mm, thickness %.1f mm" % (
            cfg["table_width_mm"], cfg["table_length_mm"], cfg["top_thickness_mm"]
        ),
        "Plywood: %.1f mm" % cfg["plywood_thickness_mm"],
        "Length scale vs 1830 mm source: %.4f" % g["s"],
        "",
        "QTY  FILE",
        "1    table_top.dxf          spoilboard rectangle",
        "1    table_edge.dxf         edge view with hinge holes (drill reference)",
        "2    side_plate.dxf         left/right; flip one face-down if grain allows",
        "2    front_back.dxf         identical front and back",
        "1    base.dxf               bin floor with box-joint tabs",
        "5    strut.dxf              50 mm stretchers: 3 in the cart, 2 between the folding legs",
        "2    leg.dxf                folding legs at the second hinge",
        "4    caster.dxf             85 mm plates",
        "",
        "Hardware (from the source model):",
        "  20 mm hinge pins at the two stations on each side",
        "  4 mm screws at box joints and struts",
        "  3 mm screws in caster corners, 4 mm axle holes",
        "  four swivel casters",
        "",
        "DXF export: " + (", ".join("%s=%s" % (k, "ok" if v else "FAIL") for k, v in dxf_ok.items())),
        "",
        "Rebuild: set table_length_mm / table_width_mm / plywood_thickness_mm at the",
        "bottom of folding_table.py and run the script in FreeCAD.",
        "Plywood thickness is independent of length/width; it only changes sheet",
        "extrusion, box-joint depth, and the span of front/back/base/strut parts.",
    ]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def layout_sheet_faces(profiles, gap):
    """Place unique profiles in a row in XY, returning transformed faces and labels."""
    order = [
        ("table_top", "table_top qty 1"),
        ("side_plate", "side_plate qty 2"),
        ("front_back", "front_back qty 2"),
        ("base", "base qty 1"),
        ("strut", "strut qty 5"),
        ("leg", "leg qty 2"),
        ("caster", "caster qty 4"),
        ("table_edge", "table_edge qty 1"),
    ]
    x = 0.0
    placed = []
    labels = []
    for key, label in order:
        face = profiles[key].copy()
        box = face.BoundBox
        face.translate(v(x - box.XMin, -box.YMin, 0))
        placed.append((key, face, label))
        labels.append((label, x, box.YLength + 30.0))
        x += box.XLength + gap
    return placed, labels


def build_table(cfg):
    profiles, g = make_profiles(cfg)
    doc_name = cfg["document_name"]
    old = App.listDocuments().get(doc_name)
    if old is not None:
        App.closeDocument(doc_name)
    doc = App.newDocument(doc_name)

    assembly = doc.addObject("App::DocumentObjectGroup", "Assembly")
    assembly.Label = "Open position"
    cnc_group = doc.addObject("App::DocumentObjectGroup", "CNCProfiles")
    cnc_group.Label = "CNC profiles"
    folded_group = doc.addObject("App::DocumentObjectGroup", "FoldedReference")
    folded_group.Label = "Folded top (reference)"

    t = g["plywood"]
    top = g["top"]

    top_solid = extrude_xy(profiles["table_top"], top)
    # Hinge holes through the top in X, at both stations, centered in thickness.
    for y in (g["pivot_y"], g["hinge2_y"]):
        hole = Part.makeCylinder(
            g["hinge_d"] / 2.0,
            cfg["table_width_mm"] + 40.0,
            v(-g["half_w"] - 20.0, y, g["pivot_z"]),
            v(1, 0, 0),
        )
        top_solid = top_solid.cut(hole)
    add_part(doc, assembly, "TableTop", top_solid, WOOD_TOP, 10)

    folded = top_solid.copy()
    folded.rotate(v(0, g["pivot_y"], g["pivot_z"]), v(1, 0, 0), 90)
    folded_obj = add_part(doc, folded_group, "TableTopFolded", folded, GHOST, 70)
    if folded_obj.ViewObject:
        folded_obj.ViewObject.Visibility = False

    add_part(
        doc, assembly, "SideRight",
        map_yz_to_3d(profiles["side_plate"], g["side_inner"], t),
        WOOD_BLACK,
    )
    left = map_yz_to_3d(profiles["side_plate"], -g["side_outer"], t)
    add_part(doc, assembly, "SideLeft", left, WOOD_BLACK)

    add_part(
        doc, assembly, "Front",
        map_xz_to_3d(profiles["front_back"], g["front_y"] - t, t),
        WOOD_BLACK,
    )
    add_part(
        doc, assembly, "Back",
        map_xz_to_3d(profiles["front_back"], g["back_y"], t),
        WOOD_BLACK,
    )

    base_solid = extrude_xy(profiles["base"], t)
    base_solid.translate(v(0, 0, g["base_bottom_z"] - base_solid.BoundBox.ZMin))
    add_part(doc, assembly, "Base", base_solid, WOOD_BLACK)

    for name, origin, along, inward in strut_notches(cfg, g):
        add_part(
            doc, assembly, name,
            place_strut(profiles["strut"], t, origin, along, inward, g["notch_l"]),
            WOOD_STRUT,
        )

    add_part(
        doc, assembly, "LegRight",
        map_yz_to_3d(profiles["leg"], g["side_inner"], t),
        WOOD_LEG,
    )
    add_part(
        doc, assembly, "LegLeft",
        map_yz_to_3d(profiles["leg"], -g["side_outer"], t),
        WOOD_LEG,
    )

    caster = extrude_xy(profiles["caster"], t)
    inset = cfg["caster_plate_mm"] / 2.0 + 12.0
    corners = [
        (g["base_x"] - inset, g["front_y"] - g["plywood"] - inset),
        (-(g["base_x"] - inset), g["front_y"] - g["plywood"] - inset),
        (g["base_x"] - inset, g["back_y"] + g["plywood"] + inset),
        (-(g["base_x"] - inset), g["back_y"] + g["plywood"] + inset),
    ]
    for i, (cx, cy) in enumerate(corners, 1):
        plate = caster.copy()
        plate.translate(v(cx, cy, g["floor_z"] - t))
        add_part(doc, assembly, "Caster%d" % i, plate, WOOD_CASTER)

    for name, face in profiles.items():
        obj = add_part(
            doc, cnc_group, "CNC_" + name, extrude_xy(face, t), CNC, 0
        )
        if obj.ViewObject:
            obj.ViewObject.Visibility = False

    add_params_object(doc, cfg, g)
    doc.recompute()

    out_dir = cfg["output_directory"]
    os.makedirs(out_dir, exist_ok=True)
    dxf_dir = os.path.join(out_dir, "dxf")
    os.makedirs(dxf_dir, exist_ok=True)

    dxf_ok = {}
    for name, face in profiles.items():
        dxf_ok[name] = export_dxf_face(doc, face, os.path.join(dxf_dir, name + ".dxf"))

    placed, labels = layout_sheet_faces(profiles, cfg["sheet_gap_mm"])
    sheet_objs = []
    for key, face, label in placed:
        obj = doc.addObject("Part::Feature", "Sheet_" + key)
        obj.Label = label
        obj.Shape = face
        if obj.ViewObject:
            obj.ViewObject.Visibility = False
        cnc_group.addObject(obj)
        sheet_objs.append(obj)
    dxf_ok["sheet"] = export_dxf_objects(sheet_objs, os.path.join(dxf_dir, "folding_table_sheet.dxf"))

    write_cut_list(os.path.join(out_dir, "CUT_LIST.txt"), cfg, g, dxf_ok)

    fcstd_path = os.path.join(out_dir, cfg["document_name"] + ".FCStd")
    doc.saveAs(fcstd_path)

    stats = measure(cfg)
    print("Folding table")
    print("  table LxW: %.1f x %.1f mm, scale %.4f" % (cfg["table_length_mm"], cfg["table_width_mm"], g["s"]))
    print("  plywood: %.1f mm (independent of length/width), top: %.1f mm" % (g["plywood"], g["top"]))
    print("  joinery: notch depth %.2f mm, base slot %.2f mm, cross-member %.2f mm" % (
        g["notch_d"], g["slot_d"], g["cross_len"]
    ))
    print("  hinge spacing: %.2f mm" % stats["hinge_spacing"])
    print("  front height: %.2f mm" % stats["front_height"])
    print("  side bbox (Y x Z mapped to XY): %.2f x %.2f mm" % stats["side_bbox"])
    print("  diagonal angle: %.3f deg" % stats["diag_angle_deg"])
    print("  cross-member length: %.2f mm" % stats["cross_len"])
    print("  floor Z: %.2f mm, folded short-end Z: %.2f mm, clears: %s" % (
        stats["floor_z"], stats["folded_short_z"], stats["fold_clears_floor"]
    ))
    print("  DXF:", dxf_ok)
    print("  saved:", fcstd_path)
    alt = dict(cfg)
    alt["table_length_mm"] = 1500.0
    alt["table_width_mm"] = 1000.0
    alt_stats = measure(alt)
    print("  check 1500x1000: scale %.4f, hinge %.2f, front_h %.2f, plywood %.1f, hole %.1f, angle %.3f, cross %.1f, fold_clears %s" % (
        alt_stats["scale"], alt_stats["hinge_spacing"], alt_stats["front_height"],
        alt_stats["plywood"], alt_stats["hinge_hole"], alt_stats["diag_angle_deg"],
        alt_stats["cross_len"], alt_stats["fold_clears_floor"],
    ))
    ply = dict(cfg)
    ply["plywood_thickness_mm"] = cfg["plywood_thickness_mm"] + 1.0
    ply_stats = measure(ply)
    print("  check plywood %.1f mm: extrusion %.1f, notch_d %.2f, slot_d %.2f, cross %.1f, front_h %.2f, hinge %.2f" % (
        ply["plywood_thickness_mm"], ply_stats["plywood"], ply_stats["notch_d"],
        ply_stats["slot_d"], ply_stats["cross_len"], ply_stats["front_height"],
        ply_stats["hinge_spacing"],
    ))

    try:
        import FreeCADGui as Gui
        Gui.SendMsgToActiveView("ViewFit")
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
    except Exception:
        pass
    doc.recompute()
    doc.save()
    return doc, stats, dxf_ok


# ---------------------------------------------------------------------------
# USER-EDITABLE PARAMETERS (millimetres)
# Length and width scale the folding linkage. Plywood thickness does not:
# it only changes sheet extrusion, box-joint depth, and cross-member span.
# ---------------------------------------------------------------------------
CONFIG = {
    "document_name": "FoldingTable",
    "output_directory": "/Users/localuser/freecadmcp_stuff/cnc_table",
    "table_length_mm": 1830.0,
    "table_width_mm": 1220.0,
    "plywood_thickness_mm": 17.0,
    "top_thickness_mm": 70.0,
    "side_gap_mm": 2.0,
    "joinery_play_mm": 0.2,
    "panel_clearance_mm": 0.2,
    "front_height_mm": 134.4,
    "strut_height_mm": 50.0,
    "tab_length_mm": 50.0,
    "tab_from_top_mm": 25.0,
    "base_tab_width_mm": 125.0,
    "hinge_hole_mm": 20.0,
    "hinge_boss_radius_mm": 30.0,
    "screw_hole_mm": 4.0,
    "leg_fillet_mm": 15.0,
    "caster_plate_mm": 85.0,
    "caster_fillet_mm": 5.0,
    "caster_screw_spacing_mm": 51.0,
    "caster_corner_hole_mm": 3.0,
    "caster_axle_hole_mm": 4.0,
    "caster_axle_hole_x": 20.0,
    "sheet_gap_mm": 80.0,
    # Source-model anchors (do not edit unless matching a new reference FCStd)
    "ref_length_mm": 1830.0,
    "ref_width_mm": 1220.0,
    "ref_pivot_y": -435.0,
    "ref_pivot_z": 35.0,
    "ref_hinge2_y": 775.0,
    "ref_floor_z": -707.0,
    "ref_front_y": 4.8,
    "ref_back_y": -739.0,
    "ref_inner_y": -395.2,
    "ref_shelf_z": -451.8084506302682,
    "ref_slope_y": -495.0,
    "ref_slope_z": -451.8084506302682,
    "ref_inner_top_z": -134.0,
    "ref_bump_y": -377.0813988351924,
    "ref_diag_fillet_angle": 0.5193021597862101,
    "ref_hinge_arc_end": 3.5465406388434255,
    "ref_strut_z_center": -443.6084506302681,
    "ref_base_slot_centers_y": [-609.1, -367.1, -125.1],
    "ref_front_slot_offset": 449.3,
    "ref_front_inner_hole_x": 224.65,
    "ref_side_holes": [
        (-705.4, -681.3),
        (-488.1, -681.3),
        (-246.1, -681.3),
        (-28.8, -681.3),
    ],
    "ref_front_tab_hole_y": -3.8,
    "ref_back_tab_hole_y": -730.4,
    "diag_notch_from_fillet_mm": 90.0,
    "ref_leg_top_z": -2.0,
    "ref_leg_bot_z": -70.93654271085353,
    "ref_leg_top_fillet_y": 622.6451421694504,
    "ref_leg_front_fillet_y": -42.25813309565524,
    "ref_leg_front_bot_cx": -49.12369611108645,
    "ref_leg_back_bot_cx": 774.1968331660154,
    "ref_leg_tip_angle": 1.3962634015954636,
    "ref_leg_arc0_start": 6.1086523819801535,
    "ref_leg_arc0_end": 8.2940535705035874,
    "ref_leg_inner_arc_start": 4.7123889803846888,
    "ref_leg_inner_cx": 622.6451421694504,
    "ref_leg_inner_cz": 13.0,
    "ref_leg_inner_a0": 4.7123889803846888,
    "ref_leg_inner_a1": 5.1524609169137943,
    "ref_leg_front_top_cx": -42.25813309565527,
    "ref_leg_front_top_cz": -17.0,
    "ref_leg_front_top_a0": 1.5707963267948968,
    "ref_leg_front_top_a1": 2.9670597283903604,
    "ref_leg_front_bot_cz": -55.93654271085354,
    "ref_leg_front_bot_a0": 2.9670597283903604,
    "ref_leg_front_bot_a1": 4.7123889803846897,
    "ref_leg_back_bot_cz": -55.93654271085354,
    "ref_leg_back_bot_a0": 4.7123889803846897,
    "ref_leg_back_bot_a1": 6.1086523819801526,
    "ref_leg_notches_y": [(50.87630388891355, 101.27630388891355), (665.5065501240496, 715.9065501240495)],
}


TABLE_DOCUMENT, TABLE_STATS, TABLE_DXF = build_table(CONFIG)
