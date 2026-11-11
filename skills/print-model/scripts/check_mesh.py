"""Check exported mesh structure, not physical fit or slicer readiness."""
import argparse
import json
from pathlib import Path
import sys
import trimesh


def check(path):
    scene = trimesh.load_scene(path)
    meshes = list(scene.geometry.values())
    bodies = []
    for mesh in meshes:
        bodies.append({
            'watertight': bool(mesh.is_watertight),
            'winding_consistent': bool(mesh.is_winding_consistent),
            'volume_positive': bool(mesh.volume > 0),
            'connected_components': len(mesh.split(only_watertight=False)),
        })
    passed = bool(bodies) and all(b['watertight'] and b['winding_consistent'] and b['volume_positive'] for b in bodies)
    return {'file': str(path), 'passed': passed, 'meshes': bodies, 'physical_fit': 'unverified', 'slice_checked': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('files', type=Path, nargs='+')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    results = []
    for path in args.files:
        try:
            results.append(check(path))
        except Exception as exc:
            results.append({'file': str(path), 'passed': False, 'error': str(exc)})
    report = {'passed': all(r['passed'] for r in results), 'results': results}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            stream.write(text + '\n')
    print(text)
    sys.exit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
