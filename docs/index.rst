Welcome to Raiden Services's documentation!
===========================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Monitoring Service
------------------

The Monitoring Service watches open payment channels when the user is not online. In case one of the user’s channel partners wants to close a channel while the user is offline, the monitoring service sends the latest balance proof to the smart contract and thus ensures the correct settlement of the channel.

Pathfinding Service
-------------------

The Pathfinding service supports users in finding the cheapest or shortest way to route a payment through the network. A pathfinding service relies on data from the network, the respective smart contract as well as information provided voluntarily by mediating nodes. This information consists of the mediation fees charged and the respective available channel capacities.

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
