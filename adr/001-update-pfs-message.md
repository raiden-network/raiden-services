# `UpdatePFS` message design

* Status: accepted
* Deciders: Augusto, Dominik, Karl, Konrad, Paul
* Date: 2019-04-09

## Context and Problem Statement

The PFS requires information about the capacity of channels from Raiden nodes. How should this information be send to the PFs?

## Decision Drivers

* Channel capacities are computable
* Privacy for nodes
* Behaviour with cheating nodes

## Considered Options

1. A solution where each participant broadcasts the balance proofs received from the other participant to the PFS'.
2. A solution where the message contains the capacities of both channel sides and both participants broadcast them to the PFS'.

## Decision Outcome

Chosen option: "Option 2", because it allows for more privacy while offering only smaller safe capacities in the worst case.

### Positive Consequences

* Message incluides only capacity, so the balance proofs stay private
* Privacy is possible because only bigger changes in the capacity need to be broadcasted.

### Negative Consequences

* In the case where one of the channel participants is malicious, the available capacities are lower than in option 1.

## Detailed analysis

To look at the feasibility of both design one needs to look at three different scenarios for the channel participants:
1. Both participants are well behaving.
2. Both participants are malicious.
3. One of the participants is malicious.

### Case 1: Two well behaving participants

In this case the PFS learns about the correct channel capacities in both message designs.

### Case 2: Two malicious participants

In this case the PFS can not do anything to find out about the malicious behaviour. However, we assume that not all participants in the network are malicious.
Therefore there must exist a channel, where case 3 is active.

### Case 3: One malicious participant

This is the interesting case.

|   | D_A | D_B | T_A | T_B | C_A | C_B |
|---|----:|----:|----:|----:|----:|----:|
| 1 | 10  | 3   | 0   | 0   | 10  | 3   |
| 2 | 10  | 3   | 10  | 0   | 0   | 13  |
| 3 | 10  | 3   | 10  | 3   | 3   | 10  |
| 4 | 10  | 3   | 10  | 13  | 13  | 0   |
| 5 | 10  | 3   | 12  | 13  | 11  | 2   |

A is honest, B is malicious

TODO: Write how B never has an incentive to send an older balance proof, as the transferred amount is monotonically increasing.


Next: Three cases for the capacity based message. We see that the formula `min(c_A, c_B)` gives a useful output.


Case 1: Channel is assumed capacityless, not matching intention from malicious node

|   | C_H | C_M |
|---|----:|----:|
| H |  15 |   0 |
| M |   0 |  15 |
|   |     |     |
|PFS|   0 |   0 |

Case 2: Channel has to malicious node has lower capacity than in reality, not matching intention from malicious node

|   | C_H | C_M |
|---|----:|----:|
| H |   7 |   8 |
| M |   0 |  15 |
|   |     |     |
|PFS|   0 |   8 |

Case 3: Not actually malicious

|   | C_H | C_M |
|---|----:|----:|
| H |   0 |  15 |
| M |   0 |  15 |
|   |     |     |
|PFS|   0 |  15 |
