"""Independent schema and threshold verification; never writes acceptance numbers."""
import argparse
import json
from pathlib import Path


def verify(folder):
    folder=Path(folder)
    skill=json.loads((folder/'skill_report.json').read_text(encoding='utf-8'))
    custom=json.loads((folder/'custom_report.json').read_text(encoding='utf-8'))
    daemon=json.loads((folder/'daemon_report.json').read_text(encoding='utf-8'))
    shapes=skill['skills'];trials=skill['trials']
    checks={
        'three_skill_forms':len(shapes)>=3 and any(not s['has_scripts'] and not s['uses_mcp'] for s in shapes) and any(s['has_scripts'] for s in shapes) and any(s['uses_mcp'] for s in shapes),
        'progressive_disclosure':skill['disclosure_ratio']>=5 and skill['catalog_has_no_bodies'],
        'six_trials_including_negative':len(trials)>=6 and any(t['expected'] is None for t in trials) and all({'query','expected','hit','ok'}<=t.keys() and t['ok'] and t['hit']==t['expected'] for t in trials),
        'no_false_positive':skill['false_positive']==0 and not any(t['hit'] is not None for t in trials if t['expected'] is None),
        'same_code_off_on':skill['before_after']['same_code'] and [r['enable_skills'] for r in skill['before_after']['runs']]==[0,1] and len({r['query'] for r in skill['before_after']['runs']})==1,
        'rules_found_within_limit':custom['agents_md']['found'] and custom['agents_md']['bytes']<=12000 and custom['agents_md']['layers']==['global','project'],
        'denials_have_reasons':len(custom['denied'])>=2 and all(d['denied'] and d['reason'] for d in custom['denied']),
        'real_red_to_green':custom['autotest']['red_to_green']>=1 and custom['autotest']['red']>=1 and custom['autotest']['green']>=1 and custom['autotest']['injected_lines']<=3,
        'reviewer_context_isolated':custom['reviewer']['runs']>=1 and custom['reviewer']['context_isolated'] and 0<custom['reviewer']['main_context_delta']<=500 and custom['reviewer']['subagent_tokens']>0,
        'optional_two_capabilities':len(daemon['qualified_capabilities'])>=2 and daemon['triggers_fired']>=1 and daemon['resume_from_step']==4 and daemon['idempotent'],
        'optional_required_fields':{'triggers_fired','resume_from_step','notify_fired','idempotent'}<=daemon.keys(),
        'all_executable_reports_passed':all(r.get('passed') for r in (skill,custom,daemon)),
    }
    return {'passed':all(checks.values()),'checks':checks}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',nargs='?',type=Path,default=Path('reports'));args=parser.parse_args()
    result=verify(args.folder);print(json.dumps(result,ensure_ascii=True,indent=2));raise SystemExit(0 if result['passed'] else 1)
