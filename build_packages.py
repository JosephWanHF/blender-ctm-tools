"""Create installable Blender ZIPs without bundling user models."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT = Path(__file__).resolve().parent
DIST = ROOT / 'dist'
DIST.mkdir(exist_ok=True)
for name in ('openctm_ctm', 'ctm_part_mapper'):
    source = ROOT / 'addons' / name
    output = DIST / (name + '.zip')
    with ZipFile(output, 'w', ZIP_DEFLATED) as z:
        for path in sorted(source.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.blend'):
                archive = path.relative_to(source) if name == 'openctm_ctm' else path.relative_to(source.parent)
                z.write(path, archive.as_posix())
    print(output)
