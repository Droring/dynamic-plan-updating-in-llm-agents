"""Offline screening invariants: historical overlap, template leakage and splits."""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"research/costbench_method_studies/candidate_source_registry/build_registry.py"
spec=importlib.util.spec_from_file_location("candidate_registry",PATH)
reg=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reg)


def record(qid,cat,style):
    return {
        "query_id":f"<Query{qid:05d}>",
        "task":cat,
        "preferences":{"style":style,"category":"example"},
        "is_valid":1
    }


class CandidateRegistryScreeningTests(unittest.TestCase):
    def test_canonical_preference_hash_is_order_independent(self):
        a=record(1,"dining","a")
        b=record(2,"dining","a")
        b["preferences"]={"category":"example","style":"a"}
        self.assertEqual(reg.preference_signature(a),reg.preference_signature(b))
        self.assertNotEqual(reg.digest(a),reg.digest(b))

    def test_stratification_never_doubles_a_structural_preference(self):
        source=[]
        cats=reg.CATEGORIES
        for cat in cats:
            for i in range(4):
                source.append(record(len(source)+100,cat,str(i)))
            source.append(record(len(source)+100,cat,"0"))
        quotas={cat:{"development":1,"validation":1,"locked_test":1} for cat in cats}
        selected,report=reg.create(source,{"Query00001"}|{f"Query{x:05d}" for x in range(2,50)},quotas)
        self.assertEqual(len(selected),15)
        self.assertEqual(len({r["query_id"] for r in selected}),15)
        self.assertEqual(len({(r["category"],r["preference_sha256"]) for r in selected}),15)
        self.assertEqual(report["selected_by_split"],{
            "development":5,"validation":5,"locked_test":5
        })
        again,_=reg.create(list(reversed(source)),{"Query00001"}|{f"Query{x:05d}" for x in range(2,50)},quotas)
        self.assertEqual(selected,again)

    def test_removes_previously_seen_preference_even_under_new_query_id(self):
        source=[record(1,"dining","historical"),record(99,"dining","historical"),
                record(100,"dining","new")]+[record(200+i,c,str(i))
                                           for i,c in enumerate(reg.CATEGORIES) if c!="dining"]
        quotas={cat:{"development":1,"validation":0,"locked_test":0} for cat in reg.CATEGORIES}
        selected,report=reg.create(source,{f"Query{x:05d}" for x in range(1,46)},quotas)
        self.assertFalse(any(r["query_id"]=="Query00099" for r in selected))
        self.assertEqual([r["query_id"] for r in selected if r["category"]=="dining"],["Query00100"])

    def test_rejects_overquota_unduplicated_pool(self):
        source=[record(100+i,c,str(i)) for i,c in enumerate(reg.CATEGORIES)]
        quotas={cat:{"development":1,"validation":1,"locked_test":0} for cat in reg.CATEGORIES}
        with self.assertRaisesRegex(ValueError,"only 1 novel"):
            reg.create(source,{f"Query{x:05d}" for x in range(1,46)},quotas)

    def test_requires_complete_primary_task_exclusion_set(self):
        with self.assertRaisesRegex(ValueError,"incomplete"):
            reg.create([],{ "Query00001" },reg.QUOTAS)


if __name__=="__main__":
    unittest.main()
