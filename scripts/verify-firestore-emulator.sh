#!/usr/bin/env bash
# Local/CI only, never points at a real cloud database.
set -euo pipefail
emulator_jar="${TMPDIR:-/tmp}/quantura-firestore-emulator-v1.20.2.jar"
if [ ! -f "$emulator_jar" ]; then
  curl --fail --silent --show-error --location https://storage.googleapis.com/firebase-preview-drop/emulator/cloud-firestore-emulator-v1.20.2.jar --output "$emulator_jar"
fi
printf '%s  %s\n' 4a117fc297b1441eac1b7756e80442e86ef88865b9e3caf6f59eabf83da574f8 "$emulator_jar" | shasum -a 256 --check
java -Xms128m -Xmx512m -jar "$emulator_jar" --host 127.0.0.1 --port 56654 --project_id demo-quantura-web --single_project_mode --rules packages/enterprise-web/test/firestore-emulator.rules > /tmp/quantura-firestore-emulator.log 2>&1 &
emulator_pid=$!
trap 'kill "$emulator_pid" 2>/dev/null || true' EXIT
for attempt in {1..30}; do
  if curl --silent --fail http://127.0.0.1:56654 > /dev/null; then break; fi
  sleep 1
done
export FIRESTORE_EMULATOR_HOST=127.0.0.1:56654
(cd packages/enterprise-web && npm run coverage && python3 scripts/check-coverage.py && npm run build)
python -m pytest -q --cov=services.api.clerk_auth --cov=services.api.firestore_scenes --cov=services.api.workspace_http --cov-branch --cov-report=xml:coverage/firestore.xml

python - <<'PYCODE'
from xml.etree import ElementTree as E
r=E.parse('coverage/firestore.xml').getroot()
assert int(r.attrib['lines-valid'])>0 and float(r.attrib['line-rate'])>=.90
assert int(r.attrib['branches-valid'])>0 and float(r.attrib['branch-rate'])>=.70
print('Python Firestore coverage gates passed')
PYCODE
