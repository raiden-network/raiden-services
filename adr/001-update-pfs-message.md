# `PFSCapacityUpdate` message design

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

1. A solution where each participant broadcasts the signed, unblinded balance proofs received from the other participant to the PFS' via the global matrix room.
2. A solution where the message contains the capacities of both channel sides and both participants broadcast them to the PFS' via the global matrix room. Conflicting statements will be resolved by taking the minima of the provided values.

## Decision Outcome

Chosen option: "Option 2", because it allows for more privacy while offering only smaller safe capacities in the worst case. The honest node always submits the real capacity, then the PFS will use ``min(real_capacity, dishonest_capacity)``. So the PFS will always assume a capacity smaller or equal to the real capacity. There's no incentive to decrease the capacity of a channel in either direction, so there's no incentive to lie.

### Positive Consequences

* Message includes only capacity, so the balance proofs stay private.
* Privacy is possible because of the possibility to broadcast only at certain thresholds and not on every balance proof change.

### Negative Consequences

* In case where one of the channel participants is malicious, the available capacities will be lower than in option 1.

## Detailed analysis

To look at the feasibility of both designs one needs to look at three different scenarios for the channel participants:
1. Both participants are well behaving.
2. Both participants are malicious.
3. One of the participants is malicious.

It's also important to make clear that the only incentive for malicious behaviour is to announce a bigger channel capacity than the available capacity, in order to get more mediated payments routed by the PFS'.

### Case 1: Two well behaving participants

In this case the PFS learns about the correct channel capacities in both message designs.

### Case 2: Two malicious participants

In this case the PFS can not do anything to find out about the malicious behaviour. However, we assume that not all participants in the network are malicious.
Therefore, a channel must exit where case 3 is active.

### Case 3: One malicious participant

Thesis: Neither in Option 1 nor in Option 2 there is an economic incentive for providing an incorrect message.

Definitions: *H* is honest, *M* is malicious, *D_H* is the deposit of *H*, *T_H* is the transferred amount of *H*, *C_H* represents the capacity of *H*'s channel side (variables for *M* are equally defined)

Looking at Option 1 - broadcasting balance proofs - *B* never has an incentive to send an older balance proof, as the transferred amount is monotonically increasing. That means for every balance proof older than the latest, *T_A* would be smaller and therefore *C_B* would be smaller as well. So *B* would artificially decrease its own capacity which does not lead to any economical incentive.

|   | D_H | D_M | T_H | T_M | C_H | C_M |
|---|----:|----:|----:|----:|----:|----:|
| 1 | 10  | 3   | 0   | 0   | 10  | 3   |
| 2 | 10  | 3   | 10  | 0   | 0   | 13  |
| 3 | 10  | 3   | 10  | 3   | 3   | 10  |
| 4 | 10  | 3   | 10  | 13  | 13  | 0   |
| 5 | 10  | 3   | 12  | 13  | 11  | 2   |

___

Looking at Option 2 - broadcasting the channel capacity - *B* never has an incentive to cheat when capacity is calculated as `min(C_A, C_B)`.

Three cases for the capacity based message when *M*  and *H* have capacities of 15 and 0 respectively.

Case 1: Honest node has it all. The channel is assumed capacityless, when *M* cheats with any value. This is not matching the intention from the malicious node. *M* could simply stop routing over *H* to achieve the same result.

|   | C_H | C_M |
|---|----:|----:|
| H |  15 |   0 |
| M |   0 |  15 |
|   |     |     |
|PFS|   0 |   0 |

Case 2: Malicious node has it all. No economic incentive for *M*. If *M* wants to provide less capacity for mediating, it can simply send a smaller value or increase the fees.

|   | C_H | C_M |
|---|----:|----:|
| H |   0 |  15 |
| M |   0 |  15 |
|   |     |     |
|PFS|   0 |  15 |

Case 3: Some distribution between *M* and *H*. *M* could cheat with *d* (delta) in either direction (*M* and *M'*). Sending *M* would lead to a lower *C_M*, which would give no economic incentive. Sending *M'* would lead to the same *C_M* as sending the correct value (no economic incentive given either) and again, artificially lowering *C_H* doesn't lead to any economic incentive.

|    | C_H | C_M |
|----|----:|----:|
| H  |   7 |   8 |
| M  | 7+d | 8-d |
| M' | 7-d | 8+d |
|    |     |     |
|PFS |   7 | 8-d |
|PFS'| 7-d |   8 |
