# Changelog

### 0.3.0 (2019-08-13)

* Wait for confirmation of transactions in monitoring service (https://github.com/raiden-network/raiden-services/pull/503)
* Take unconfirmed state into account if necessary, e.g. user deposit check (https://github.com/raiden-network/raiden-services/pull/502)
* Remove handling of ChannelNewDeposit event (https://github.com/raiden-network/raiden-services/pull/496)
* Bugfix: Fix possible crash when receiving unexpected message types (https://github.com/raiden-network/raiden-services/pull/499)
* Bugfix: Fix crash related to handling of settled channels (https://github.com/raiden-network/raiden-services/pull/512)
* Bugfix: Ignore MonitorRequests after channel closing (https://github.com/raiden-network/raiden-services/pull/510)

### 0.2.0 (2019-07-30)

* Update to raiden 0.100.5.dev0
* Add CLI options for PFS info settings (https://github.com/raiden-network/raiden-services/issues/479)
* Provide script to register services in ServiceRegistry (https://github.com/raiden-network/raiden-services/issues/447)
* Allow error reporting to Sentry (https://github.com/raiden-network/raiden-services/issues/406)
* Bugfix: Request collector crashes on unsigned RequestMonitoring Messages (https://github.com/raiden-network/raiden-services/issues/420)
* Bugfix: Request collector stores arbitrary Monitoring Requests (https://github.com/raiden-network/raiden-services/issues/419)
* Bugfix: Monitoring Service database vulnerable to timing based Monitoring Request injection (https://github.com/raiden-network/raiden-services/issues/418)

### 0.1.0 (2019-07-09)

* Initial testnet release of the Raiden Services
