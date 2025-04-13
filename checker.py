from parser import *

# vvv NOTE vvv !!!! Independent of model / planner !!!!

def check_plan_properties(
    properties: dict[PropId, dict[str, str]],
    plan_def: BelugaPlanDef,
    flights_in_order: list[str],
    jig_types: dict[str, str],
    racks_initial_jigs: dict[str, list[str]],
    racks_size: dict[str, int],
) -> list[str]:

    props_satisfied: dict[str, bool] = {}

    # addressed / checkable properties:
    #
    # [V] unload_beluga:
    # [V] load_beluga:
    # [V] deliver_to_production_line:
    # [V] rack_always_empty
    # [V] at_least_one_rack_always_empty
    # [V] jig_always_placed_on_rack_size_leq
    # [V] num_swaps_used_leq
    # [V] jig_never_on_rack
    # [V] jig_only_if_ever_on_rack
    # [V] jig_to_production_line_order
    # [V] jig_to_rack_order
    # [V] jig_to_production_line_before_flight

    props_unload_beluga: dict[tuple[str, str, int], str] = {}
    props_load_beluga: dict[tuple[str, str, int], str] = {}
    props_deliver_to_production_line: dict[tuple[str, str, int], str] = {}
    props_rack_always_empty: dict[str, str] = {}
    prop_at_least_one_rack_always_empty: str = ""
    props_jig_always_placed_on_rack_size_leq: dict[tuple[str, int], str] = {}
    props_num_swaps_used_leq: dict[int, str] = {}
    props_jig_never_on_rack: dict[tuple[str, str], str] = {}
    props_jig_only_if_ever_on_rack: dict[tuple[str, str], str] = {}
    props_jig_to_production_line_order: dict[tuple[str, str, str, str], str] = {}
    props_jig_to_rack_order: dict[tuple[str, str, str, str], str] = {}
    props_jig_to_production_line_before_flight: dict[tuple[str, str, str], str] = {}

    for (prop_id, prop_name_and_params) in properties.items():
        prop_name = prop_name_and_params['name']
        prop_params = prop_name_and_params['parameters']

        if prop_name == "unload_beluga":
            j, b, ji = prop_params[0], prop_params[1], int(prop_params[2])
            props_unload_beluga[(j, b, ji)] = prop_id

        elif prop_name == "load_beluga":
            j, b, ji = prop_params[0], prop_params[1], int(prop_params[2])
            props_load_beluga[(j, b, ji)] = prop_id

        elif prop_name == "deliver_to_production_line":
            j, pl, pli = prop_params[0], prop_params[1], int(prop_params[2])
            props_deliver_to_production_line[(j, pl, pli)] = prop_id

        elif prop_name == "rack_always_empty":
            r = prop_params[0]
            props_rack_always_empty[r] = prop_id

        elif prop_name == "at_least_one_rack_always_empty":
            prop_at_least_one_rack_always_empty = prop_id

        elif prop_name == "jig_always_placed_on_rack_size_leq":
            j, rs = prop_params[0], int(prop_params[1])
            props_jig_always_placed_on_rack_size_leq[(j, rs)] = prop_id

        elif prop_name == "num_swaps_used_leq":
            ns = int(prop_params[0])
            props_num_swaps_used_leq[ns] = prop_id

        elif prop_name == "jig_never_on_rack":
            j, r = prop_params[0], prop_params[1]
            props_jig_never_on_rack[(j, r)] = prop_id

        elif prop_name == "jig_only_if_ever_on_rack":
            j, r = prop_params[0], prop_params[1]
            props_jig_only_if_ever_on_rack[(j, r)] = prop_id

        elif prop_name == "jig_to_production_line_order":
            j1, pl1, j2, pl2 = prop_params[0], prop_params[1], prop_params[2], prop_params[3]
            props_jig_to_production_line_order[(j1, pl1, j2, pl2)] = prop_id

        elif prop_name == "jig_to_rack_order":
            j1, r1, j2, r2 = prop_params[0], prop_params[1], prop_params[2], prop_params[3]
            props_jig_to_rack_order[(j1, r1, j2, r2)] = prop_id

        elif prop_name == "jig_to_production_line_before_flight":
            j, pl, b = prop_params[0], prop_params[1], prop_params[2],
            props_jig_to_production_line_before_flight[(j, pl, b)] = prop_id

        else:
            assert False, "unknown property name {}".format(prop_name)

    racks_thought_empty = set(racks_initial_jigs.keys())
    racks_used_to_put_jig: dict[str, set[str]] = {}

    for r, jigs_list in racks_initial_jigs.items():
        if len(jigs_list) > 0:
            if r in props_rack_always_empty:
                props_satisfied[props_rack_always_empty[r]] = False
            for j in jigs_list:
                if (j, r) in props_jig_never_on_rack:
                    props_satisfied[props_jig_never_on_rack[(j,r)]] = False
                racks_used_to_put_jig.setdefault(j, set()).add(r)
                racks_thought_empty.discard(r)

    unloads_encountered: dict[str, int] = {}    # key: beluga / flight name, value: number of unloads from beluga
    loads_encountered: dict[str, int] = {}      # key: beluga / flight name, value: number of loads to beluga
    delivers_encountered: dict[str, int] = {}   # key: production line name, value: number of jigs delivered to it
    switches_to_next_flight_encountered: set[str] = set()   # values: beluga / flight name

    jigs_delivered_to_pl: dict[str, set[str]] = {}
    
    swaps_picks_and_puts: dict[tuple[str, str, str], int] = {}

    for act in plan_def:

        if act.name == "unload_beluga":
            j = act.params['j']
            b = act.params['b']
            ji = unloads_encountered.setdefault(b, 0)

            prop_id = props_unload_beluga.get((j, b, ji), None)
            if prop_id is not None:
                props_satisfied[prop_id] = True

            unloads_encountered[b] += 1

        elif act.name == "load_beluga":
            j = act.params['j']
            b = act.params['b']
            ji = loads_encountered.setdefault(b, 0)

            prop_id = props_load_beluga.get((j, b, ji), None)
            if prop_id is not None:
                props_satisfied[prop_id] = True

            prop_id = props_load_beluga.get((jig_types[j], b, ji), None)
            if prop_id is not None:
                props_satisfied[prop_id] = True

            loads_encountered[b] += 1

        elif act.name == "put_down_rack":
            j, r, t, s = act.params['j'], act.params['r'], act.params['t'], act.params['s']
            if r in props_rack_always_empty:
                props_satisfied[props_rack_always_empty[r]] = False
            if (j,r) in props_satisfied:
                props_satisfied[props_jig_never_on_rack[(j,r)]] = False
            racks_thought_empty.discard(r)
            racks_used_to_put_jig.setdefault(j, set()).add(r)

            for ((j1, r1, j2, r2), prop_id) in props_jig_to_rack_order.items():
                if j == j1 and r == r1:
                    props_satisfied[prop_id] = (j2 not in racks_used_to_put_jig or r2 not in racks_used_to_put_jig[j2])
                if j == j2 and r == r2:
                    if (j1 in racks_used_to_put_jig and r1 in racks_used_to_put_jig[r1]):
                        assert props_satisfied[prop_id]
                    else:
                        props_satisfied[prop_id] = False
            
            if (j, t, s) in swaps_picks_and_puts:
                if swaps_picks_and_puts[(j, t, s)]%2 == 0:
                    swaps_picks_and_puts[(j, t, s)] += 1

        elif act.name == "pick_up_rack":
            j, r, t, s = act.params['j'], act.params['r'], act.params['t'], act.params['s']
            if (j, t, s) in swaps_picks_and_puts:
                assert swaps_picks_and_puts[(j, t, s)]%2 != 0
                swaps_picks_and_puts[(j, t, s)] += 1
            else:
                swaps_picks_and_puts[(j, t, s)] = 0

        elif act.name == "deliver_to_hangar":
            j = act.params['j']
            pl = act.params['pl']
            pli = delivers_encountered.setdefault(pl, 0)

            prop_id = props_deliver_to_production_line.get((j, pl, pli), None)
            if prop_id is not None:
                props_satisfied[prop_id] = True

            delivers_encountered[pl] += 1

            jigs_delivered_to_pl.setdefault(pl, set()).add(j)

            for ((j1, pl1, j2, pl2), prop_id) in props_jig_to_production_line_order.items():
                if j == j1 and pl == pl1:
                    props_satisfied[prop_id] = (pl2 not in jigs_delivered_to_pl or j2 not in jigs_delivered_to_pl[pl2])
                if j == j2 and pl == pl2:
                    if (pl1 in jigs_delivered_to_pl and j1 in jigs_delivered_to_pl[pl1]):
                        assert props_satisfied[prop_id]
                    else:
                        props_satisfied[prop_id] = False

            for (jj, pll, fli) in props_jig_to_production_line_before_flight:
                if jj == j and pll == pl:
                    prop_id = props_jig_to_production_line_before_flight[(j, pl, fli)]
                    props_satisfied[prop_id] = fli not in switches_to_next_flight_encountered

        elif act.name == "get_from_hangar":
            pass

        elif act.name == "switch_to_next_beluga":
            # switches_to_next_flight_encountered.add(beluga_index_from_name(act.params['b']))
            switches_to_next_flight_encountered.add(flights_in_order[len(switches_to_next_flight_encountered) + 1])

        else:
            assert False, "unknown action name {}".format(act.name)

    num_swaps_in_plan = sum(int(n / 2) for n in swaps_picks_and_puts.values())
    assert num_swaps_in_plan == int(num_swaps_in_plan)

    assert all(prop_id not in props_satisfied or props_satisfied[prop_id] == True for prop_id in props_unload_beluga.values())
    for prop_id in props_unload_beluga.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = False

    assert all(prop_id not in props_satisfied or props_satisfied[prop_id] == True for prop_id in props_load_beluga.values())
    for prop_id in props_load_beluga.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = False

    assert all(prop_id not in props_satisfied or props_satisfied[prop_id] == True for prop_id in props_deliver_to_production_line.values())
    for prop_id in props_deliver_to_production_line.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = False

    assert all(prop_id not in props_satisfied or props_satisfied[prop_id] == False for prop_id in props_rack_always_empty.values())
    for prop_id in props_rack_always_empty.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = True

    assert all(prop_id not in props_satisfied or props_satisfied[prop_id] == False for prop_id in props_jig_never_on_rack.values())
    for prop_id in props_jig_never_on_rack.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = True

    props_satisfied[prop_at_least_one_rack_always_empty] = len(racks_thought_empty) > 0

    for ((j, r), prop_id) in props_jig_only_if_ever_on_rack.items():
        props_satisfied[prop_id] = (j not in racks_used_to_put_jig or len(racks_used_to_put_jig[j]) <= 1)

    for ((j, rs), prop_id) in props_jig_always_placed_on_rack_size_leq.items():
        props_satisfied[prop_id] = (
            j not in racks_used_to_put_jig
            or max(racks_size[r] for r in racks_used_to_put_jig[j]) <= rs
        )

    for ns, prop_id in props_num_swaps_used_leq.items():
        props_satisfied[prop_id] = num_swaps_in_plan <= ns

    for prop_id in props_jig_to_production_line_order.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = False

    for prop_id in props_jig_to_rack_order.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = False

    for prop_id in props_jig_to_production_line_before_flight.values():
        if prop_id not in props_satisfied:
            props_satisfied[prop_id] = False

    return [prop for prop, prop_sat in props_satisfied.items() if prop_sat]
