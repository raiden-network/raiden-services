# Mediation Fees calculation and message format

* Status: proposed
* Deciders: Augusto, Dominik, Karl, Paul
* Date: 2019-05-07

## Context and Problem Statement

Mediating nodes demand fees for their mediation services. These fees should not only incentivize running a Raiden node, but also help balancing the network. This can be done by reducing the mediation fees for payments which leave channels in a more balanced state than before the payment (possibly even to a negative fee).

## Decision Drivers

* Balancing the network should be incentivized
* Raiden nodes will act selfishly
* Mediation fees should be flexible enough to accommodate arbitrary business models for parties operation Raiden nodes.

## Considered Options

1. A fixed fee + a proportional fee (flat + prop * amount)
2. A fixed fee + a proportional fee + an imbalance fee based on a fixed imbalance measure
3. A fixed fee + a proportional fee + submitting points of a function describing the imbalance fee
4. Submitting points of a single function (dependent on the payment amount) which includes all fees

## Decision Outcome

Chosen option: **Option 3**, but with some important additions (see below).

* Option 1 would be sufficient for the short very term, but does not incentivize rebalancing.
* Option 2 does not work because no objective balance measure could be found that is valid across all business models / user interests.
* Option 4 would work but require sending a changed fee schedule after every transfer or mediation. Since this information is broadcast, that's a non-negligible amount of traffic.

### Positive Consequences

* Adaptable to different business models
* Both in- and outgoing channels can be rebalanced
* Fully exhausting a channel can be punished more strongly than just moving into the wrong direction
* Fee schedules only have to be changed when the node's strategy changes or the on-chain capacity changes via `deposit` or `withdraw`
* Fee components are optional. A node only using flat fees does not have to submit complicated functions.

### Negative Consequences

* Comparatively complex

## Detailed analysis

One important detail is that fees are not only calculated for the channel over which the mediation payment is sent, but also for the channel over which the payment is received. Without this, a node could not incentivize receiving through a certain channel, which is just as important for rebalancing as sending through the right channel (see the next section for a detailed example). So the total mediation fee for a node is

`MF_total = MF_in_channel + MF_out_channel`

where for each channel

`MF_channel = flat_fee + proportional_fee * amount + IP(C_after) - IP(C_before)`

where `IP` is the "Imbalance Penalty" function and `C_before/after` are the channel capacities before and after the payment. The channel capacity is the node's free capacity as reported to the PFS with the PFSCapacityUpdate messages.

The IP function is a function that describes how much a node is willing to pay (in absolute values/wad) to move away from an undesirable channel capacity. If a node prefers to have a channel capacity of 5 while the total capacity of that channel is 10 (so that it could mediate up to 5 tokens in both directions) the IP function might look like

```
IP
^
|X                      X
|X                      X
| X                    X
| X                    X
|  X                  X
|   X                X|
|    X              X |
|     X            X  |dIP = IP(C_after) - IP(C_before)
|      XX        XX   |
|        XX    XX----->
|          XXXX  amount
+---------------+-----+--> Capacity
                6     9
```

If the node currently has a capacity of 6 and is asked to mediate a payment of 3 tokens coming from this channel, it will get into the less desired position of 9 capacity. To compensate for this, it will demand an imbalance fee of `dIP = IP(C_after) - IP(C_before)`. If the situation was reversed and the capacity would go from 9 to 6, the absolute value would be the same, but this time it would be negative and thus incentivize moving towards the preferred state. By viewing the channel balances in this way, the imbalance fee is a zero sum game in the long term. All tokens which are earned by going into a bad state will be spent for moving into a good state again, later.

Only mediating nodes demand mediation fees. The initiator and target could theoretically benefit if their IP was taken into account during routing, but this aspect is left out for now to avoid additional complexity.

### Why apply fees for the incoming channel?

At a first glance, calculating fees for the incoming channel does not make any sense, since the mediating node itself only sends money over the outgoing channel. But taking part in the mediation will modify both channels, so the choice of the incoming channel is relevant to the mediating node. To demonstrate that you can't reliably influence the balancing of your channels if you only apply fees to the outgoing channel, let's look at one example:

A mediating node has three channels. The channel to C is nearly exhausted, while the other channels have a free capacity of 9 tokens left (of 10 tokens which are deposited in that channel). This node wants to have
a similar amount of free capacity for all channels, so that it has more mediation opportunities. To achieve this, it must receive tokens over channel C.

++: desirable transfer (point of view of the mediating node)<br/>
--: undesirable transfer<br/>

| from\to | A   | B   | C   |
| ---     | --- | --- | --- |
| A 1/10  |     | -   | --  |
| B 1/10  | -   |     | --  |
| C 9/10  | ++  | ++  |     |

To incentivize rebalancing, the node could reduce fees for channels A and B to a negative value. But this might lead to mediating transfers A&rarr;B and B&rarr;A, both of which are not intended! The problem is visible in the table above: by changing fees for outgoing channels, you can only incentivize all transfers in a single column. But all desirable transfers are in a single row, meaning the we must incentivize usage of an incoming channel.

### Economic Aspects

In this model, the mediation fees are split into three parts:

1. The *flat fee*. This is meant to represent the base cost of handling a payment, so that even small payment amounts can be profitable to mediate.
2. The *proportional fee*. Large payments lock up tokens while the payment is in progress. To compensate this, the operator should receive larger fees for large payments
3. The *imbalance fee*. The direction of payments and the specific channels used are relevant to the operator. Some payments might exhaust the channel capacity and prevent future profitable mediations while others could facilitate future mediations. Due to this, the operator should be compensated (or willing to compensate the initiator, respectively). As a side effect, the whole network will get into a more balanced state.

These three parts roughly map to operating costs, capital costs and opportunity costs.

The flexible shape of the IP function allows to encode many different operator intentions. If I use a channel solely to pay, having more free capacity is always desired and any capacity gained by mediating in the reverse direction is welcome. In that case, my IP function could look like

```
IP
^
|X
|X
| X
|  X
|   XX
|     XX
|       XX
|         XX
|           XX
|             XXX
|                XXX
+------------------------> Capacity
```

If I only expect small payments, I mainly want to stay away from totally exhausting the channel in either direction, but the exact capacity does not matter. So the IP function would have a large, mostly flat part in the middle:

```
IP
^
|X                     X
|X                     X
|X                     X
|X                     X
| X                   X
| X                   X
| X                   X
|  X                 X
|  X                 X
|   X               X
|    XXXXXXXXXXXXXXX
+------------------------> Capacity
```

### Message Format

The three mediation fee components are sent separately. Each component is optional and will be assumed to be zero (no cost) if not included in the message. If other components are needed in the future, they could be added the same fashion.

The message format still has to be defined in detail, but the payload will look roughly like this:

```json
{
    'flat': 10,
    // we have to deal with float values anyway, due to the interpolation
    'proportional': 100,  // factor of transfer amount in parts-per-million
    'imbalance_penalty': [
        [0, 1000],
        [1000, 500],
        [3000, 0],
        [5300, 600],
        [6000, 1000],
    ],
}
```

The imbalance penalty functions is sent as a list of function points which are interpolated linearly to build the function. Values outside of the defined range will be considered as impossible to mediate.
