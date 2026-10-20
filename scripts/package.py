"""Build a source archive without local photos, credentials, caches or environments."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root=Path(__file__).resolve().parents[1]
destination=root.parent/'pixel-avatar-portable.zip'
files=['pyproject.toml','README.md','MEMORY.md','AGENTS.md','LLM_GUIDE.md','PROVENANCE.md','VALIDATION.md','requirements.lock.txt',
       '.env.example','.gitignore','.dockerignore','Dockerfile','compose.yaml']
with ZipFile(destination,'w',ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(root/name,Path('pixel-avatar')/name)
    for directory in ('pixel_avatar','tests','scripts','examples'):
        for path in (root/directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
                archive.write(path,Path('pixel-avatar')/path.relative_to(root))
print(destination)
