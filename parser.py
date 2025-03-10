from dataclasses import dataclass
from types import SimpleNamespace

import json

@dataclass 
class JigType:
    name: str
    size_empty: int
    size_loaded: int

@dataclass
class Rack:
    name: str
    size: int
    jigs: list[str]

@dataclass
class Jig:
    name: str
    type: str
    empty: bool

@dataclass
class ProductionLine:
    name: str
    schedule: list[str]

@dataclass
class Flight:
    name: str
    incoming: list[str]  # jigs
    outgoing: list[str]  # jig types

@dataclass
class BelugaProblemDef:
    trailers_beluga: list[str]
    trailers_factory: list[str]
    hangars: list[str]
    jig_types: list[JigType]
    racks: list[Rack]
    jigs: list[Jig]
    production_lines: list[ProductionLine]
    flights: list[Flight]

    def get_jig_type(self, name: str) -> JigType:
        return next(x for x in self.jig_types if x.name == name)

    def get_jig(self, name: str) -> Jig:
        return next(x for x in self.jigs if x.name == name)

@dataclass 
class BelugaPlanAction:
    name: str
    params: dict[str, str]

class BelugaPlanDef(list[BelugaPlanAction]):
    pass

def parse_problem_and_plan(filename: str) -> tuple[BelugaProblemDef, BelugaPlanDef | None]:
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    pb_def = _parse_problem(d.instance)
    plan_def = _parse_plan(d.plan) if hasattr(d, 'plan') and d.plan != ['UNSAT'] else None
    return (pb_def, plan_def)

def parse_problem(filename: str) -> BelugaProblemDef:
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    pb_def = _parse_problem(d.instance)
    return pb_def

def parse_plan(filename: str) -> list[BelugaPlanAction] | None:
    with open(filename) as f:
        d = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
    plan_def = _parse_plan(d.plan) if hasattr(d, 'plan') and d.plan != ['UNSAT'] else None
    return plan_def

def _parse_problem(d) -> BelugaProblemDef:
    pb_def = BelugaProblemDef(
        trailers_beluga=[t.name for t in d.trailers_beluga],
        trailers_factory=[t.name for t in d.trailers_factory],
        hangars=[h for h in d.hangars],
        jig_types=[JigType(jt.name, jt.size_empty, jt.size_loaded) for jt in vars(d.jig_types).values()],
        racks=[Rack(r.name, r.size, r.jigs) for r in d.racks],
        jigs=[Jig(r.name, r.type, r.empty) for r in vars(d.jigs).values()],
        production_lines=[ProductionLine(r.name, r.schedule) for r in d.production_lines],
        flights=[Flight(r.name, r.incoming, r.outgoing) for r in d.flights],
    )
    return pb_def

def _parse_plan(d_plan) -> BelugaPlanDef:
    plan_def = BelugaPlanDef()
    for a in d_plan:
        name = a.name
        params = { k:v for (k,v) in vars(a).items() if k != 'name' }
        plan_def += [BelugaPlanAction(name, params)]
    return plan_def

if __name__ == "__main__":
    filename = 'instances/example_sat_questions116.json'
    (pb_def, plan_def) = parse_problem_and_plan(filename)
    print("---- Parsed problem ----")
    print(pb_def)
    print("---- Parsed plan ----")
    print(plan_def)