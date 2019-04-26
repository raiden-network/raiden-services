# Routing feedback design

* Status: proposed
* Deciders: Dominik, Karl, Konrad, Paul
* Date: 2019-04-26

## Context and Problem Statement

The PFS receives information about the payment network from different sources (topology information from the chain, capacity information from nodes, node presence from Matrix), but currently doesn't receive feedback on whether or not the proposed routes worked for the initiator of the payment.

There are three goal for such a feedback mechanism:
1. Failure detection
2. Quality of service (of the PFS)
3. Routing improvements

## Decision Drivers

* Privacy for nodes
* Behavior with cheating nodes
* Usable feedback for PFS

## Considered Options

1. A solution where each participant sends proof (probably a balance proof) for a transfer to the PFS.
2. A solution where the initiator includes non-working routes in a subsequent request to the PFS.
3. A solution where the initiator sends feedback about (non)successful routes to the PFS. The acceptance of feedback is bound to the lifetime of a token received when requesting a route.

## Decision Outcome

Chosen option: "Option 3", because it allows for nodes to disable route feedback for greater privacy than option 1 and also provides feedback about working routes (in comparison to option 2).

### Positive Consequences

* PFS receives positive and negative feedback about routes it proposes
* Feedback is bound to a token that is only received when requesting a route. So misusage has a financial disadvantage.

### Negative Consequences

* Feedback that nodes provide can not be verified and shouldn't be trusted
* Nodes can not explicitly exclude certain routes when requesting routes from PFS
