"""Every feature cell cites code. Check each citation names a file that exists at the pinned
revision and lines inside it; fail the build otherwise."""
import json
import re
import sys

from common import CONFIG, ROOT, source_dir

VALUES = {'yes', 'partial', 'engine-only', 'no', 'unknown'}


def citations(text):
    for item in (t.strip() for t in text.split(';') if t.strip()):
        m = re.fullmatch(r'([a-z0-9-]+):([^:]+?)(?::(\d+)(?:-(\d+))?)?', item)
        if not m:
            raise ValueError(f'unreadable citation {item!r}')
        yield m.groups()


def main():
    problems, count = [], 0
    for wallet in CONFIG['wallets']:
        features = json.loads((ROOT / f'features/{wallet.lower()}.json').read_text())['features']
        for key, cell in features.items():
            if key != 'license' and cell['value'] not in VALUES:
                problems.append(f'{wallet}.{key}: value {cell["value"]!r}')
            for source, path, a, b in citations(cell['evidence']):
                count += 1
                if source not in CONFIG['sources']:
                    problems.append(f'{wallet}.{key}: unknown source {source}')
                    continue
                f = source_dir(source) / path
                if not f.is_file():
                    problems.append(f'{wallet}.{key}: missing {source}:{path}')
                    continue
                n = len(f.read_text(errors='ignore').splitlines())
                for line in (a, b):
                    if line and int(line) > n:
                        problems.append(f'{wallet}.{key}: {source}:{path} has {n} lines, cites {line}')
    profiles = json.loads((ROOT / 'wallets.json').read_text())['profiles']
    for wallet, profile in profiles.items():
        for key, value in profile.items():
            if isinstance(value, dict) and value.get('cite'):
                for source, path, a, b in citations(value['cite']):
                    count += 1
                    f = source_dir(source) / path
                    if not f.is_file():
                        problems.append(f'{wallet} profile {key}: missing {source}:{path}')
                    elif a and int(a) > len(f.read_text(errors='ignore').splitlines()):
                        problems.append(f'{wallet} profile {key}: {source}:{path} is shorter than line {a}')
    if problems:
        sys.exit('\n'.join(problems))
    print(f'{count} citations resolve at the pinned revisions')


if __name__ == '__main__':
    main()
