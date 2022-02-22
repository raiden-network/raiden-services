# Raiden Services

Supplemental services for the [Raiden Network](https://raiden.network/).

[![Build Status](https://travis-ci.com/raiden-network/raiden-services.svg?branch=master)](https://travis-ci.com/raiden-network/raiden-services)
[![Coverage](https://img.shields.io/codecov/c/github/raiden-network/raiden-services.svg?style=round)](https://codecov.io/gh/raiden-network/raiden-services/)

More information can be found in the [documentation](https://raiden-services.readthedocs.io/en/latest/) and in the
[service intro blogpost](https://medium.com/raiden-network/raiden-service-bundle-explained-f9bd3f6f358d).

### Monitoring Service

The Monitoring Service watches open payment channels when the user is not online. In case one of the user’s channel partners wants to close a channel while the user is offline, the monitoring service sends the latest balance proof to the smart contract and thus ensures the correct settlement of the channel.

### Pathfinding Service

The Pathfinding service supports users in finding the cheapest or shortest way to route a payment through the network. A pathfinding service relies on data from the network, the respective smart contract as well as information provided voluntarily by mediating nodes. This information consists of the mediation fees charged and the respective available channel capacities.

### Specification

For more technical details see:
- [Services smart contracts specification](https://raiden-network-specification.readthedocs.io/en/latest/service_contracts.html)
- [Monitoring Service specification](https://raiden-network-specification.readthedocs.io/en/latest/monitoring_service.html)
- [Pathfinding Service specification](https://raiden-network-specification.readthedocs.io/en/latest/pathfinding_service.html)

## Service Providers

To become a service provider, follow the instructions in the [Raiden Service Bundle repository](https://github.com/raiden-network/raiden-service-bundle).

## Developers

The Raiden Services require Python 3.8+.

To install the latest development version of the services run the following commands:

```sh
git clone git@github.com:raiden-network/raiden-services.git
cd raiden-services
virtualenv -p python3.8 venv
source venv/bin/activate
make install-dev
```
