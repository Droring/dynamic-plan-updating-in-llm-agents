"""High-precision recovery of actual pre-event LLM textual plan commitments.

NOT a solver replacement: parse only unambiguous paths explicitly selected in
the original pre-event assistant response. Decline when unclear. The recovered
suffix is checked against the actual native post-prefix type state using only
the old PUBLIC tool catalogue. No hidden reference path or future observation.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Mapping, Sequence

from .core import ToolSpec, simulate

LABELS = "ABCDE"
SEQ = re.compile(r"(?<![A-Za-z0-9_])([A-E]{1,5}(?:\s*(?:→|->|⇒|\+|·|,)\s*[A-E]{1,5}){1,4})(?![A-Za-z0-9_])")
SEGMENT = re.compile(r"\s*(?:→|->|⇒|\+|·|,)\s*")
KEYWORD = re.compile(r"(?i)lowest[ -]cost|minimum[ -]cost|cheapest|optimal\s+(?:path|plan)|selected\s+path|chosen\s+path|\bmy\s+plan\b|\buse\s+path\b")
BACKTICK = re.compile(r"`([A-Za-z_][A-Za-z_0-9]*)`")


@dataclass(frozen=True)
class Commitment:
    status: str
    full_path: tuple[str, ...]
    remaining_path: tuple[str, ...]
    evidence: str
    provenance: str
    matching_candidates: int


def _atomic_stages(tools: Mapping[str, ToolSpec]) -> dict[str,int] | None:
    rules = [
        lambda n: n.startswith("Decide_") and "Preference" in n,
        lambda n: n.startswith("Search_") and "Candidates" in n,
        lambda n: n.endswith("Refinement_Step1"),
        lambda n: n.endswith("Refinement_Step2"),
        lambda n: n.startswith("Select_Final_"),
    ]
    found = []
    for rule in rules:
        options=[t for t in tools.values() if rule(t.name)]
        if len(options)!=1:return None
        found.append(options[0])
    if len({x.output for x in found})!=5:return None
    return {t.output:i for i,t in enumerate(found,1)}


def public_blocks(tools: Mapping[str, ToolSpec]) -> dict[str,tuple[str,...]]:
    """Map atomic stage spans to unique public tool names (no hidden graph)."""
    stages=_atomic_stages(tools)
    if stages is None:return {}
    blocks={}
    for spec in tools.values():
        end=stages.get(spec.output)
        if end is None:continue
        before=max((stages.get(t,0) for t in spec.inputs),default=0)
        if before>=end:continue
        span=LABELS[before:end]
        blocks.setdefault(span,[]).append(spec.name)
    return {k:tuple(v) for k,v in blocks.items()}


def _candidate_paths(content:str,tools:Mapping[str,ToolSpec]):
    blocks=public_blocks(tools)
    if not blocks:return []
    candidates=[]
    markers=list(KEYWORD.finditer(content))
    for hit in SEQ.finditer(content):
        tokens=tuple(SEGMENT.split(hit.group(1)))
        if "".join(tokens)!=LABELS or any(len(blocks.get(t,()))!=1 for t in tokens):
            continue
        # Require direct narrative selection near the candidate, NOT a row in a
        # 15-path cost table. A marker may be immediately before or after.
        line_start=content.rfind("\n",0,hit.start())+1
        line_end=content.find("\n",hit.end())
        if line_end<0:line_end=len(content)
        line=content[line_start:line_end]
        if line.lstrip().startswith("|"):continue
        distance=min((min(abs(m.start()-hit.start()),abs(m.end()-hit.end()))
                      for m in markers),default=10**9)
        if distance>140:continue
        full=tuple(blocks[t][0] for t in tokens)
        candidates.append((hit.start(),full,content[max(0,hit.start()-115):min(len(content),hit.end()+95)]))
    # Exact explicitly named tool list following a selection headline.
    for marker in markers:
        end=content.find("\n\n",marker.start())
        if end<0:end=len(content)
        excerpt=content[marker.start():min(end,marker.start()+330)]
        names=[x.group(1) for x in BACKTICK.finditer(excerpt)
               if x.group(1) in tools]
        if len(names)<2:continue
        # Only use consecutive full-plan names explicitly present in that prose;
        # never append a guessed "obvious" final tool.
        candidates.append((marker.start(),tuple(names),excerpt))
    return candidates


def recover_pre_event_commitment(
    first_assistant_content: str,
    old_tools: Mapping[str,ToolSpec],
    actual_pre_event_tool_names: Sequence[str],
    actual_current_state: frozenset[str],
    public_goal: frozenset[str],
) -> Commitment:
    if not isinstance(first_assistant_content,str) or not first_assistant_content.strip():
        return Commitment("NO_EXPLICIT_TEXT","".split(),(),"","pre_event_assistant",0)
    prefix=tuple(actual_pre_event_tool_names)
    matches=[]
    for pos,full,evidence in _candidate_paths(first_assistant_content,old_tools):
        if len(full)<len(prefix) or full[:len(prefix)]!=prefix:
            continue
        remainder=full[len(prefix):]
        endpoint=simulate(actual_current_state,remainder,old_tools)
        if endpoint is None or not public_goal<=endpoint:continue
        matches.append((pos,full,remainder,evidence))
    # Favor latest explicit narrative decision, but reject conflicting plans
    # rather than converting the *shortest* public path into a fake commitment.
    unique={p for _,p,_,_ in matches}
    if len(unique)!=1:
        status="UNPARSEABLE_OR_AMBIGUOUS" if len(unique)!=0 else "NO_VALID_COMMITTED_PATH"
        return Commitment(status,(),(),"","pre_event_assistant",len(unique))
    pos,full,remaining,ev=max(matches,key=lambda x:x[0])
    return Commitment("VALID_PRE_EVENT_COMMITMENT",full,remaining,ev[:350],
                      "original_agent_first_assistant_text_before_dynamic_event",
                      len(unique))
