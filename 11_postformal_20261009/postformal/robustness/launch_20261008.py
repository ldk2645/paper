"""Operational wrapper for the frozen supplement and retained plotting vendor.

Load the pinned physical NumPy before making plotting-only vendor packages
available. This wrapper changes no study parameters or analysis decisions.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
import numpy as np
if np.__version__ != '2.3.5':
    raise RuntimeError('Physical model requires NumPy 2.3.5')
VENDOR = ROOT/'outputs/formal_reporting_tools_20261003/vendor'
sys.path.append(str(VENDOR))
CONTROL = ROOT/'postformal/robustness/launch_20261008'
os.environ['MPLCONFIGDIR'] = str(CONTROL/'matplotlib_cache')
import matplotlib
matplotlib.use('Agg')
from postformal.simulation.run import pipeline
from postformal.simulation.common import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    import matplotlib.pyplot as plt
    CONTROL.mkdir(parents=True, exist_ok=True)
    if args.check:
        fig, ax = plt.subplots(figsize=(3,2))
        ax.plot([0,1],[0,1])
        ax.set_title('Rendering dependency check')
        for suffix in ('png','pdf'):
            fig.savefig(CONTROL/('render_check.'+suffix))
        plt.close(fig)
        print(json.dumps({'status':'passed','numpy':np.__version__,'matplotlib':matplotlib.__version__,
                          'models_executed':0,'png_pdf_rendered':True}))
        return
    receipt = {'status':'launched','pid':os.getpid(),'started_at':datetime.now(timezone.utc).isoformat(),
               'python':sys.executable,'numpy':np.__version__,'matplotlib':matplotlib.__version__,
               'launcher_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'registry':'postformal/robustness/registry_20261008',
               'pipeline':'postformal/robustness/execution_20261008','workers':3,
               'plotting_vendor':str(VENDOR),'numpy_file':np.__file__}
    write_json(CONTROL/'launch.json',receipt)
    try:
        result = pipeline(ROOT/receipt['registry'], ROOT/receipt['pipeline'], 3)
    except BaseException as exc:
        write_json(CONTROL/'completion.json',dict(receipt,status='failed',error=repr(exc),
                   completed_at=datetime.now(timezone.utc).isoformat()))
        raise
    write_json(CONTROL/'completion.json',dict(receipt,status=result['status'],
               completed_at=datetime.now(timezone.utc).isoformat()))
    print(json.dumps({'status':result['status'],'pipeline':receipt['pipeline']}),flush=True)


if __name__ == '__main__':
    main()
