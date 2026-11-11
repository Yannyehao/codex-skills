"""Create a CAD project skeleton; does not install tools or write to Notion."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('slug')
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'config.local.json')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', args.slug):
        parser.error('Use a lowercase ASCII slug with hyphens.')
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    if not config.get('projects_root'):
        parser.error('Set projects_root in the local config first.')
    date = datetime.datetime.now(ZoneInfo(config.get('timezone', 'UTC'))).date().isoformat()
    root = Path(config['projects_root']).resolve()
    project = root / f'{date}_{args.slug}'
    project.mkdir(parents=True, exist_ok=False)
    files = {
        'PLAN.md': f'# {args.slug}\n\n## Goal\nRecord intended use and measurable requirements before modeling.\n\n## Architecture\nLocal AgentCAD/build123d, browser preview, print exports.\n\n## Phases\nInspect, specify, build, validate, trial fit, iterate.\n\n## Risks\nPhysical fit and slicer behavior remain unverified.\n',
        'README.md': f'# {args.slug}\n\nUse the shared CAD Python from print-model/config.local.json.\n\nRun `<cad_python> -m agentcad init --name {args.slug} --no-agent-setup`.\nKeep original models in source/, generated history in build/, reviewed deliverables in outputs/.\n',
        'DEVLOG.md': f'# DEVLOG\n\n## {date}\n- Created project skeleton. Next: inspect references and write SPEC.md.\n',
        'agentcad.toml': 'build_dir = "./build"\n',
        '.gitignore': 'build/\n.agentcad/\nwork/\n__pycache__/\n*.local.json\n',
    }
    for name, content in files.items():
        (project / name).write_text(content, encoding='utf-8')
    for name in ('source', 'outputs'):
        (project / name).mkdir()
    for command in (['git', 'init'], ['git', 'add', 'PLAN.md', 'README.md', 'DEVLOG.md', 'agentcad.toml', '.gitignore'], ['git', 'commit', '-m', 'Initialize CAD project skeleton']):
        subprocess.run(command, cwd=project, check=True, capture_output=True, text=True)
    print(json.dumps({'project': str(project), 'status': 'created'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
