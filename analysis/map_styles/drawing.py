"""Geometry-only renderer. Text and legends belong to the LaTeX fragments."""
from collections import defaultdict
import numpy as np
import shapely
from matplotlib.collections import PatchCollection, LineCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path
W, G = "#ffffff", "#535353"
EXT = 4096

def pathpatch(poly):
    vs, cs = [], []
    for ring in [poly.exterior, *poly.interiors]:
        c = np.asarray(ring.coords)[:, :2]
        vs.append(c); cs += [Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY]
    return PathPatch(Path(np.vstack(vs), cs))

def draw(ax, layers, cfg):
    """z-order is per feature: cfg["zfun"](layer, props) if given, else the layer's index in cfg["zorder"].
    hatch "line:w" = outline/line of width w; any other hatch is a fill pattern."""
    polys, lines, pts = defaultdict(list), defaultdict(list), defaultdict(list)
    zf = cfg.get("zfun") or (lambda layer, props: (cfg["zorder"].index(layer) if layer in cfg["zorder"] else 0))
    for name, feats in layers.items():
        for g, props in feats:
            fc, ec, hatch, off, _ = cfg["style"](name, props); z = zf(name, props)
            lw = float(hatch.split(":")[1]) if hatch and hatch.startswith("line:") else None
            ishatch = hatch and not hatch.startswith("line") and hatch != "pt"
            for p in shapely.get_parts(g):
                t = p.geom_type
                if t == "Polygon":
                    if fc is None and hatch and hatch.startswith("line"): lines[(z, ec, lw or 1.0)].append(np.asarray(p.exterior.coords)[:, :2])
                    else: polys[(z, off, fc or W, ec, hatch if ishatch else None)].append(pathpatch(p))
                elif t == "LineString": lines[(z, ec if ec != W else G, lw or cfg.get("line_w", .7))].append(np.asarray(p.coords)[:, :2])
                elif t == "Point": pts[(z, ec if ec != W else G)].append(p.coords[0][:2])
    for (z, off, fc, ec, hatch), ps in sorted(polys.items(), key=lambda kv: (kv[0][0], kv[0][1])):  # unofficial fallback first within a z
        ax.add_collection(PatchCollection(ps, fc=fc, ec=ec, lw=cfg.get("poly_lw", .3) if hatch is None else .1, hatch=hatch, zorder=z + 1))
    for (z, c, lw), ls in lines.items(): ax.add_collection(LineCollection(ls, colors=c, lw=lw, zorder=z + 1.5))
    for (z, c), a in pts.items():
        a = np.array(a); ax.scatter(a[:, 0], a[:, 1], s=cfg.get("pt_s", .5), c=c, lw=0, zorder=z + 1.6)
    ax.set_xlim(0, EXT); ax.set_ylim(EXT, 0)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    for s_ in ax.spines.values(): s_.set_color("#cccccc")
