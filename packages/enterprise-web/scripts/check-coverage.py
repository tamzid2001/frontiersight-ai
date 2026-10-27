"""Validate actual server Cobertura hit counts and acceptance gates."""
from pathlib import Path
from xml.etree import ElementTree as E
p=Path('coverage/cobertura-coverage.xml')
r=E.parse(p).getroot()
classes=r.findall('.//class');assert len(classes)>=10,'missing executed server files'
valid=int(r.attrib['lines-valid']);hits=int(r.attrib['lines-covered'])
assert valid>0 and hits>0 and hits/valid>=0.90,'line coverage below 90%'
bv=int(r.attrib['branches-valid']);bc=int(r.attrib['branches-covered'])
assert bv>0 and bc/bv>=0.80,'branch coverage below 80%'
for c in classes:
 lines=c.findall('./lines/line');assert lines and any(int(x.attrib['hits'])>0 for x in lines),c.attrib['filename']
 assert float(c.attrib['line-rate'])>=0.90,c.attrib['filename']+' below 90% lines'
assert Path('coverage/lcov.info').stat().st_size>100
print(f'Server coverage: {100*hits/valid:.2f}% lines, {100*bc/bv:.2f}% branches; valid Cobertura and LCOV')
