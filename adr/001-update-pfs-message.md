# `UpdatePFS` message design

* Status: accepted
* Deciders: Augusto, Dominik, Karl, Konrad, Paul
* Date: 2019-04-09

## Context and Problem Statement

The PFS requires information about the capacity and mediation fees of channels from Raiden nodes. This information must be passed on by the Raiden nodes. The design of the balance and fee updates must optimize for two contradicting paradigms

1. Accuracy of the global state from the PFS's perspective
2. Privacy of the Raiden nodes

The nodes can decide themselves whether to send balance and fee updates to the PFS to advertise their channel for mediating or not. 

## Decision Drivers

* Channel capacities are computable
* Privacy for nodes
* Behaviour with cheating nodes

## Considered Options

1. Option 1: A solution where each participant broadcasts the signed, clear balance proofs received from the other participant to the PFS' via the gloabl matrix room.
2. Option 2: A solution where the message contains the capacities of both channel sides and both participants broadcast them to the PFS' via the gloabl matrix room. Conflicting statements will be resolved by taking the mininma of the provided values.

## Decision Outcome

Chosen option: "Option 2", because it allows for more privacy while offering only smaller safe capacities in the worst case.

### Positive Consequences

* Message incluides only capacity, so the balance proofs stay private
* Privacy is possible because possibility to broadcast only at certain thresholds and not for every update

### Negative Consequences

* In case where one of the channel participants is malicious, the available capacities will be computed lower than in option 1.

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

Thesis: Neither in Option 1 nor in Option 2 there is a economic incentive providing an incorrect message.

Definitions: H is honest, M is malicious, H_A is deposit of H, T_H is the transferred amount of H, C_H represents the capacity of H's channel side (variables for M are equially defined)

Looking at Option 1 - broadcasting balance proofs - B never has an incentive to send an older balance proof, as the transferred amount is monotonically increasing. That means for every balance proof older than the latest, T_A would be smaller and therefore C_B as well. So B would artifically decrease her own capacity which does not lead to any economical incentive. 

|   | D_H | D_M | T_H | T_M | C_H | C_M |
|---|----:|----:|----:|----:|----:|----:|
| 1 | 10  | 3   | 0   | 0   | 10  | 3   |
| 2 | 10  | 3   | 10  | 0   | 0   | 13  |
| 3 | 10  | 3   | 10  | 3   | 3   | 10  |
| 4 | 10  | 3   | 10  | 13  | 13  | 0   |
| 5 | 10  | 3   | 12  | 13  | 11  | 2   |

___

Looking at Option 2 - broadcasting the channel capacity - B never has an incentive when `min(c_A, c_B)` is taken into account.

Three cases for the capacity based message when M has capacity of 15 and H 0.

Case 1: Honest node has it all. Channel is assumed capacityless, when M cheats with any value. No matching intention from malicious node. M could simply stop routing over H to achieve the same result.

|   | C_H | C_M |
|---|----:|----:|
| H |  15 |   0 |
| M |   0 |  15 |
|   |     |     |
|PFS|   0 |   0 |

Case 2: Malicious node has it all. No economic incentive for M. If M wants to provide less capacity for mediating, it can simply send a smaller value or higher the fees. 

|   | C_H | C_M |
|---|----:|----:|
| H |   0 |  15 |
| M |   0 |  15 |
|   |     |     |
|PFS|   0 |  15 |

Case 3: Some distribution between M and H. M could cheat with d (delta) in either direction (M and M'). Sending M would lead to less C_M, so no economic incentive. Sending M' would lead to the same C_M as sending the correct value (so no economic incentive) and again, artificially lowering C_H doesn't lead to any economic incentive.  

|    | C_H | C_M |
|----|----:|----:|
| H  |   7 |   8 |
| M  | 7+d | 8-d |
| M' | 7-d | 8+d |
|    |     |     |
|PFS |   7 | 8-d |
|PFS'| 7-d |   8 |


