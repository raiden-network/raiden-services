# Changelog

### 0.10.0 (2020-05-20)

* PFS: Improve error messages (https://github.com/raiden-network/raiden-services/pull/779)
* MS/PFS: Catch exceptions in Matrix correctly (https://github.com/raiden-network/raiden-services/pull/780)
* MS/PFS: Update to latest contracts (https://github.com/raiden-network/raiden-services/pull/784)
* MS/PFS: Make blockchain syncing adaptive (https://github.com/raiden-network/raiden-services/issues/782)

### 0.9.0 (2020-05-11)

* PFS: Add matrix server to `/info` endpoint (https://github.com/raiden-network/raiden-services/pull/771)
* PFS: Add CLI option to set PFS port (https://github.com/raiden-network/raiden-services/pull/770)
* MS: Change default minimum required reward to Raiden's default (https://github.com/raiden-network/raiden-services/pull/773)
* MS: Add gas price CLI argument (https://github.com/raiden-network/raiden-services/pull/774)
* Service Registry: Reset token allowance if necessary (https://github.com/raiden-network/raiden-services/issues/769)

### 0.8.0 (2020-04-08)

* Update to latest Raiden and contracts (https://github.com/raiden-network/raiden-services/pull/767)

### 0.7.1 (2020-03-31)

* PFS: Provide better error messages when user deposit is too low (https://github.com/raiden-network/raiden-services/pull/761)
* Service Registry: Add interactive mode suitable for external service providers (https://github.com/raiden-network/raiden-services/issues/758)

### 0.7.0 (2020-03-27)

* PFS: Fix invalid hex encoding in `get_feedback_routes` (https://github.com/raiden-network/raiden-services/issues/711)
* PFS: Add more information to `/info` endpoint (https://github.com/raiden-network/raiden-services/pull/705, https://github.com/raiden-network/raiden-services/pull/752)
* MS: Do not send transactions too early (https://github.com/raiden-network/raiden/issues/5919, https://github.com/raiden-network/raiden-services/pull/737)
* MS: Send transaction earlier if possible (https://github.com/raiden-network/raiden-services/issues/721)
* MS/PFS: Improve sentry messages (https://github.com/raiden-network/raiden-services/pull/722)
* MS/PFS: Use stricter mypy settings (https://github.com/raiden-network/raiden-services/pull/704, https://github.com/raiden-network/raiden-services/pull/745)
* MS/PFS: Show disclaimer during startup (https://github.com/raiden-network/raiden-services/issues/741)
* Service Registry: Add *withdraw* command to *register_service* script (https://github.com/raiden-network/raiden-services/issues/743)

### 0.6.0 (2020-01-14)

* PFS: Fix DB schema to not override channels (https://github.com/raiden-network/raiden-services/issues/693)
* PFS: Fix deletion of channels (https://github.com/raiden-network/raiden-services/pull/695)
* PFS: Add UDC info to `/info` endpoint (https://github.com/raiden-network/raiden-services/pull/689)
* PFS: Forbid concurrent database usage (https://github.com/raiden-network/raiden-services/pull/681)
* PFS: Provide specific error message for common errors (https://github.com/raiden-network/raiden-services/pull/674)
* PFS: Wait for first matrix sync before starting PFS API (https://github.com/raiden-network/raiden-services/pull/659)
* PFS: Rework path validation (https://github.com/raiden-network/raiden-services/pull/666)
* PFS: Improve handling of `PFSFeeUpdate` messages (https://github.com/raiden-network/raiden-services/pull/661)
* MS/PFS: Add profiling options to services (https://github.com/raiden-network/raiden-services/pull/653)
* MS/PFS: Don't replace gevent's error handler (https://github.com/raiden-network/raiden-services/pull/652)

### 0.5.0 (2019-11-25)

* Properly handle 'ValueError: x_list must be in strictly ascending order!' (https://github.com/raiden-network/raiden-services/issues/636)
* Don't force presence update when receiving capacity update (https://github.com/raiden-network/raiden-services/pull/647)
* Allow passing Matrix servers as CLI arguments (https://github.com/raiden-network/raiden-services/issues/633)
* Properly validate integer fields in API (https://github.com/raiden-network/raiden-services/issues/620)
* Properly validate `DateTime`s in messages and API (https://github.com/raiden-network/raiden-services/issues/619)
* Fix unhandled exception when receiving unexpected IOU (https://github.com/raiden-network/raiden-services/issues/624)
* Increase precision in fee calculation (https://github.com/raiden-network/raiden-services/pull/611)
* Add JSON logging mode (https://github.com/raiden-network/raiden-services/pull/599)
* Wait for Matrix to start properly (https://github.com/raiden-network/raiden-services/pull/595)
* Show contracts version in info endpoint (https://github.com/raiden-network/raiden-services/issues/590)
* Add capped mediation fees (https://github.com/raiden-network/raiden-services/pull/574)
* Use production Matrix servers on mainnet (https://github.com/raiden-network/raiden-services/issues/575)

### 0.4.1 (2019-10-08)

* Improve Dockerfile (https://github.com/raiden-network/raiden-services/pull/570)

### 0.4.0 (2019-10-04)

* Improve accuracy of imbalance fee calculation (https://github.com/raiden-network/raiden-services/pull/565)
* Allow CORS requests to PFS (https://github.com/raiden-network/raiden-services/pull/559)
* Check MS registration at startup (https://github.com/raiden-network/raiden-services/pull/545)
* Improve PFS routing performance (https://github.com/raiden-network/raiden-services/pull/521)
* Bugfix: handle nodes with unknown visibility (https://github.com/raiden-network/raiden-services/pull/525)

### 0.3.0 (2019-08-13)

* Wait for confirmation of transactions in monitoring service (https://github.com/raiden-network/raiden-ya(services/pull/503)
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
