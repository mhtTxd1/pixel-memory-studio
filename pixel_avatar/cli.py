import argparse
import json
from pathlib import Path
from .pipeline import create_job,run_job,approve,retry_stage,load


def main():
    parser=argparse.ArgumentParser(description="Photo → pixel avatar (one person per job)")
    sub=parser.add_subparsers(dest="cmd",required=True)
    create=sub.add_parser("create")
    create.add_argument("photos",nargs="+")
    create.add_argument("--root",default="data")
    create.add_argument("--name",default="Avatar")
    create.add_argument("--notes",default="")
    create.add_argument("--pixel-block",type=int,default=2,choices=[1,2,4])
    for name in ("run","status","approve","retry"):
        p=sub.add_parser(name); p.add_argument("folder",type=Path)
        if name in ("approve","retry"):
            p.add_argument("stage"); p.add_argument("note")
    args=parser.parse_args()
    try:
        if args.cmd=="create":
            print(create_job(args.root,args.photos,args.name,args.notes,args.pixel_block)); return
        result = {"run":lambda:run_job(args.folder),"status":lambda:load(args.folder),
                  "approve":lambda:approve(args.folder,args.stage,args.note),
                  "retry":lambda:retry_stage(args.folder,args.stage,args.note)}[args.cmd]()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:
        parser.exit(1,f"{type(exc).__name__}: {exc}\n")


if __name__=="__main__": main()
