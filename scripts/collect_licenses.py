#!/usr/bin/env python3
"""Copy the downloaded Go modules' notices alongside the compiled binary."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

destination = Path(sys.argv[1])
data = subprocess.check_output(['go', 'list', '-m', '-json', 'all'], text=True)
decoder = json.JSONDecoder()
while data.strip():
    module, end = decoder.raw_decode(data.lstrip())
    data = data.lstrip()[end:]
    if 'Dir' not in module or module.get('Main'):
        continue
    for file in Path(module['Dir']).iterdir():
        if file.is_file() and file.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE', 'AUTHORS')):
            folder = destination / 'go-modules' / (module['Path'].replace('/', '~') + '@' + module['Version'])
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, folder / file.name)
goroot = Path(subprocess.check_output(['go', 'env', 'GOROOT'], text=True).strip())
shutil.copyfile(goroot / 'LICENSE', destination / 'Go-LICENSE.txt')
