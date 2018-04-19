DB_CREATION_SQL = """
CREATE TABLE `metadata` (
    `chain_id`                              INTEGER,
    `monitoring_contract_address`           CHAR(42),
    `receiver`                              CHAR(42)
);
CREATE TABLE `syncstate` (
    `confirmed_head_number`   INTEGER,
    `confirmed_head_hash`     CHAR(66),
    `unconfirmed_head_number` INTEGER,
    `unconfirmed_head_hash`   CHAR(66)
);
-- channel_id is uint256
-- transferred_amount is uint256
-- reward_amount is uint192
-- nonce is uint64
CREATE TABLE `monitor_requests` (
    `channel_identifier` CHAR(34)    NOT NULL PRIMARY KEY,
    `nonce`              CHAR(34)    NOT NULL,
    `transferred_amount` CHAR(34)    NOT NULL,
    `locksroot`          CHAR(34)    NOT NULL,
    `extra_hash`         CHAR(32)    NOT NULL,
    `balance_proof_signature`  CHAR(160)   NOT NULL,
    `reward_sender_address`    CHAR(42)    NOT NULL,
    `reward_proof_signature`   CHAR(42)    NOT NULL,
    `reward_amount`            CHAR(34)    NOT NULL,
    `token_network_address`    CHAR(42)    NOT NULL
);
INSERT INTO `metadata` VALUES (
    NULL,
    NULL,
    NULL
);
INSERT INTO `syncstate` VALUES (
    NULL,
    NULL,
    NULL,
    NULL
);
"""


ADD_MONITOR_REQUEST_SQL = """
INSERT OR REPLACE INTO `monitor_requests` VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
);"""

UPDATE_METADATA_SQL = """
UPDATE `metadata` SET
    `chain_id` = ?,
    `monitoring_contract_address` = ?,
    `receiver` = ?;
"""
