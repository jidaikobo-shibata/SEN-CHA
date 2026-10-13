"""Measure this process and decoder child peak RSS separately on Linux/macOS."""
import json
from pathlib import Path
import platform
import resource
import sys

from tvfc.analysis import analyze

report = analyze(Path(sys.argv[1]))
scale = 1 if sys.platform == 'darwin' else 1024
result = {
    'platform':platform.platform(), 'processor':platform.processor(),
    'python':platform.python_version(), 'video':report['metadata'],
    'frames':report['frames'], 'analysis_seconds':report['elapsed'],
    'video_seconds_per_wall_second':report['metadata']['duration']/report['elapsed'],
    'analysis_process_peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*scale/1024**2,
    'decoder_child_peak_rss_mib':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*scale/1024**2,
    'candidate_count':len(report['candidates']), 'settings':report['settings']
}
print(json.dumps(result,ensure_ascii=False,indent=2))
