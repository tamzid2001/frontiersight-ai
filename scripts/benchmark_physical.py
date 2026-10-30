"""Measured local CPU simulation benchmark; no GPU/camera/inference claims."""
import argparse
import json
from pathlib import Path
import platform
import statistics
import subprocess
import time
import tracemalloc
from engine.demos3d import demonstration
from engine.world3d import simulate,digest
from edge.runtime import percentile


def benchmark(runs):
    reports=[]
    for name in ('warehouse','flying'):
        scene=demonstration(name);simulate(scene);samples=[]
        for _ in range(runs):
            start=time.perf_counter();result=simulate(scene);samples.append((time.perf_counter()-start)*1000)
        tracemalloc.start();simulate(scene);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        reports.append({'demo':name,'source_sha256':digest(scene),'samples_ms':samples,'latency_ms':{
            'p50':percentile(samples,.5),'p95':percentile(samples,.95),'p99':percentile(samples,.99)},
            'peak_traced_python_bytes_separate_run':peak,'frames':len(result['frames']),'objects':len(scene['objects'])})
    root=Path(__file__).resolve().parents[1]
    source_hashes={str(p.relative_to(root)):__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in sorted((root/'engine').glob('*3d*.py'))}
    return {'implementation_sha256':source_hashes,'platform':platform.platform(),'python':platform.python_version(),'runs':runs,'reports':reports,
            'scope':'CPU kinematic simulation; memory tracing measured in a separate run; no comparison/speedup, camera, inference or hardware claims.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runs',type=int,default=10);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if not 3<=args.runs<=100:raise ValueError('3..100 benchmark runs required')
    result=benchmark(args.runs);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'benchmarked':[r['demo'] for r in result['reports']],'runs':args.runs,'output':str(args.out)}))
