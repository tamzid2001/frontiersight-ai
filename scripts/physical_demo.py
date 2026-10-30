"""Reproduce warehouse/flying counterfactuals without a browser or model key."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from engine.demos3d import demonstration
from engine.world3d import compare,digest


def demonstration_report(demo,variant):
    scene=demonstration(demo)
    if demo=='warehouse':
        joint=deepcopy(scene['objects'][2]['joint'])
        if variant=='earlier':joint['start_s']=0
        elif variant=='faster':joint['speed_mps']=.65
        elif variant=='unsafe':joint['target_m']=3.5
        elif variant=='elevated':
            path=deepcopy(scene['objects'][0]['waypoints']);path.append({'t_s':16,'position_m':[7,4,.65]})
            joint['start_s']=0
            return compare(scene,[{'object_id':'chassis','waypoints':path},{'object_id':'forks','joint':joint}])
        elif variant!='normal':raise ValueError('unknown warehouse variant')
        changes=[{'object_id':'forks','joint':joint}]
    else:
        changes=[{'object_id':'flying-vehicle','acceleration_mps2':[0,0,0] if variant=='grounded' else [0,0,2]}]
    return compare(scene,changes)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--demo',choices=['warehouse','flying'],default='warehouse')
    parser.add_argument('--variant',default='unsafe');parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    report=demonstration_report(args.demo,args.variant);args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'output':str(args.out),'sha256':digest(report),'baseline_events':len(report['baseline']['events']),
                      'counterfactual_events':len(report['counterfactual']['events']),'physical_actuation':False}))
