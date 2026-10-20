import argparse
import json
from pathlib import Path
from .scenes import create_scene, run_scene, retry_scene
from .movie import create_movie, render_movie
from .pipeline import load


def main():
    parser=argparse.ArgumentParser(description='Micro-pixel scene + avatars -> an 8-second 2D memory')
    sub=parser.add_subparsers(dest='cmd',required=True)
    scene=sub.add_parser('scene-create')
    scene.add_argument('--description',default='');scene.add_argument('--photo',type=Path)
    scene.add_argument('--style-avatar',type=Path);scene.add_argument('--root',default='data/scenes')
    scene.add_argument('--aspect',default='landscape',choices=['landscape','portrait','square'])
    scene.add_argument('--pixel-block',type=int,default=2,choices=[1,2,4])
    for name in ('scene-run','scene-retry','render','status'):
        p=sub.add_parser(name);p.add_argument('folder',type=Path)
        if name=='scene-retry':p.add_argument('description')
    movie=sub.add_parser('movie-create')
    movie.add_argument('--scene',type=Path,required=True)
    movie.add_argument('--avatar',type=Path,action='append',required=True)
    movie.add_argument('--options',type=Path,help='JSON with timeline and render options')
    movie.add_argument('--caption',default='');movie.add_argument('--preset',default='meet',choices=['meet','celebrate','quiet'])
    movie.add_argument('--root',default='data/movies')
    args=parser.parse_args()
    try:
        if args.cmd=='scene-create':
            print(create_scene(args.root,args.description,args.photo,args.style_avatar,args.aspect,args.pixel_block));return
        if args.cmd=='movie-create':
            options=json.loads(args.options.read_text(encoding='utf-8')) if args.options else {'caption':args.caption,'preset':args.preset}
            print(create_movie(args.root,args.scene,args.avatar,options));return
        result={'scene-run':lambda:run_scene(args.folder),'scene-retry':lambda:retry_scene(args.folder,args.description),
                'render':lambda:render_movie(args.folder),'status':lambda:load(args.folder)}[args.cmd]()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:parser.exit(1,f'{type(exc).__name__}: {exc}\n')


if __name__=='__main__':main()
