"""Validate frozen prompts synchronously before entering the transport event loop."""
from pathlib import Path
import argparse
import asyncio
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cce_generation_confirmation_v2 as frozen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=frozen.OUT)
    parser.add_argument('--ids',nargs='+',choices=frozen.IDS)
    parser.add_argument('--allow-local-calls',action='store_true')
    args=parser.parse_args()
    # The original prompt helper uses asyncio.run internally. It is a local
    # prompt construction operation and must execute before the transport loop.
    state=frozen.validate(args.out)
    def already_validated(out):
        if Path(out).resolve()!=args.out.resolve():raise ValueError('VALIDATED_OUTPUT_IDENTITY')
        frozen.base.verify_bindings(state[0]['frozen_inputs'])
        return state
    frozen.validate=already_validated
    dest=args.out/'runtime_records'/(frozen.j.now().replace(':','').replace('+','_')+'.json')
    frozen.write(dest,dict(adapter=frozen.bind(__file__),plan=frozen.bind(args.out/'plan.json'),
        action='Move exact prompt reconstruction and validation before asyncio transport loop; scientific payload bytes and processor unchanged.',
        actual_command=[sys.executable,*sys.argv],new_requests_from_validation=0))
    asyncio.run(frozen.run(args))


if __name__=='__main__':main()
