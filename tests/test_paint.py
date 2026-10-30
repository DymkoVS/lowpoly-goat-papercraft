"""Проверки палитр, панелей и экспортированных материалов без новых зависимостей."""
import ast
import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh
from pxr import Usd, UsdGeom, UsdShade

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'goat'))
import paint


def glb_json(path):
    data = Path(path).read_bytes()
    length, kind = struct.unpack_from('<II', data, 12)
    assert kind == 0x4e4f534a
    return json.loads(data[20:20+length])


def geometry_colors(path):
    scene = trimesh.load(path, force='scene', process=False)
    return {mesh.visual.material.name: (np.asarray(mesh.vertices), np.asarray(mesh.faces),
                   np.asarray(mesh.visual.material.baseColorFactor))
            for mesh in scene.geometry.values()}


class PaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mesh = trimesh.load(ROOT / 'patterns/v2/goat.obj', process=False)
        cls.mesh.merge_vertices()
        cls.panel, cls.adj, cls.flat = paint.panels(cls.mesh)

    def test_palettes_match_html(self):
        html = (ROOT / 'goat/viewer.html').read_text()
        decola = ast.literal_eval(re.search(r'const DECOLA = (\[.*?\]);', html, re.S)[1])
        reds = ast.literal_eval(re.search(r'const REDS = (\[.*?\]);', html, re.S)[1])
        self.assertEqual(paint.DECOLA, [tuple(p) for p in decola])
        self.assertEqual(paint.REDS, reds)
        self.assertEqual(len(decola), 23)

    def test_flat_triangles_are_one_panel(self):
        self.assertTrue(self.flat)
        for (a, b), e in zip(self.mesh.face_adjacency, self.mesh.face_adjacency_edges):
            if tuple(sorted(e)) in self.flat:
                self.assertEqual(self.panel[a], self.panel[b])

    def test_balance_and_conflicts(self):
        for n in (1, 2, 3, 9, 21):
            assigned, conflicts = paint.color_panels(self.adj, n, 1)
            counts = np.bincount(assigned, minlength=n)
            self.assertLessEqual(int(np.ptp(counts)), 2)
            actual = sum(assigned[a] == assigned[b] for a in range(len(self.adj))
                         for b in self.adj[a] if a < b)
            self.assertEqual(conflicts, actual)
            if n in (9, 21):
                self.assertEqual(conflicts, 0)

    def test_exports_and_seed_loaded_from_glb(self):
        V, col, black, _, _, source = paint.bake(self.mesh, .125, self.flat)
        with tempfile.TemporaryDirectory() as tmp:
            snapshots = []
            for suffix in ('a', 'b'):
                assigned, _ = paint.color_panels(self.adj, 21, 1)
                pool = [(n, c) for n, c in paint.DECOLA if n not in ('Белила титановые', 'Серая')]
                rgb = [paint.tint(c, .1) for _, c in pool]
                face_colors = assigned[self.panel[source]]
                groups = [(f'paint_{i}', col[face_colors == i], c) for i, c in enumerate(rgb)]
                groups.append(('edges', black, paint.EDGE_BLACK))
                path = Path(tmp) / f'{suffix}.glb'
                paint.export_glb(str(path), V, groups)
                doc = glb_json(path)
                self.assertEqual(len(doc['materials']), 22)
                for mat in doc['materials']:
                    self.assertEqual(mat['pbrMetallicRoughness']['roughnessFactor'], 1)
                    self.assertEqual(mat['pbrMetallicRoughness']['metallicFactor'], 0)
                snapshots.append(geometry_colors(path))
            self.assertEqual(snapshots[0].keys(), snapshots[1].keys())
            for name in snapshots[0]:
                for a, b in zip(snapshots[0][name], snapshots[1][name]):
                    np.testing.assert_array_equal(a, b)
            # Каждая цветная запечённая грань имеет именно цвет исходной панели.
            for i, c in enumerate(rgb):
                loaded = snapshots[0][f'paint_{i}']
                np.testing.assert_array_equal(loaded[2][:3], np.round(c * 255).astype(int))
                self.assertEqual(len(loaded[1]), int(np.count_nonzero(face_colors == i)))
            usdpath = str(Path(tmp) / 'test.usdz')
            paint.export_usdz(usdpath, V, groups)
            stage = Usd.Stage.Open(usdpath)
            self.assertEqual(UsdGeom.GetStageUpAxis(stage), 'Y')
            self.assertEqual(UsdGeom.GetStageMetersPerUnit(stage), 1)
            materials = [p for p in stage.Traverse() if p.IsA(UsdShade.Material)]
            self.assertEqual(len(materials), 22)
            for prim in stage.Traverse():
                if prim.IsA(UsdShade.Shader):
                    shader = UsdShade.Shader(prim)
                    self.assertEqual(shader.GetIdAttr().Get(), 'UsdPreviewSurface')
                    self.assertEqual(shader.GetInput('roughness').Get(), 1)
                    self.assertEqual(shader.GetInput('metallic').Get(), 0)

    def test_custom_pool_and_color_scope(self):
        from argparse import Namespace
        args = Namespace(paints='Красная,Кармин,Красная', palette='decola', color='#000000')
        self.assertEqual(paint.paint_pool(args), [('Красная', '#b3342f'), ('Кармин', '#8a2934')])
        args.paints = 'Ошибочная'
        with self.assertRaisesRegex(ValueError, 'Допустимые:'):
            paint.paint_pool(args)
        args.paints = None
        self.assertEqual(len(paint.paint_pool(args)), 21)
        args.palette = 'reds'
        self.assertEqual([n for n, _ in paint.paint_pool(args)], paint.REDS)
        args.palette = 'single'
        self.assertEqual(paint.paint_pool(args), [('#000000', '#000000')])

    def test_default_red(self):
        rgb = paint.tint(paint.DECOLA_RED, .1)
        self.assertEqual('#' + ''.join(f'{round(x*255):02x}' for x in rgb), '#c94d46')
        V, col, black, _, _, _ = paint.bake(self.mesh, .125)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'single.glb'
            paint.export_glb(str(path), V, [('paint_0', col, rgb), ('edges', black, paint.EDGE_BLACK)])
            self.assertEqual(len(glb_json(path)['materials']), 2)


if __name__ == '__main__':
    unittest.main()
