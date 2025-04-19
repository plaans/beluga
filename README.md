**WARNING**: The code in this repository could very well be quite unpolished !

# Experiments with the Beluga planning domain

This repository is dedicated to experiments on the [**Beluga**](https://github.com/TUPLES-Trustworthy-AI/Beluga-AI-Challenge) planning domain, using the [**Unified Planning (UP)**](https://unified-planning.readthedocs.io/en/latest/) library and [**Aries**](https://github.com/plaans/aries/blob/master/planning/unified/plugin/README.md) planning engine. At the moment of writing, the versions of UP and Aries that are used are in-development versions, not yet part of their main branches.

Three types of high-level tasks were investigated in this repository:

- **Planning**: Given 1. a specification of the Beluga problem and 2. a set of properties, **compute a (valid) action plan** achieving them. Integrated to the [IPEXCO platform](https://github.com/r-eifler/IPEXCO-frontend/tree/dev/beluga_demonstrator) via the following [web service](https://github.com/nrealus/ipexco-planner-service-beluga-up-aries).

- **Explaining**: Given 1. a specification of the Beluga problem and 2. a set of properties, such that they (problem and properties together) are infeasible, **compute minimal unsatisfiable subsets (MUSes) and minimal correction subsets (MCSes)** of these properties. Integrated to the IPEXCO platform via the following [web service](https://github.com/nrealus/ipexco-explainer-service-beluga-up-aries).

- **Property checking**: Given 1. a specification of the Beluga problem, 2. a set of properties, and 3. a (valid) action plan for that problem, **determine which of the properties are satisfied in the plan**. Note that this is implemented as completely independent of the planning and explaining. Clearly, this task is more secondary compared to the planning and explaining tasks. Integrated to the IPEXCO platform via the following [web service](https://github.com/nrealus/ipexco-property-checker-service-beluga-domdep).

## Setup / Usage

TODO

- **Planning**:
    ```
    TODO
    ```

- **Explaining**:
    ```
    TODO
    ```

- **Property checking**:
    ```
    TODO
    ```

## The Beluga Domain

TODO

### Base Problem Specification

TODO

#### Legacy format

TODO

### Properties Specification

Properties are specified in a JSON file containing a single list
whose entries represent properties and follow the `{ "name": "xxx", "params": {...} }` format.
An example entry could be the following: `{ "name": "unload_beluga", "params": { "j": "jig0001", "b": "beluga1", "i": 0 } }`.

List of considered / supported properties:

- `unload_beluga(j, b, i)`: represents jig `j` being the `i`-th one to be unloaded from beluga `b`.
- `load_beluga(j_or_jt, b, i)`: represents jig `j` being the `i`-th one to be loaded into beluga `b`.
- `deliver_to_production_line(j, pl, i)`: represents jig `j` being the `i`-th one to be delivered to production line `pl`.
    - **NOTE**: for `unload_beluga(j, b, i)`, `load_beluga(j, b, i)`, and `deliver_to_production_line(j, pl, i)`, the ordinal `i` indicates a "relative" position in an order. For example, if we to unload only two jigs from the same beluga at "positions" `i_1 = 2` and `i_2 = 4`, they will be treated as the first and second one respectively. As a corollary, if `i = 4` and there is only one jig, everything will be the same as with `i = 0`.

- `rack_always_empty(r)`: represents rack `r` never having a jig on itself (including initially).
- `at_least_one_rack_always_empty`: represents at least one rack never having a jig on itself (including initially).
- `jig_always_placed_on_rack_size_leq(j, sz)`: represents jig `j` never being okaced on rack of size strictly larger than `sz`.
- `num_swaps_used_leq(n)`: represents `n` jig swaps being used at most.
- `jig_never_on_rack(j, r)`: represents jig `j` never being placed on rack `r`.
- `jig_only_if_ever_on_rack(j, r)`: represents jig `j` being either never placed on a rack, or only on rack `r`.
- `jig_to_production_line_order(j1, pl1, j2, pl2)`: represents jig `j1` being delivered to production line `pl1` and `j2` being delivered to production_line `pl2`, in that order.
- `jig_to_rack_order(j1, r1, j2, r2)`: represents jig `j1` being placed on rack `r1` and `j2` being placed on rack `r2`, in that order.
- `jig_to_production_line_before_flight(j, pl, b)`: represents jig `j` being delivered to production line `pl`, before the arrival of beluga `b`.

## Property Checking

We cover the property checking task first, since it is very simple and independent from the planning and explaining tasks.

The property checking works by simply iterating through the given plan's actions, and, depending on their parameters and previous actions, marking the properties as (un)satisfied as soon as possible.
It is designed and implemented in a domain-dependent, *ad hoc* manner, relying on the specifics of the considered properties.

## Planning

We cast Beluga problems as optional scheduling problems.
This is equivalent to a (non-recursive) hierarchical task network (HTN) where tasks have two decomposition methods: one "concrete" method that bears the task's operational semantics, and another "noop" empty method that represents the task being left out of the solution plan.

This problem casting is well suited (but not absolutely required) for the "planning as constraint satisfaction" approach used by Aries with the CSP encoding presented in [[1]]().

#### A limitation on the number of swaps

However this comes at the cost of a limitation, namely that there is a *bounded* number of possible jig swaps (pick-up and put-down actions) allowed in the model.
However, if no solution is found for a given number of swaps, one could always consider a new model with a larger number of these available actions.
This limitation is briefly discussed sections 4.2 and 4.3 in [[2]]().

As such, we may be unable to prove the unsatisfiability of a problem instance in the most general case, when no assumptions are made on the maximal number of possible swaps.
This has a direct impact on the matter of explainability, as will be touched upon further below.

### Optional Scheduling Model

For every flight excluding the very first one, create a **non-optional** `switch_to_next_beluga` action.
Constrain all these `switch_to_next_beluga` actions to be one after the other.

For every incoming flight, and every concrete jig carried in it (processed in order):
- Add an optional `unload_beluga` *action* as well as an optional `put_down_rack` action (on the beluga side of the rack system), and constrain them to be ordered.
- Constrain the `unload_beluga` action to be between the previous (if it exists) and the next (if it exists) `switch_to_next_beluga` actions.
- Constrain the `unload_beluga` action to be after *all* previous `unload_beluga` actions.

NOTE: Since `unload_beluga` actions are optional, precedence constraints between two of them only hold when both are present.
As such, the precedence is not always transitive and isn't necessarily propagated to earlier actions, which why these precedences must be enforced for all pairs of `unload_beluga` actions.

For every outgoing flight, and every jig type *or concrete jig* that it must take (processed in order), the procedure is very similar to the one for `unload_beluga` actions, except that it uses `pick_up_rack` and `load_beluga` actions.

NOTE: `unload_beluga` and `load_beluga` actions for the same flight do not need to be ordered !

For every production line and every jig required by it (processed in order), the procedure is very similar to the one for `unload_beluga` and `load_beluga`, except it uses `pick_up_rack` and `deliver_to_hangar` actions. For each jig (and the same production line), the associated `deliver_to_hangar` is constrained to be after all previous ones.

In addition, optional `get_from_hangar` and `put_down_rack` actions are added for each jig that had to be delivered to a production line. There are no constraints to enforce between these `get_from_hangar` actions.

On top of that, for each jig initially placed on a trailer, an optional `put_down_rack` action is made available (for the appropriate side of the rack system, i.e. "beluga" or "production"). Also, for each jig initially located in hangar, optional `get_from_hangar` and `put_down_rack` actions are made available.

Finally, for a given number `N` representing the maximum number of jig swaps allowed, a pair of ordered `pick_up_rack` and `put_down_rack` actions are made available, with their `j` (jig) and `s` (side) parameters constrained to be equal.

There are some additional constraints -- both required and unrequired, but beneficial to prune the search space. However, we do not describe them for the sake of brevity.

## Explaining

Explanations are adressed by computing the MUSes and/or MCSes of an unsatisfiable set of desired properties. This approach to provide explanations planning / sequential decision making problems is rooted in [[4]]().

These property conflicts (MUSes and/or MCSes) are computed by applying a MUS/MCS enumeration algorithm (namely MARCO [[3]]()) on the CSP planning encoding mentioned above. The "soft constraints" on which the MARCO algorithm is run are simply the (positive) boolean literals reifying (FIXME representing ?) the properties in CSP model.
The version of MARCO used was implemented as an extension to (FIXME for?) the Aries solver.

## Discussion

TODO

## References

[[1] Godet, R., & Bit-Monnot, A. (2022, June). Chronicles for representing hierarchical planning problems with time. In ICAPS Hierarchical Planning Workshop (HPlan).](https://hal.science/hal-03690713/document)

[[2] Bit-Monnot, A. (2018). A constraint-based encoding for domain-independent temporal planning. In Principles and Practice of Constraint Programming: 24th International Conference, CP 2018, Lille, France, August 27-31, 2018, Proceedings 24 (pp. 30-46). Springer International Publishing.](https://laas.hal.science/hal-02931989v1/document)

[[3] Liffiton, M. H., Previti, A., Malik, A., & Marques-Silva, J. (2016). Fast, flexible MUS enumeration. Constraints, 21, 223-250.](https://drive.google.com/file/d/1CExi081SBDXvAZwUYEtHO5vF2sTH3qa4/view)

[[4] Eifler, R., Cashmore, M., Hoffmann, J., Magazzeni, D., & Steinmetz, M. (2020, April). A new approach to plan-space explanation: Analyzing plan-property dependencies in oversubscription planning. In Proceedings of the AAAI Conference on Artificial Intelligence (Vol. 34, No. 06, pp. 9818-9826).](http://fai.cs.uni-saarland.de/hoffmann/papers/aaai20a.pdf)