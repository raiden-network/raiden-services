# Raiden Services

Supplemental services for the [Raiden Network](https://raiden.network/).

[![Build Status](https://travis-ci.com/raiden-network/raiden-services.svg?branch=master)](https://travis-ci.com/raiden-network/raiden-services)
[![Coverage](https://img.shields.io/codecov/c/github/raiden-network/raiden-services.svg?style=round)](https://codecov.io/gh/raiden-network/raiden-services/)

### Monitoring Service

The Monitoring Service watches open payment channels when the user is not online. In case one of the user’s channel partners wants to close a channel while the user is offline, the monitoring service sends the latest balance proof to the smart contract and thus ensures the correct settlement of the channel.

### Pathfinding Service

The Pathfinding service supports users in finding the cheapest or shortest way to route a payment through the network. A pathfinding service relies on data from the network, the respective smart contract as well as information provided voluntarily by mediating nodes. This information consists of the mediation fees charged and the respective available channel capacities.

### Specification

For more technical details see:
- [Services smart contracts specification](https://raiden-network-specification.readthedocs.io/en/latest/service_contracts.html)
- [Monitoring Service specification](https://raiden-network-specification.readthedocs.io/en/latest/monitoring_service.html)
- [Pathfinding Service specification](https://raiden-network-specification.readthedocs.io/en/latest/pathfinding_service.html)

## Getting started

The Raiden Services require Python 3.7+.

To install the Raiden services run the following commands:

```sh
virtualenv -p python3.7 venv
. venv/bin/activate
pip install raiden-services
```
