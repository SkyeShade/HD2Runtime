"""Import normalized wiki primary weapons into compact generated Lua data."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sdk'))
from tools.wiki_primary import compact
from reference_format import lua

DEFAULT_INPUT=ROOT/'data/wiki_primary_weapons.json'
DEFAULT_SUMMARY=ROOT/'data/wiki_primary_weapons.summary.json'
DEFAULT_OUTPUT=ROOT/'primary_mapper/wiki_data.lua'


def generate(source=DEFAULT_INPUT,summary=DEFAULT_SUMMARY,output=DEFAULT_OUTPUT,check=False):
    data=compact(Path(source),Path(summary))
    if data['weapon_count']!=55:raise ValueError('expected exactly 55 normalized primary weapons')
    body='-- Generated from data/wiki_primary_weapons.json; do not edit.\nreturn '+lua(data)+'\n'
    output=Path(output)
    if check:
        if not output.exists()or output.read_text(encoding='ascii')!=body:
            raise ValueError(f'{output} is stale; run scripts/import_primary_weapons.py')
    else:
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(body,encoding='ascii')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=DEFAULT_INPUT)
    parser.add_argument('--summary',type=Path,default=DEFAULT_SUMMARY)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    data=generate(args.input,args.summary,args.output,args.check)
    print(f"{data['weapon_count']} weapons -> {args.output}")


if __name__=='__main__':main()
