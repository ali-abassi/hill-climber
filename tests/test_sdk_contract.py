"""Synthetic SDK completion regressions; no model calls and no real session state."""
from __future__ import annotations
import json, math, os, shlex, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = r'''import {writeFileSync} from 'node:fs';
import {join} from 'node:path';
const spec=SPEC;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const usage=USAGE;
export class Codex {
  constructor(options) {
    if(spec.check_binary) {
      if(options.codexPathOverride!==spec.expected_binary) throw new Error('explicit binary was not passed to SDK');
      if('TOP_SECRET_FOR_CLIMB' in options.env || 'HILL_CLIMBER_CODEX_PATH' in options.env)
        throw new Error('controller settings or unrelated secret leaked into SDK environment');
    }
  }
  startThread(options) { return {async runStreamed(prompt,{signal}) {
    writeFileSync(join(options.workingDirectory,'solution.txt'),'1\n');
    if(spec.stage==='before_stream') await sleep(spec.delay);
    async function* events() {
      if(spec.stage==='before_event') await sleep(spec.delay);
      yield {type:'thread.started',thread_id:'synthetic-contract-thread'};
      yield {type:'turn.started'};
      if(spec.stage==='interrupt') {process.kill(process.pid,'SIGINT');await sleep(spec.delay);}
      yield {type:'item.completed',item:{type:'agent_message',text:spec.response}};
      if(spec.stage==='after_response') await sleep(spec.delay);
      yield {type:'turn.completed',usage};
      if(spec.duplicate) yield {type:'turn.completed',usage};
      if(spec.error) yield {type:'error',message:'synthetic provider error'};
      if(spec.stage==='after_complete') await sleep(spec.delay);
    }
    return {events:events()};
  }}; }
}
'''

def run(command, **kwargs):
    return subprocess.run(command, text=True, capture_output=True, **kwargs)

def one_case(source: Path, case: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix='hill-sdk-contract-') as raw:
        root=Path(raw); repo=root/'repo';repo.mkdir()
        for argv in (['git','init','-q'],['git','config','user.name','Synthetic Contract'],
                     ['git','config','user.email','contract@example.test']):
            subprocess.run(argv,cwd=repo,check=True,capture_output=True)
        (repo/'solution.txt').write_text('0\n')
        subprocess.run(['git','add','solution.txt'],cwd=repo,check=True)
        subprocess.run(['git','commit','-qm','baseline'],cwd=repo,check=True)
        bindir=root/'bin';bindir.mkdir();codex=bindir/'codex'
        codex.write_text("#!/bin/sh\nprintf '%s\\n' 'Logged in using ChatGPT'\n");codex.chmod(0o755)
        if case.get('check_binary'):
            alternate=bindir/'alternate codex'
            alternate.write_text("#!/bin/sh\nprintf '%s\\n' 'Logged in using ChatGPT'\n")
            alternate.chmod(0o755)
            codex.write_text("#!/bin/sh\nexit 1\n")
            case={**case,'expected_binary':str(alternate)}
        usage=case.get('usage',{'input_tokens':9,'output_tokens':5,'cached_input_tokens':0,'reasoning_output_tokens':0})
        sdk=root/'sdk.mjs'
        sdk.write_text(SDK.replace('SPEC',json.dumps(case)).replace('USAGE',case.get('usage_literal',json.dumps(usage))))
        evaluator="import json\nfrom pathlib import Path\nprint(json.dumps({'score':int(Path('solution.txt').read_text()),'gates':{'valid':True}}))\n"
        dev=root/'dev.py';private=root/'private.py';dev.write_text(evaluator);private.write_text(evaluator)
        experiment=root/'experiment'
        env=os.environ.copy();env.update(PATH=str(bindir)+os.pathsep+env['PATH'],HILL_CLIMBER_CODEX_MODULE=str(sdk))
        env.pop('HILL_CLIMBER_CODEX_PATH',None)
        if case.get('check_binary'):
            env['HILL_CLIMBER_CODEX_PATH']=case['expected_binary']
            env['TOP_SECRET_FOR_CLIMB']='synthetic-constructor-secret'
        for key in ('HILL_CLIMBER_FAKE_SCENARIO','HILL_CLIMBER_FAKE_DELAY_MS','PAL_SESSION','PAL_DEPTH','PAL_ROLE'):
            env.pop(key,None)
        command=[sys.executable,str(source/'bin/hill-climber'),'run','--json','--workspace',str(repo),
                 '--task','Improve a synthetic integer','--eval',shlex.join([sys.executable,str(dev)]),
                 '--holdout-eval',shlex.join([sys.executable,str(private)]),'--mutable','solution.txt',
                 '--candidates','1','--rounds','1','--generation-parallel','1','--candidate-timeout','1',
                 '--eval-timeout','3','--max-wall-seconds','20','--max-failures','1','--out',str(experiment),'--no-apply']
        try: result=run(command,cwd=repo,env=env,timeout=8)
        except subprocess.TimeoutExpired: return {'passed':False,'reason':'controller exceeded outer watchdog'}
        try:
            assert len(result.stdout.strip().splitlines())==1,'stdout is not one JSON document'
            response=json.loads(result.stdout)
            trace=json.loads((experiment/'candidates/r01-c01/turn.json').read_text())
            assert trace.get('thread_id') in (None,'synthetic-contract-thread'),'session identity changed'
            assert (repo/'solution.txt').read_text()=='0\n','source applied despite --no-apply'
            assert not (experiment/'run.lock').exists(),'writer lock left behind'
            state=json.loads((experiment/'state.json').read_text())
            assert all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>=0
                       for x in state['usage'].values()),'invalid usage corrupted durable aggregate'
            if case['expected']=='valid':
                assert result.returncode==0 and response['result']['status']=='promoted','valid candidate rejected'
                generated=json.loads((experiment/'candidates/r01-c01/generated.json').read_text())
                assert generated['metadata']==json.loads(case['response']),'metadata changed'
            elif case['expected']=='interrupt':
                assert result.returncode==130 and response['error']['code']=='E_INTERRUPTED','interrupt misclassified'
                assert not (experiment/'candidates/r01-c01/generated.json').exists(),'cancelled turn became generated'
                assert state['usage']['input_tokens']==9 and state['usage']['output_tokens']==5,'reported interrupt usage lost'
            else:
                assert result.returncode==1 and response['result']['status']=='retained','unfinished/invalid candidate promoted'
                failure=json.loads((experiment/'candidates/r01-c01/failure.json').read_text())
                assert failure['code']==case['expected'],f"expected {case['expected']}, received {failure['code']}"
                assert response['result']['promotion']['holdout_used'] is False,'invalid candidate reached holdout'
                assert response['result']['counts']['crashed']+response['result']['counts']['invalid']==1,'failure not accounted'
                expected_input,expected_output=(0,0) if case.get('invalid_usage') else (9,5)
                assert (state['usage']['input_tokens'],state['usage']['output_tokens'])==(expected_input,expected_output),'reported usage missing or unsafe'
            status=run([sys.executable,str(source/'bin/hill-climber'),'status',str(experiment),'--json'],cwd=repo,env=env,timeout=5)
            assert status.returncode==0 and json.loads(status.stdout)['ok'],'saved evidence cannot be inspected'
            return {'passed':True}
        except (AssertionError,KeyError,ValueError,FileNotFoundError) as error:
            return {'passed':False,'reason':str(error)}


class SDKCompletionContractTests(unittest.TestCase):
    def check_case(self, expected="valid", metadata=None, **options):
        metadata = metadata if metadata is not None else {
            "mechanism": "bounded-extractor", "hypothesis": "Preserve the transport contract.",
            "summary": "Synthetic candidate completed.",
        }
        result = one_case(ROOT, {"id": "native-contract", "expected": expected,
                                 "response": json.dumps(metadata, ensure_ascii=False), **options})
        self.assertTrue(result["passed"], result.get("reason"))

    def test_valid_metadata_and_unicode_boundaries_still_promote(self):
        self.check_case(metadata={"mechanism": "😀" * 160, "hypothesis": "h" * 1000,
                                  "summary": "s" * 2000})
        self.check_case(usage={"input_tokens": 0, "output_tokens": 14})

    def test_schema_extras_and_oversized_metadata_cannot_promote(self):
        self.check_case("E_SDK_SCHEMA", metadata={"mechanism": "m", "hypothesis": "h",
                                                 "summary": "s", "score": 999})
        self.check_case("E_SDK_SCHEMA", metadata={"mechanism": "m", "hypothesis": "h",
                                                 "summary": "s" * 2001})

    def test_invalid_usage_cannot_corrupt_counters_or_promote(self):
        for usage in ({"input_tokens": -1, "output_tokens": 5},
                      {"input_tokens": "9", "output_tokens": 5},
                      {"input_tokens": 9.5, "output_tokens": 5},
                      {"input_tokens": 9, "output_tokens": 5, "cached_input_tokens": -1}):
            with self.subTest(usage=usage):
                self.check_case("E_SDK_EMPTY", usage=usage, invalid_usage=True)

    def test_expired_finite_streams_preserve_meter_but_cannot_promote(self):
        for stage in ("before_stream", "after_complete"):
            with self.subTest(stage=stage):
                self.check_case("E_CANDIDATE_TIMEOUT", stage=stage, delay=1150)

    def test_user_cancellation_does_not_publish_late_generated_candidate(self):
        self.check_case("interrupt", stage="interrupt", delay=80)

    def test_explicit_binary_is_used_for_auth_and_sdk_without_environment_leaks(self):
        self.check_case(check_binary=True)

    def test_provider_error_keeps_reported_usage_and_inspectable_evidence(self):
        self.check_case("E_SDK", error=True)


if __name__ == "__main__":
    unittest.main()
