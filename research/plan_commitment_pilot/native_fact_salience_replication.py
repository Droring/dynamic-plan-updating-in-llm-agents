#!/usr/bin/env python3
"""Repeat identical native factual-salience protocol on two other archived tasks."""
import argparse
import asyncio
from pathlib import Path
import native_fact_salience_control as study

study.CASES={
 "Query00261":{"old":"scenic_route","new":"comfort_priority",
    "old_next":["Transportation_Refine_to_Step2","Select_Final_Transportation"],
    "alternative":[]},
 "Query00249":{"old":"scenic_route","new":"comfort_priority",
    "old_next":["Transportation_Search_to_Final_4Steps"],
    "alternative":[]}
}
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--costbench-root",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--call-cap",type=int,default=4)
    a=p.parse_args()
    if not 1<=a.call_cap<=4:raise ValueError("max 4 model calls per continuation")
    asyncio.run(study.execute(a.costbench_root.resolve(),a.out.resolve(),a.call_cap))
