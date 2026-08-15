#!/usr/bin/env bash
set -euo pipefail

BASE='https://www.task-force.app'
CURL=(curl -LsS --connect-timeout 5 --max-time 15)
SECRET_FILE='/var/lib/louis-os/secrets/taskforce.env'
OUT='/var/lib/louis-os/results/taskforce'
mkdir -p "$OUT"

if [[ ! -s "$SECRET_FILE" ]]; then
  echo 'VERIFY_GATE=missing_taskforce_vm_secret'
  exit 2
fi
# shellcheck disable=SC1090
source "$SECRET_FILE"

code="$("${CURL[@]}" -o "$OUT/challenge-live.json" -w '%{http_code}' \
  -X POST "$BASE/api/agent/verify/challenge" \
  -H "Authorization: Bearer $TASKFORCE_API_KEY" \
  -H 'Content-Type: application/json' -d '{}')"
echo "CHALLENGE_HTTP=$code"
[[ "$code" == '200' ]] || { cat "$OUT/challenge-live.json"; exit 3; }

python3 - "$OUT/challenge-live.json" "$OUT/challenge-answer.json" <<'PY'
import ast, json, operator, re, sys
src, dst = sys.argv[1:]
d=json.load(open(src))
cid=d.get('challengeId')
prompt=str(d.get('prompt') or '').strip()
print('CHALLENGE_ID_PRESENT=' + ('true' if cid else 'false'))
print('CHALLENGE_PROMPT=' + json.dumps(prompt, ensure_ascii=False))
if not cid or not prompt:
    raise SystemExit(4)

def eval_expr(expr):
    allowed_bin={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.FloorDiv:operator.floordiv,ast.Mod:operator.mod}
    allowed_un={ast.UAdd:operator.pos,ast.USub:operator.neg}
    def go(n):
        if isinstance(n,ast.Expression): return go(n.body)
        if isinstance(n,ast.Constant) and isinstance(n.value,(int,float)): return n.value
        if isinstance(n,ast.BinOp) and type(n.op) in allowed_bin: return allowed_bin[type(n.op)](go(n.left),go(n.right))
        if isinstance(n,ast.UnaryOp) and type(n.op) in allowed_un: return allowed_un[type(n.op)](go(n.operand))
        raise ValueError('unsupported expression')
    return go(ast.parse(expr,mode='eval'))

answer=None
candidates=re.findall(r'(?<![\w.])[-+]?\d+(?:\.\d+)?(?:\s*[-+*/%]\s*[-+]?\d+(?:\.\d+)?)+(?![\w.])', prompt)
if candidates:
    try:
        v=eval_expr(candidates[-1])
        answer=str(int(v)) if isinstance(v,(int,float)) and float(v).is_integer() else str(v)
    except Exception:
        pass

if answer is None:
    p=prompt.lower()
    nums=[float(x) for x in re.findall(r'-?\d+(?:\.\d+)?',p)]
    if len(nums)>=2:
        a,b=nums[-2],nums[-1]
        if any(w in p for w in (' plus ',' add ',' sum ')): v=a+b
        elif any(w in p for w in (' minus ',' subtract ',' difference ')): v=a-b
        elif any(w in p for w in (' times ',' multiply ',' product ')): v=a*b
        elif any(w in p for w in (' divided by ',' divide ',' quotient ')) and b != 0: v=a/b
        else: v=None
        if v is not None: answer=str(int(v)) if float(v).is_integer() else str(v)

if answer is None:
    quoted=re.findall(r'["“](.*?)["”]',prompt)
    token=quoted[-1] if quoted else None
    low=prompt.lower()
    if token is not None and ('how many words' in low or 'count the words' in low):
        answer=str(len(re.findall(r'\S+', token.strip())))
    elif token is not None and 'reverse' in low: answer=token[::-1]
    elif token is not None and ('uppercase' in low or 'upper case' in low): answer=token.upper()
    elif token is not None and ('lowercase' in low or 'lower case' in low): answer=token.lower()

if answer is None:
    print('VERIFY_GATE=unsupported_challenge_shape')
    raise SystemExit(5)
print('ANSWER_KIND=deterministic')
json.dump({'challengeId':cid,'answer':answer},open(dst,'w'))
PY

submit="$("${CURL[@]}" -o "$OUT/verify-submit.json" -w '%{http_code}' \
  -X POST "$BASE/api/agent/verify/submit" \
  -H "Authorization: Bearer $TASKFORCE_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @"$OUT/challenge-answer.json")"
echo "VERIFY_SUBMIT_HTTP=$submit"
python3 - "$OUT/verify-submit.json" <<'PY'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception:
    print('VERIFY_RESPONSE_PARSE=false'); print(open(sys.argv[1]).read()[:1000]); raise SystemExit(6)
print('VERIFY_RESPONSE_PARSE=true')
print('VERIFIED=' + str(bool(d.get('verified') or d.get('success') or str(d.get('status','')).upper() in {'VERIFIED','ACTIVE'})).lower())
print('STATUS=' + str(d.get('status') or (d.get('agent') or {}).get('status') or ''))
PY

tasks="$("${CURL[@]}" -o "$OUT/tasks-after-verify.json" -w '%{http_code}' \
  "$BASE/api/agent/tasks?status=ACTIVE&limit=100" \
  -H "X-API-Key: $TASKFORCE_API_KEY")"
echo "TASKS_AFTER_VERIFY_HTTP=$tasks"
python3 - "$OUT/tasks-after-verify.json" <<'PY'
import datetime as dt,json,sys
try: d=json.load(open(sys.argv[1]))
except Exception:
    print('TASKS_PARSE=false'); print(open(sys.argv[1]).read()[:1000]); raise SystemExit
items=d.get('tasks',d.get('data',d if isinstance(d,list) else [])) if isinstance(d,(dict,list)) else []
if not isinstance(items,list): items=[]
print('TASKS_SEEN='+str(len(items)))
now=dt.datetime.now(dt.timezone.utc); q=[]
for j in items:
    if not isinstance(j,dict): continue
    budget=j.get('totalBudget',j.get('budgetUsdc',j.get('budget',0)))
    try: budget=float(budget or 0)
    except Exception: budget=0
    dl=j.get('deadline') or j.get('deadlineAt') or ''
    fresh=True
    if dl:
        try:
            x=dt.datetime.fromisoformat(str(dl).replace('Z','+00:00'))
            if x.tzinfo is None: x=x.replace(tzinfo=dt.timezone.utc)
            fresh=x>=now
        except Exception: pass
    if fresh and 1<=budget<=100: q.append(j)
print('QUALIFIED_1_100_USDC='+str(len(q)))
for j in q[:12]:
    safe={k:j.get(k) for k in ('id','title','status','category','totalBudget','budgetUsdc','deadline','skillsRequired','paymentType')}
    print('CANDIDATE='+json.dumps(safe,separators=(',',':'),ensure_ascii=False)[:2200])
PY
