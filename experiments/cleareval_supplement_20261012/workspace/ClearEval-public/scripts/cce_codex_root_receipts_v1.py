"""Record actual root-observed spawn/ack receipts for the fixed Codex matrix."""
from pathlib import Path
import argparse
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_codex_repeat_extension_v1 as ext
old, j = ext.old, ext.j


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['dispatch', 'return'])
    p.add_argument('--cell', required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    row = old.selected(j.read(ext.OUT/'matrix.json'), a.cell)
    out = Path(row['source_out'])
    dest = old.directory(out, row)
    receipt = j.read(a.receipt)
    if a.action == 'dispatch':
        e = dict(recorded_by='root_agent', event='actual_subagent_started',
            tool_name='collaboration.spawn_agent', fork_turns='none', cell_id=a.cell,
            packet_sha256=row['packet']['sha256'], actual_agent_id=receipt['agent_id'],
            actual_tool_receipt=receipt, one_packet_only=True, followup_sent=False,
            root_experiment_history_passed=False, assigned_packet_path=row['packet']['path'],
            only_assigned_packet_read_permitted=True, assigned_submission_path=row['submission_path'],
            only_one_apply_patch_creation_permitted=True, declared_model_override=None)
    else:
        dispatch=j.read(dest/'actual_dispatch_evidence.json')
        raw=Path(row['submission_path']).read_bytes()
        e=dict(recorded_by='root_agent',event='actual_subagent_file_submission',
            response_kind='agent_authored_file_submission',source_kind=old.SOURCE_KIND,
            cell_id=a.cell,actual_agent_id=dispatch['actual_agent_id'],raw_sha256=old.handoff.rawsha(raw),
            root_edited=False,submission_path=row['submission_path'],actual_final_ack_receipt=receipt,
            root_sent_followup=False,independently_observed_creation=False,
            agent_reported_creation_attestation=dict(source='agent_self_report',independently_observed=False,
                tool_name='apply_patch',operation='create',write_count=receipt['reported_write_count'],
                revised=receipt['reported_revised'],raw_acknowledgement=receipt['acknowledgement']))
    ep=dest/('root_'+a.action+'_record.json')
    old.once(ep,e)
    args=argparse.Namespace(out=out,cell_id=a.cell,evidence=ep,raw=Path(row['submission_path']),
        approval=old.OUT/'root_approval.json',action='record-dispatch' if a.action=='dispatch' else 'import-result')
    if out==old.OUT:
        (old.record_dispatch if a.action=='dispatch' else old.import_result)(args)
    else:
        ext.action(args)


if __name__=='__main__':main()
