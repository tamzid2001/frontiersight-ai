"""Validate real Cobertura hits, thresholds and coverage of changed production code."""
import argparse
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOTS=('engine/','agents/','integrations/','services/','edge/','sdk/')


def check(path,line=.8,branch=.7,base=None):
    root=ET.parse(path).getroot()
    if int(root.get('lines-valid','0'))==0 or int(root.get('lines-covered','0'))==0:raise ValueError('empty coverage report')
    if float(root.get('line-rate','0'))<line or float(root.get('branch-rate','0'))<branch:raise ValueError('coverage threshold not met')
    records={}
    for cls in root.findall('.//class'):
        name=cls.get('filename','').replace('\\','/')
        records[name]={int(row.get('number')):int(row.get('hits')) for row in cls.findall('./lines/line')}
    if not records or not any(hit>0 for rows in records.values() for hit in rows.values()):raise ValueError('no executed source lines')
    result={'line_percent':100*float(root.get('line-rate')),'branch_percent':100*float(root.get('branch-rate')),'files':len(records)}
    if base:
        if base.startswith('-') or not re.fullmatch('[A-Za-z0-9_./-]{1,100}',base):raise ValueError('invalid Git base')
        diff=subprocess.check_output(['git','diff','--no-renames','--unified=0',base,'--','*.py'],text=True)
        added={};name=None;number=0
        for row in diff.splitlines():
            if row.startswith('+++ b/'):name=row[6:]
            elif row.startswith('@@ '):number=int(re.search(r'\+(\d+)',row).group(1))
            elif row.startswith('+') and name and not row.startswith('+++'):
                if name.startswith(ROOTS):added.setdefault(name,set()).add(number)
                number+=1
            elif not row.startswith(('-', '\\')):number+=1
        covered=total=0;unmeasured=[]
        for name,lines in added.items():
            if name not in records:
                unmeasured.append(name);continue
            hits=records[name]
            executable=lines.intersection(hits)
            total+=len(executable);covered+=sum(hits[n]>0 for n in executable)
        if unmeasured:raise ValueError('changed source absent from report: '+', '.join(unmeasured))
        result.update(changed_executable_lines=total,changed_lines_covered=covered,changed_line_percent=100*covered/total if total else 100.)
        if total and covered/total<.9:raise ValueError('changed production line coverage below 90%: '+str(result))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('report');parser.add_argument('--line',type=float,default=.8);parser.add_argument('--branch',type=float,default=.7);parser.add_argument('--base')
    args=parser.parse_args();print(check(args.report,args.line,args.branch,args.base))
