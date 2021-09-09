# Changelog

### 0.17.0 (2021-09-09)
* Update to contracts 0.40.0rc (https://github.com/raiden-network/raiden-services/pull/1062)
* Update to raiden dependency to [latest develop](https://github.com/raiden-network/raiden/commit/9e4ac56117314bc4630e8bf68da2424c01989025) (https://github.com/raiden-network/raiden-services/pull/1062)

### 0.16.0 (2021-08-12)
* Update to contracts 0.39.0 (https://github.com/raiden-network/raiden-services/pull/1052)
* Handle channels closed by cooperative settlement (https://github.com/raiden-network/raiden-services/issues/1040)
* Simplify MS code by using new contract interface (https://github.com/raiden-network/raiden-services/issues/807)
* Fix PFS handling of certain environment variables (https://github.com/raiden-network/raiden-services/issues/1023)

### 0.15.4 (2021-05-17)
* Add displayname to address metadata (https://github.com/raiden-network/raiden-services/pull/1009)
* Add end endpoint to retrieve all online addresses (https://github.com/raiden-network/raiden-services/pull/1010)
* Fix a crash of the `service_registry` script on private chains
* Add Python 3.9 support (https://github.com/raiden-network/raiden-services/pull/877)

### 0.15.3 (2021-05-12)
* Fix a crash of the `service_registry` script on private chains

### 0.15.2 (2021-05-12)
* Add `seen_offline_since` to address_metadata endpoint if node is offline. Returns time in seconds.

### 0.15.1 (2021-05-10)
* Do not join discovery room anymore

### 0.15.0 (2021-05-07)
* Return displayname and capabilities in avatar_url format

### 0.14.4 (2021-04-21)
* Fix an error where the PFS would not reconnect to a homeserver if he becomes unavailable and returns 404

### 0.14.3 (2021-04-21)
* Fix an uncaught error during connecting to matrix server

### 0.14.2 (2021-04-09)
* Allow selection of unstable contracts env for Raiden development
* Add endpoint to fetch address metadata

### 0.14.1 (2021-02-25)
* Fix issues with DNS and logging ([#937](https://github.com/raiden-network/raiden-services/pull/937)).
* Pin `raiden` requirement to specific commit in absence of a recent release.

### 0.14.0 (2021-02-23)
* Change communication model to `toDevice` messages ([#918](https://github.com/raiden-network/raiden-services/pull/918))
* Change the presence tracking model ([#912](https://github.com/raiden-network/raiden-services/pull/912))
* Include user IDs in PFS route responses ([#929](https://github.com/raiden-network/raiden-services/pull/929), [#933](https://github.com/raiden-network/raiden-services/pull/933))
### 0.13.2 (2020-11-25)
* Improve registration script ([#890](https://github.com/raiden-network/raiden-services/pull/890)) to allow for extension.
* Longer timeouts for first Matrix sync ([#878](https://github.com/raiden-network/raiden-services/pull/878)).
* Adaptions for newer Matrix usage in Raiden.
* Dependency updates.

### 0.13.1 (2020-10-06)

* Move metrics endpoint path outside the API ([#870](https://github.com/raiden-network/raiden-services/pull/870))

### 0.13.0 (2020-10-02)

* MS/PFS: Return `price_info` and `block_number` as strings in `/info` endpoint v2, since uint256 are not a safe part of JSON (https://github.com/raiden-network/raiden-services/pull/862)
* Service Registry: Wait until transactions are confirmed (https://github.com/raiden-network/raiden-services/issues/855)

### 0.12.0 (2020-09-16)

* MS/PFS: Add prometheus endpoints for accessing metrics (https://github.com/raiden-network/raiden-services/pull/836)
* PFS: Return broadcast room ID in `info` endpoint (https://github.com/raiden-network/raiden-services/pull/858)
* MS/PFS: Add Python 3.8 support (https://github.com/raiden-network/raiden-services/pull/810)

### 0.11.0 (2020-06-18)

* MS/PFS: Minimize ETH-RPC requests by batching token network event queries (https://github.com/raiden-network/raiden-services/pull/793)
* MS/PFS: Optimize event decoding (https://github.com/raiden-network/raiden-services/pull/795)
* MS/PFS: Introduce adaptive blockchain event filtering (https://github.com/raiden-network/raiden-services/issues/782)
* MS/PFS: Handle `DeprecationSwitch` event properly (https://github.com/raiden-network/raiden-services/issues/787)
* MS/PFS: Update to latest Raiden release (https://github.com/raiden-network/raiden-services/pull/800)
* MS: Prepare API for the MS (not publicly available yet) (https://github.com/raiden-network/raiden-services/pull/797)
* RSB: Check for deprecation of service registry before withdraw (https://github.com/raiden-network/raiden-services/pull/792)
* RSB: Check if IOUs expiration is still valid when collection fees (https://github.com/raiden-network/raiden-services/pull/790)

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
