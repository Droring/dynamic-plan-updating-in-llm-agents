"""Verify the final or historical release manifest without network or writes."""
import argparse
import hashlib
import json
from pathlib import Path

def verify(root,manifest_path):
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    failures=[]
    for name,expected in manifest['sha256'].items():
        path=root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:failures.append(name)
    return {'checked':len(manifest['sha256']),'mismatches':failures}

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--historical',action='store_true',help='compare against the older snapshot (expected differences)')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    name='RELEASE_MANIFEST_HISTORICAL.json' if args.historical else 'RELEASE_MANIFEST_FINAL.json'
    result=verify(root,root/'provenance'/name)
    print(json.dumps(result,ensure_ascii=False))
    if result['mismatches']:raise SystemExit(1)
