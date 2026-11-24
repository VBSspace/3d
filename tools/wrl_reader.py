# -*- coding: utf-8 -*-
"""Чтение .wrl (VRML 2.0) из Базиса с сохранением иерархии.

Основано на wrl.py из «Шаблон КП bvsspace» (мм, Y вверх), но каждая
фигура помнит путь именованных узлов (имя + уникальный номер узла),
а для каждого узла запоминается мировая матрица — так можно получить
размеры детали в её собственных осях.
"""
import math
import re
import sys

import numpy as np

TOK = re.compile(r'"[^"]*"|[\[\]{}]|[^\s\[\]{},"]+')


def _tokens(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if '#' in line and '"' not in line:
                line = line.split('#', 1)[0]
            for m in TOK.finditer(line):
                yield m.group(0)


def _rotmat(ax, ay, az, a):
    n = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    x, y, z = ax / n, ay / n, az / n
    c, s = math.cos(a), math.sin(a)
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


class Scene:
    def __init__(self):
        self.shapes = []       # dict: path, pts(world, мм), ci, uv, ti, tex, color, transp
        self.nodes = {}        # uid -> dict(name, parent, M)
        self._uid = 0


class _Parser:
    def __init__(self, path, scene):
        self.g = _tokens(path)
        self.buf = []
        self.sc = scene

    def next(self):
        return self.buf.pop() if self.buf else next(self.g, None)

    def expect(self, tok):
        t = self.next()
        if t != tok:
            raise ValueError('ожидалось %r, получено %r' % (tok, t))

    def numbers(self):
        self.expect('[')
        out = []
        while True:
            t = self.next()
            if t == ']':
                return out
            out.append(t)

    def skip_open(self):
        """Пропустить блок, когда '{' или '[' уже прочитан."""
        depth = 1
        while depth:
            t = self.next()
            if t is None:
                return
            if t in ('{', '['):
                depth += 1
            elif t in ('}', ']'):
                depth -= 1

    # ---------------------------------------------------------------
    def any(self, t, M, path):
        if t == 'DEF':
            nm = self.next()
            ty = self.next()
            self.sc._uid += 1
            uid = self.sc._uid
            self.sc.nodes[uid] = {'name': nm, 'parent': path[-1][1] if path else None, 'M': M}
            self.node(ty, M, path + [(nm, uid)], uid)
        elif t == 'USE':
            self.next()
        else:
            self.node(t, M, path, None)

    def node(self, ty, M, path, uid):
        self.expect('{')
        if ty in ('Transform', 'Group'):
            trans = np.zeros(3)
            R = np.eye(3)
            while True:
                t = self.next()
                if t == '}' or t is None:
                    return
                if t == 'translation':
                    trans = np.array([float(self.next()) for _ in range(3)])
                elif t == 'rotation':
                    R = _rotmat(*[float(self.next()) for _ in range(4)])
                elif t in ('scale', 'center'):
                    [self.next() for _ in range(3)]
                elif t == 'scaleOrientation':
                    [self.next() for _ in range(4)]
                elif t == 'children':
                    L = np.eye(4)
                    L[:3, :3] = R
                    L[:3, 3] = trans
                    MM = M @ L
                    if uid is not None:
                        self.sc.nodes[uid]['M'] = MM
                    self.expect('[')
                    while True:
                        t2 = self.next()
                        if t2 == ']' or t2 is None:
                            break
                        self.any(t2, MM, path)
        elif ty == 'Shape':
            shp = {'path': path, 'tex': None, 'color': (1.0, 1.0, 1.0), 'transp': 0.0}
            while True:
                t = self.next()
                if t == '}' or t is None:
                    break
                if t == 'appearance':
                    self.appearance(shp)
                elif t == 'geometry':
                    gt = self.next()
                    if gt == 'DEF':
                        self.next()
                        gt = self.next()
                    if gt == 'IndexedFaceSet':
                        self.ifs(shp)
                    else:
                        self.expect('{')
                        self.skip_open()
            if 'pts' in shp and 'ci' in shp and len(shp['pts']):
                hp = np.c_[shp['pts'], np.ones(len(shp['pts']))]
                shp['pts'] = (hp @ M.T)[:, :3]
                self.sc.shapes.append(shp)
        else:
            self.skip_open()

    def appearance(self, shp):
        t = self.next()
        if t == 'DEF':
            self.next()
            t = self.next()
        self.expect('{')
        depth = 1
        while depth:
            t = self.next()
            if t is None:
                return
            if t == 'diffuseColor':
                shp['color'] = tuple(float(self.next()) for _ in range(3))
            elif t == 'transparency':
                shp['transp'] = float(self.next())
            elif t == 'url':
                shp['tex'] = self.next().strip('"').replace('\\', '/')
            elif t in ('{', '['):
                depth += 1
            elif t in ('}', ']'):
                depth -= 1

    def ifs(self, shp):
        self.expect('{')
        depth = 1
        while depth:
            t = self.next()
            if t is None:
                return
            if t == 'coord' or t == 'texCoord':
                ct = self.next()
                if ct == 'DEF':
                    self.next()
                    ct = self.next()
                self.expect('{')
                self.expect('point')
                nums = np.array(self.numbers(), dtype=float)
                self.expect('}')
                if t == 'coord':
                    shp['pts'] = nums.reshape(-1, 3)
                else:
                    shp['uv'] = nums.reshape(-1, 2)
            elif t == 'coordIndex':
                shp['ci'] = np.array(self.numbers(), dtype=np.int64)
            elif t == 'texCoordIndex':
                shp['ti'] = np.array(self.numbers(), dtype=np.int64)
            elif t in ('normal', 'color'):
                nt = self.next()
                if nt == 'DEF':
                    self.next()
                self.expect('{')
                self.skip_open()
            elif t in ('normalIndex', 'colorIndex'):
                self.numbers()
            elif t in ('{', '['):
                depth += 1
            elif t in ('}', ']'):
                depth -= 1


def read(path):
    sc = Scene()
    p = _Parser(path, sc)
    while True:
        t = p.next()
        if t is None:
            break
        if t == 'DEF' or t[0].isupper():
            p.any(t, np.eye(4), [])
    return sc


def triangulate(ci):
    """coordIndex (-1 разделители) -> массив треугольников (N,3) индексов углов в ci."""
    tris = []
    start = 0
    n = len(ci)
    for i in range(n + 1):
        if i == n or ci[i] < 0:
            k = i - start
            for j in range(1, k - 1):
                tris.append((start, start + j, start + j + 1))
            start = i + 1
    return np.array(tris, dtype=np.int64).reshape(-1, 3)


if __name__ == '__main__':
    import time
    t0 = time.time()
    sc = read(sys.argv[1])
    print('shapes', len(sc.shapes), 'nodes', len(sc.nodes), '%.1fs' % (time.time() - t0))
