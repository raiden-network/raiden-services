=========
Changelog
=========

* Changes entry point commands from "_" to "-"
* PR review
* Fix state update when new token network is found
* Silence mypy in a case it gets wrong
* Remove raiden_libs.message.Message
* Rename to HashedBalanceProof, more flexible init.
* Remove BalanceProof message from raiden-libs
* Test channel_settled_event_handler
* Test that expired settlement period channels are ignored
* Add foreign key on channel(token_network_address)
* Review feedback #88
* Add tests for channel and MR loading and saving
* Remove outdates tables from schema
* Fix linting errors
* Unify db classes between MS and requrest collector
* Use same db code to persist channels in MR and RC
* Use MR form MS in request collector
* Increase reability of `database.py`
* Make mypy happy at the new, stricter settings
* Prepare merging of `Database` and `SqliteStateDB`
* Add non_closing signer to properly identify MRs
* Save MS state to database, rough version
* Test event filtering boundaries and simplify limit calculation in BC listener (#86)
* Sets 'topics=[None]' for event filtering of MS contract
* Add POA middleware to make PFS run on POA test chains
* Enable --disallow-untyped-defs for monitoring_service
* Add more folders to .dockerignore
* Add .dockerignore and update Dockerfile for PFS
* PR review
* Don't check for available MR at ReceiveChannelClosedEvent
* Add test for `monitor` being called after ActionMonitoringTriggeredEvent
* (change_eth_getLog_topics_to_None) Add test for MR received before ChannelOpen event
* Link docs in REAME
* Add basic Sphinx docs and requirements
* Remove merkle tree utils
* Add basic MS cli test
* Lint whole src/ directory
* Remove gevent Matrix client
* PR review
* Add basic information to the README
* Fix remaining problems
* Adds tests to makefile and resolves most make lint errors
* PR review
* Factor out initial state setup in event handler tests
* Unify all event exception tests in one test
* Update channel state correctly
* Add tests for action_monitoring_triggered_event_handler
* Add tests for monitor_new_balance_proof_event_handler
* Add tests for channel_non_closing_balance_proof_updated_event_handler
* Handle updates from Raiden nodes
* Enable request collector cli tests
* Fix tests after rename of RSB in contracts
* Don't generate universal wheels
* Remove unused fixture
* Simply monitoring service fixture
* Remove raiden-libs BlockChain listener
* Remove no_ssl_verification context manager
* (solve_linting_problems) Remove FeeInfo, PathsReply and PathsRequest messages (#60)
* Add client update period of 30% settle period before MS intervention
* Remove unused monitor_addres from MR
* PR review
* Only trigger rewards claim if MS is eligible
* Remove old reference to raiden-libs
* Return new MonitorRequest state from MockRaidenClient
* Adapt to updated contracts
* Pr review
* Implement on-chain transactions
* Make from_block exclusive
* Introduce and listen to events from MS contract
* Remove support for python 3.6
* Fix failing tests
* Move all services in a single package
* Adds settle & reveal timeout to path finding - incl. tests (#46)
* Make log level configurable
* Fix addition of new token networks
* Bring back command line parameters
* Add more state handler tests
* Move monitoring_service tests to own directory
* Remove unnessesary data from MonitorRequest
* Remodel blockchain listeners to make state more explicit
* Make client runnable again
* Change event handlers to functions
* Use UserDepositContract
* Transfer request_collector in new project
* Remove old MS code
* Add basic E2E test
* Add signing code to MonitorRequest
* Package restructure
* Remove test file
* Don't schedule monitoring if settle period is in the past
* Add structlog logging
* Start implementing MonitorRequest handling
* Add scheduled events
* Add new event based monitoring service.
* Test for event based architecture
* MS now uses UDC instead of its own balances
* Adds settle_timeout & reveal_timeout to pfs's channel view
* Add coveragerc to libs
* Update travis file
* Add isort config
* Fix some flake8 errors
* Basic travis setup
* Add editors to gitignore
* Update issue templates
* Update issue templates
* Merge pull request #1 from karlb/master
* Add 'libs/' from commit '9902dcdb74b8d18a232df3f1e1dc5442882419fe'
* Add 'monitoring/' from commit '49c0200f101b23a2913ea57805eb3e52295154c1'
* Add 'pathfinding/' from commit '2ee7fa78122d1739e61e463d4fff0c1e05ad86ed'
* Initial commit
* Remove chunk callbacks
* Proper start_block for new token networks
* Save and reload syncstate for BlockchainListeners
* Remove unnecessary type annotations
* Remove unused travis solc script
* Run isort checking+fixing on request_collector dir
* Minor TokenNetworkListener cleanup
* Split TokenNetworkListener out of server.py
* Fix docker file after rename
* More changes due to request collector split
* Rename `test` dir to `tests` for consistency
* Create separate request_collector tests
* Remove matrix code from main MS
* Move listening for MRs to separate processes
* Make mypy use --check-untyped-defs
* Make mypy use --check-untyped-defs
* Remove unused files
* add type annotation
* Use .sql file for schema (syntax highlighting!)
* Don't use db cursor explicitly
* Use sqlite3 converter to decode hex from db
* Add basic CLI tests
* Address PR review comments
* Use channel info for more thorough MR validation
* Store channel state in db
* Remove `monitoring_service/tools`
* Address PR comments
* Write db access in a more consise way
* Use sqlite3.Row instead of custom row factory
* Remove generic db class
* Remove StateDBMockup and fix discovered problems
* Remove REST Api
* Review fixes
* Remove old BlockchainMonitor
* Integrate the new BlockchainListener into the codebase
* Update .gitignore
* Add new BlockchainListener
* Exclude tests from coverage
* Add coverage to travis build
* Remove codecov token from travis config
* Changes default port pathfinding service to 6000
* Adapt raiden comma style
* Run all lints on travis, fix linting problems
* Remove duplicate check for token network in API
* Remove network graph generation on info endpoint
* Fix name clash between file and module
* Use TEST_POLL_INTERVAL inst. of repeating constant
* Speed up end to end test
