"""Profile separately from timing runs; never compare profiled timings."""
import argparse
import cProfile
import io
import json
import pstats
import tracemalloc
from pathlib import Path
from build_benchmark import run

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--count', type=int, default=100)
    args = parser.parse_args()
    profile = cProfile.Profile()
    profile.enable(); run(args.count); profile.disable()
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).sort_stats('cumulative').print_stats(20)
    tracemalloc.start(); result = run(args.count); current, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    Path(args.output).write_text(json.dumps({'components': args.count,
        'python_traced_peak_bytes': peak, 'output_bytes': result['cold']['output_bytes'],
        'profile': stream.getvalue()}, indent=2) + '\n')
