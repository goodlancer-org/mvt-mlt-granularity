"""Compile the supplied extended LaTeX manuscript without rebuilding it from Markdown."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
from .pipeline import ROOT


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('build',),default='build',nargs='?')
    parser.add_argument('--tex-file',type=Path,default=ROOT/'paper/latex/_main.tex')
    args=parser.parse_args(argv);tex=args.tex_file.resolve()
    work=ROOT/'.paper-build'/tex.stem;work.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ);env['TEXINPUTS']='.'+os.pathsep+tex.parent.as_posix()+'//'+os.pathsep+env.get('TEXINPUTS','')
    command=['pdflatex','-interaction=nonstopmode','-halt-on-error',str(tex)]
    subprocess.run(command,cwd=work,env=env,check=True)
    for p in tex.parent.glob('*.bib'):shutil.copy2(p,work/p.name)
    subprocess.run(['bibtex',tex.stem],cwd=work,env=env,check=True)
    for _ in range(3):subprocess.run(command,cwd=work,env=env,check=True)
    shutil.copy2(work/(tex.stem+'.pdf'),tex.with_suffix('.pdf'))
    print(tex.with_suffix('.pdf'))
    return 0

if __name__=='__main__':raise SystemExit(main())
