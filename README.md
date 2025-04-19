# Experiments with the Beluga planning domain

This repository is dedicated to experiments on the [**Beluga**](https://github.com/TUPLES-Trustworthy-AI/Beluga-AI-Challenge) planning domain, using the [**Unified Planning (UP)**](https://unified-planning.readthedocs.io/en/latest/) library and [**Aries**](https://github.com/plaans/aries/blob/master/planning/unified/plugin/README.md) planning engine. At the moment of writing, the versions of UP and Aries that are used are in-development versions, not yet part of their main branches.

Three types of high-level tasks were investigated in this repository:

- **Planning**: Given 1. a specification of the Beluga problem and 2. a set of properties, **compute a (valid) action plan** achieving them. Integrated to the [IPEXCO platform](https://github.com/r-eifler/IPEXCO-frontend/tree/dev/beluga_demonstrator) via the following [web service](https://github.com/nrealus/ipexco-planner-service-beluga-up-aries).

- **Explaining**: Given 1. a specification of the Beluga problem and 2. a set of properties, such that they (problem and properties together) are infeasible, **compute minimal unsatisfiable subsets (MUSes) and minimal correction subsets (MCSes)** of these properties. Integrated to the IPEXCO platform via the following [web service](https://github.com/nrealus/ipexco-explainer-service-beluga-up-aries).

- **Property checking**: Given 1. a specification of the Beluga problem, 2. a set of properties, and 3. a (valid) action plan for that problem, **determine which of the properties are satisfied in the plan**. Note that this is implemented as completely independent of the planning and explaining. Clearly, this task is more secondary compared to the planning and explaining tasks. Integrated to the IPEXCO platform via the following [web service](https://github.com/nrealus/ipexco-property-checker-service-beluga-domdep).

## Setup / Usage

TODO

## The Beluga Domain

TODO

### Base Problem Specification

TODO

### Properties Specification

TODO

List of considered / supported properties:
- TODO

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

TODO

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